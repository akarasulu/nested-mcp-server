"""Storage inspection tools."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import xml.etree.ElementTree as ET

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


def list_storage_pools(config: ServerConfig, libvirt_adapter: LibvirtAdapter, *, hypervisor_ref: str | None) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_storage_pools(uri)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_storage_pool(uri, pool_name)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def list_storage_volumes(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_storage_volumes(uri, pool_name)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "pool_name": pool_name,
        "items": items,
        "total_count": len(items),
    }


def get_storage_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_storage_volume(uri, pool_name, volume_name)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_storage_pool_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_xml: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_define_allowed(config, "define_storage_pool_xml")
    pool_name = _extract_name_from_xml(pool_xml, "pool", "name", "INVALID_STORAGE_POOL_XML")
    _ensure_test_prefix(config, tool_name="define_storage_pool_xml", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_storage_pool_xml(uri, pool_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def start_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "start_storage_pool")
    _ensure_test_prefix(config, tool_name="start_storage_pool", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.start_storage_pool(uri, pool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def destroy_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "destroy_storage_pool")
    _ensure_test_prefix(config, tool_name="destroy_storage_pool", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.destroy_storage_pool(uri, pool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "undefine_storage_pool")
    _ensure_test_prefix(config, tool_name="undefine_storage_pool", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_storage_pool(uri, pool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def create_storage_volume_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_xml: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "create_storage_volume_xml")
    _ensure_test_prefix(config, tool_name="create_storage_volume_xml", object_name=pool_name)
    volume_name = _extract_name_from_xml(volume_xml, "volume", "name", "INVALID_STORAGE_VOLUME_XML")
    _ensure_test_prefix(config, tool_name="create_storage_volume_xml", object_name=volume_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.create_storage_volume_xml(uri, pool_name, volume_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def create_linked_clone_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    backing_file: str,
    capacity_bytes: int,
    format: str,
    backing_format: str,
    relative_backing: bool,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "create_linked_clone_volume")
    _ensure_test_prefix(config, tool_name="create_linked_clone_volume", object_name=pool_name)
    _ensure_test_prefix(config, tool_name="create_linked_clone_volume", object_name=volume_name)

    if relative_backing and os.path.isabs(backing_file):
        raise MCPError(
            code="INVALID_BACKING_PATH",
            message="backing_file must be relative when relative_backing=true",
            details={"backing_file": backing_file, "policy": "relative_backing"},
        )

    volume_xml = _build_linked_clone_volume_xml(
        volume_name=volume_name,
        backing_file=backing_file,
        capacity_bytes=capacity_bytes,
        format=format,
        backing_format=backing_format,
    )
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.create_storage_volume_xml(uri, pool_name, volume_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    payload["backing_file"] = backing_file
    payload["relative_backing"] = relative_backing
    return payload


def delete_storage_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "delete_storage_volume")
    _ensure_test_prefix(config, tool_name="delete_storage_volume", object_name=pool_name)
    _ensure_test_prefix(config, tool_name="delete_storage_volume", object_name=volume_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.delete_storage_volume(uri, pool_name, volume_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload



def get_volume_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_volume_xml(uri, pool_name, volume_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_volume_backing_chain(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_volume_backing_chain(uri, pool_name, volume_name)
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


def _extract_name_from_xml(xml_payload: str, root_tag: str, name_tag: str, code: str) -> str:
    try:
        root = ET.fromstring(xml_payload)
    except Exception as exc:
        raise MCPError(code=code, message=f"Invalid {root_tag} XML", details={"cause": str(exc)})
    if root.tag != root_tag:
        raise MCPError(code=code, message=f"Expected root tag '{root_tag}'")
    name_node = root.find(name_tag)
    name = (name_node.text or "").strip() if name_node is not None else ""
    if not name:
        raise MCPError(code=code, message=f"{root_tag} XML must include <{name_tag}>")
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
# Storage volume clone
# ---------------------------------------------------------------------------


def clone_storage_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    src_pool_name: str,
    src_volume_name: str,
    volume_xml: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "clone_storage_volume")
    _ensure_test_prefix(config, tool_name="clone_storage_volume", object_name=volume_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.clone_storage_volume(uri, pool_name, volume_name, src_pool_name, src_volume_name, volume_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Storage pool autostart and refresh
# ---------------------------------------------------------------------------


def set_storage_pool_autostart(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    autostart: bool,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "set_storage_pool_autostart")
    _ensure_test_prefix(config, tool_name="set_storage_pool_autostart", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_storage_pool_autostart(uri, pool_name, autostart)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def refresh_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "refresh_storage_pool")

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.refresh_storage_pool(uri, pool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _build_linked_clone_volume_xml(
    *,
    volume_name: str,
    backing_file: str,
    capacity_bytes: int,
    format: str,
    backing_format: str,
) -> str:
    root = ET.Element("volume")
    ET.SubElement(root, "name").text = volume_name

    capacity = ET.SubElement(root, "capacity", unit="bytes")
    capacity.text = str(capacity_bytes)

    target = ET.SubElement(root, "target")
    ET.SubElement(target, "format", type=format)

    backing_store = ET.SubElement(root, "backingStore")
    ET.SubElement(backing_store, "path").text = backing_file
    ET.SubElement(backing_store, "format", type=backing_format)

    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Storage volume resize and wipe
# ---------------------------------------------------------------------------


def resize_storage_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    capacity_bytes: int,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "resize_storage_volume")
    _ensure_test_prefix(config, tool_name="resize_storage_volume", object_name=volume_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.resize_storage_volume(uri, pool_name, volume_name, capacity_bytes)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def wipe_storage_volume(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    volume_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "wipe_storage_volume")
    _ensure_test_prefix(config, tool_name="wipe_storage_volume", object_name=volume_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.wipe_storage_volume(uri, pool_name, volume_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


# ---------------------------------------------------------------------------
# Storage pool build
# ---------------------------------------------------------------------------


def build_storage_pool(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    pool_name: str,
    hypervisor_ref: str | None = None,
) -> dict:
    _ensure_mutations_allowed(config, "build_storage_pool")
    _ensure_test_prefix(config, tool_name="build_storage_pool", object_name=pool_name)

    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.build_storage_pool(uri, pool_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload
