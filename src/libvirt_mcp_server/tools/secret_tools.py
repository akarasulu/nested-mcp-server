"""Secret lifecycle tools - virSecret* operations."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


def list_secrets(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_secrets(uri)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "items": items,
        "total_count": len(items),
    }


def get_secret(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    secret_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_secret(uri, secret_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def define_secret_xml(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    secret_xml: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_define_allowed(config, "define_secret_xml")
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.define_secret_xml(uri, secret_xml)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def set_secret_value(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    secret_ref: str,
    value_b64: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "set_secret_value")
    try:
        value_bytes = base64.b64decode(value_b64)
    except Exception as exc:
        raise MCPError(
            code="INVALID_SECRET_VALUE",
            message="secret value must be valid base64",
            retryable=False,
            details={"source": "libvirt", "cause": str(exc)},
        )
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.set_secret_value(uri, secret_ref, value_bytes)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def get_secret_value(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    secret_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_secret_read_allowed(config, "get_secret_value")
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.get_secret_value(uri, secret_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def undefine_secret(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    secret_ref: str,
    hypervisor_ref: str | None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "undefine_secret")
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.undefine_secret(uri, secret_ref)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _ensure_define_allowed(config: ServerConfig, tool_name: str) -> None:
    if not config.allow_define:
        raise MCPError(
            code="DEFINE_DISABLED",
            message=f"Tool '{tool_name}' is disabled while allow_define=false",
            details={"tool_name": tool_name, "policy": "allow_define"},
        )


def _ensure_mutations_allowed(config: ServerConfig, tool_name: str) -> None:
    if not config.allow_mutations:
        raise MCPError(
            code="MUTATION_DISABLED",
            message=f"Tool '{tool_name}' is disabled while allow_mutations=false",
            details={"tool_name": tool_name, "policy": "allow_mutations"},
        )


def _ensure_secret_read_allowed(config: ServerConfig, tool_name: str) -> None:
    if not config.allow_secret_read:
        raise MCPError(
            code="SECRET_READ_DISABLED",
            message=f"Tool '{tool_name}' requires allow_secret_read=true in server config",
            details={"tool_name": tool_name, "policy": "allow_secret_read"},
        )
