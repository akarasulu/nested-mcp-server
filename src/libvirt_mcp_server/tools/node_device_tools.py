"""Node device tools for host PCI/USB/etc device management."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


def list_node_devices(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    capability: str | None = None,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_node_devices(uri, capability=capability)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_node_device(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    device_name: str,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_node_device(uri, device_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def detach_node_device(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    device_name: str,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "detach_node_device")
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.detach_node_device(uri, device_name)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def reattach_node_device(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    device_name: str,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "reattach_node_device")
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.reattach_node_device(uri, device_name)
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
