"""Network inspection tools."""

from __future__ import annotations

from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


def list_networks(config: ServerConfig, libvirt_adapter: LibvirtAdapter, *, hypervisor_ref: str | None) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_networks(uri)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_network(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_network(uri, network_name)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_network_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_xml: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_define_allowed(config, "define_network_xml")
    network_name = _extract_name_from_xml(network_xml)
    _ensure_test_prefix(config, tool_name="define_network_xml", object_name=network_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_network_xml(uri, network_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def start_network(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "start_network")
    _ensure_test_prefix(config, tool_name="start_network", object_name=network_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.start_network(uri, network_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def destroy_network(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "destroy_network")
    _ensure_test_prefix(config, tool_name="destroy_network", object_name=network_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.destroy_network(uri, network_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_network(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "undefine_network")
    _ensure_test_prefix(config, tool_name="undefine_network", object_name=network_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_network(uri, network_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _ensure_mutations_allowed(config: ServerConfig, tool_name: str) -> None:
    if config.allow_mutations:
        return
    raise MCPError(
        code="MUTATION_DISABLED",
        message=f"Tool '{tool_name}' is disabled while allow_mutations=false",
        details={"tool_name": tool_name, "policy": "allow_mutations"},
    )


def _ensure_define_allowed(config: ServerConfig, tool_name: str) -> None:
    if config.allow_define:
        return
    raise MCPError(
        code="DEFINE_DISABLED",
        message=f"Tool '{tool_name}' is disabled while allow_define=false",
        details={"tool_name": tool_name, "policy": "allow_define"},
    )


def _extract_name_from_xml(network_xml: str) -> str:
    try:
        root = ET.fromstring(network_xml)
    except Exception as exc:
        raise MCPError(code="INVALID_NETWORK_XML", message="Invalid network XML", details={"cause": str(exc)})
    if root.tag != "network":
        raise MCPError(code="INVALID_NETWORK_XML", message="Expected root tag 'network'")
    name_node = root.find("name")
    name = (name_node.text or "").strip() if name_node is not None else ""
    if not name:
        raise MCPError(code="INVALID_NETWORK_XML", message="Network XML must include <name>")
    return name


def _ensure_test_prefix(config: ServerConfig, *, tool_name: str, object_name: str) -> None:
    if object_name.startswith(config.test_resource_prefix):
        return
    raise MCPError(
        code="TEST_PREFIX_REQUIRED",
        message=f"Tool '{tool_name}' requires '{config.test_resource_prefix}' prefix (got '{object_name}')",
        details={"tool_name": tool_name, "object_name": object_name, "required_prefix": config.test_resource_prefix},
    )


# ---------------------------------------------------------------------------
# Host network interfaces
# ---------------------------------------------------------------------------


def list_interfaces(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    hypervisor_ref: str | None = None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_interfaces(uri)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_interface(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    iface_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_interface(uri, iface_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_interface_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    interface_xml: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_define_allowed(config, "define_interface_xml")
    iface_name = _extract_interface_name_from_xml(interface_xml)
    _ensure_test_prefix(config, tool_name="define_interface_xml", object_name=iface_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_interface_xml(uri, interface_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def start_interface(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    iface_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "start_interface")
    _ensure_test_prefix(config, tool_name="start_interface", object_name=iface_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.start_interface(uri, iface_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def stop_interface(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    iface_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "stop_interface")
    _ensure_test_prefix(config, tool_name="stop_interface", object_name=iface_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.stop_interface(uri, iface_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_interface(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    iface_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "undefine_interface")
    _ensure_test_prefix(config, tool_name="undefine_interface", object_name=iface_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_interface(uri, iface_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _extract_interface_name_from_xml(interface_xml: str) -> str:
    try:
        root = ET.fromstring(interface_xml)
    except Exception as exc:
        raise MCPError(code="INVALID_INTERFACE_XML", message="Invalid interface XML", details={"cause": str(exc)})
    if root.tag != "interface":
        raise MCPError(code="INVALID_INTERFACE_XML", message="Expected root tag 'interface'")
    name_node = root.find("name")
    name = (name_node.text or "").strip() if name_node is not None else ""
    if not name:
        # fall back to 'name' attribute on root
        name = (root.get("name") or "").strip()
    if not name:
        raise MCPError(code="INVALID_INTERFACE_XML", message="Interface XML must include <name> or name attribute")
    return name


# ---------------------------------------------------------------------------
# Network filters
# ---------------------------------------------------------------------------


def list_nwfilters(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    hypervisor_ref: str | None = None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_nwfilters(uri)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_nwfilter(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    filter_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_nwfilter(uri, filter_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_nwfilter_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    filter_xml: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_define_allowed(config, "define_nwfilter_xml")
    filter_name = _extract_nwfilter_name_from_xml(filter_xml)
    _ensure_test_prefix(config, tool_name="define_nwfilter_xml", object_name=filter_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_nwfilter_xml(uri, filter_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_nwfilter(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    filter_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "undefine_nwfilter")
    _ensure_test_prefix(config, tool_name="undefine_nwfilter", object_name=filter_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_nwfilter(uri, filter_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _extract_nwfilter_name_from_xml(filter_xml: str) -> str:
    try:
        root = ET.fromstring(filter_xml)
    except Exception as exc:
        raise MCPError(code="INVALID_NWFILTER_XML", message="Invalid nwfilter XML", details={"cause": str(exc)})
    if root.tag != "filter":
        raise MCPError(code="INVALID_NWFILTER_XML", message="Expected root tag 'filter'")
    name = (root.get("name") or "").strip()
    if not name:
        name_node = root.find("name")
        name = (name_node.text or "").strip() if name_node is not None else ""
    if not name:
        raise MCPError(code="INVALID_NWFILTER_XML", message="NWFilter XML must include name attribute")
    return name


# ---------------------------------------------------------------------------
# Network DHCP leases
# ---------------------------------------------------------------------------


def get_network_dhcp_leases(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    leases = libvirt_adapter.get_network_dhcp_leases(uri, network_name)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "network_name": network_name,
        "items": leases,
        "total_count": len(leases),
    }


# ---------------------------------------------------------------------------
# Network autostart
# ---------------------------------------------------------------------------


def set_network_autostart(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    network_name: str,
    autostart: bool,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "set_network_autostart")
    _ensure_test_prefix(config, tool_name="set_network_autostart", object_name=network_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_network_autostart(uri, network_name, autostart)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload
