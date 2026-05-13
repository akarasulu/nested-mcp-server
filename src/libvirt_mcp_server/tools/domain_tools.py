"""Domain tools for lifecycle and XML operations."""

from __future__ import annotations

from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from typing import Any

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


LIFECYCLE_TOOLS = {
    "start_domain",
    "shutdown_domain",
    "destroy_domain",
    "reboot_domain",
    "suspend_domain",
    "resume_domain",
}


def list_domains(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    active_only: bool,
    inactive_only: bool,
    name_prefix: str | None,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_domains(
        uri,
        active_only=active_only,
        inactive_only=inactive_only,
        name_prefix=name_prefix,
    )
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_domain(config: ServerConfig, libvirt_adapter: LibvirtAdapter, *, domain_ref: str, hypervisor_ref: str | None) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    item = libvirt_adapter.get_domain(uri, domain_ref)
    item["timestamp"] = datetime.now(timezone.utc).isoformat()
    item["hypervisor_ref"] = hypervisor_ref or "default"
    return item


def get_domain_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
    live: bool,
    inactive: bool,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_xml(uri, domain_ref, live=live, inactive=inactive)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def set_domain_autostart(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
    autostart: bool,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="set_domain_autostart")
    _ensure_domain_mutation_allowed(config, tool_name="set_domain_autostart", domain_ref=domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_autostart(uri, domain_ref, autostart)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_domain_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_xml: str,
    hypervisor_ref: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    _ensure_define_allowed(config, tool_name="define_domain_xml")
    domain_name = _extract_name_from_xml(domain_xml, "domain")
    _ensure_test_prefix(config, tool_name="define_domain_xml", object_name=domain_name)
    if dry_run:
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypervisor_ref": hypervisor_ref or "default",
            "domain_ref": domain_name,
            "dry_run": True,
            "status": "approved",
        }
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_domain_xml(uri, domain_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def validate_domain_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_xml: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.validate_domain_xml(uri, domain_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def update_domain_device_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    device_xml: str,
    live: bool,
    persistent: bool,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="update_domain_device_xml")
    _ensure_domain_mutation_allowed(config, tool_name="update_domain_device_xml", domain_ref=domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.update_domain_device_xml(uri, domain_ref, device_xml, live=live, config=persistent)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_domain(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="undefine_domain")
    _ensure_test_prefix(config, tool_name="undefine_domain", object_name=domain_ref)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_domain(uri, domain_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def lifecycle_action(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    tool_name: str,
    domain_ref: str,
    hypervisor_ref: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if tool_name not in LIFECYCLE_TOOLS:
        raise MCPError(code="INVALID_ACTION", message=f"Unknown lifecycle tool '{tool_name}'")

    _ensure_mutations_allowed(config, tool_name=tool_name)
    _ensure_domain_mutation_allowed(config, tool_name=tool_name, domain_ref=domain_ref)
    if tool_name == "destroy_domain":
        _ensure_destructive_allowed(config, tool_name=tool_name, domain_ref=domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    if dry_run:
        return {
            "source": "libvirt",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hypervisor_ref": hypervisor_ref or "default",
            "domain_ref": domain_ref,
            "action": tool_name,
            "dry_run": True,
            "status": "approved",
        }

    payload = libvirt_adapter.lifecycle_action(uri, domain_ref, action=tool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["dry_run"] = False
    return payload


def _ensure_mutations_allowed(config: ServerConfig, *, tool_name: str) -> None:
    if not config.allow_mutations:
        raise MCPError(
            code="MUTATION_DISABLED",
            message=f"Tool '{tool_name}' is disabled while allow_mutations=false",
            details={"tool_name": tool_name, "policy": "allow_mutations"},
        )


def _ensure_define_allowed(config: ServerConfig, *, tool_name: str) -> None:
    if config.allow_define:
        return
    raise MCPError(
        code="DEFINE_DISABLED",
        message=f"Tool '{tool_name}' is disabled while allow_define=false",
        details={"tool_name": tool_name, "policy": "allow_define"},
    )


def _ensure_domain_mutation_allowed(config: ServerConfig, *, tool_name: str, domain_ref: str) -> None:
    if not config.mutation_domain_allowlist:
        return
    if domain_ref in config.mutation_domain_allowlist:
        return
    raise MCPError(
        code="MUTATION_DOMAIN_DENIED",
        message=f"Tool '{tool_name}' is denied for domain '{domain_ref}' by mutation allowlist",
        details={
            "tool_name": tool_name,
            "domain_ref": domain_ref,
            "policy": "mutation_domain_allowlist",
            "allowed_domains": sorted(config.mutation_domain_allowlist),
        },
    )


def _ensure_destructive_allowed(config: ServerConfig, *, tool_name: str, domain_ref: str) -> None:
    if config.allow_destructive:
        return
    if domain_ref in config.destructive_domain_allowlist:
        return
    raise MCPError(
        code="DESTRUCTIVE_DISABLED",
        message=f"Tool '{tool_name}' is disabled while allow_destructive=false for domain '{domain_ref}'",
        details={
            "tool_name": tool_name,
            "domain_ref": domain_ref,
            "policy": "allow_destructive",
            "allowed_domains": sorted(config.destructive_domain_allowlist),
        },
    )


def _extract_name_from_xml(xml_payload: str, root_tag: str) -> str:
    try:
        root = ET.fromstring(xml_payload)
    except Exception as exc:
        raise MCPError(
            code="INVALID_XML",
            message=f"Invalid {root_tag} XML",
            details={"source": "server", "cause": str(exc)},
        )
    if root.tag != root_tag:
        raise MCPError(
            code="INVALID_XML",
            message=f"Expected root tag '{root_tag}'",
            details={"source": "server", "root_tag": root.tag},
        )
    name_node = root.find("name")
    name = (name_node.text or "").strip() if name_node is not None else ""
    if not name:
        raise MCPError(
            code="INVALID_XML",
            message="Object name is required in XML",
            details={"source": "server", "expected_node": "name"},
        )
    return name


def _ensure_test_prefix(config: ServerConfig, *, tool_name: str, object_name: str) -> None:
    if object_name.startswith(config.test_resource_prefix):
        return
    raise MCPError(
        code="TEST_PREFIX_REQUIRED",
        message=f"Tool '{tool_name}' requires '{config.test_resource_prefix}' prefix (got '{object_name}')",
        details={
            "tool_name": tool_name,
            "object_name": object_name,
            "required_prefix": config.test_resource_prefix,
            "policy": "test_resource_prefix",
        },
    )


# ---------------------------------------------------------------------------
# Domain vCPU and memory tuning
# ---------------------------------------------------------------------------

# Flag constants (mirrors libvirt values)
_VIR_DOMAIN_VCPU_LIVE = 1
_VIR_DOMAIN_VCPU_CONFIG = 2
_VIR_DOMAIN_MEM_LIVE = 1
_VIR_DOMAIN_MEM_CONFIG = 2


def set_domain_vcpus(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    vcpu_count: int,
    live: bool = True,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="set_domain_vcpus")
    _ensure_domain_mutation_allowed(config, tool_name="set_domain_vcpus", domain_ref=domain_ref)

    flags = 0
    if live:
        flags |= _VIR_DOMAIN_VCPU_LIVE
    if persistent:
        flags |= _VIR_DOMAIN_VCPU_CONFIG

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_vcpus(uri, domain_ref, vcpu_count, flags)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["live"] = live
    payload["persistent"] = persistent
    return payload


def set_domain_memory(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    memory_kb: int,
    live: bool = True,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="set_domain_memory")
    _ensure_domain_mutation_allowed(config, tool_name="set_domain_memory", domain_ref=domain_ref)

    flags = 0
    if live:
        flags |= _VIR_DOMAIN_MEM_LIVE
    if persistent:
        flags |= _VIR_DOMAIN_MEM_CONFIG

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_memory(uri, domain_ref, memory_kb, flags)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["live"] = live
    payload["persistent"] = persistent
    return payload


# ---------------------------------------------------------------------------
# Domain statistics
# ---------------------------------------------------------------------------


def get_domain_stats(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_stats(uri, domain_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_domain_block_stats(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    disk: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_block_stats(uri, domain_ref, disk)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_domain_interface_stats(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    interface: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_interface_stats(uri, domain_ref, interface)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_domain_memory_stats(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_memory_stats(uri, domain_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# CPU pinning
# ---------------------------------------------------------------------------


def get_domain_vcpu_pin_info(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_vcpu_pin_info(uri, domain_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def set_domain_vcpu_pin(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    vcpu: int,
    cpumap: list[int],
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="set_domain_vcpu_pin")
    _ensure_domain_mutation_allowed(config, tool_name="set_domain_vcpu_pin", domain_ref=domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_domain_vcpu_pin(uri, domain_ref, vcpu, cpumap)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_domain_emulator_pin_info(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_domain_emulator_pin_info(uri, domain_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def set_domain_emulator_pin(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    cpumap: list[int],
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, tool_name="set_domain_emulator_pin")
    _ensure_domain_mutation_allowed(config, tool_name="set_domain_emulator_pin", domain_ref=domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_domain_emulator_pin(uri, domain_ref, cpumap)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload
