"""Domain snapshot tools."""

from __future__ import annotations

from datetime import datetime, timezone

from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError


def list_domain_snapshots(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    hypervisor_ref: str | None,
) -> dict:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    items = libvirt_adapter.list_domain_snapshots(uri, domain_ref)
    return {
        "source": "libvirt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hypervisor_ref": hypervisor_ref or "default",
        "domain_ref": domain_ref,
        "items": items,
        "total_count": len(items),
    }


def create_domain_snapshot(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    snapshot_xml: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "create_domain_snapshot")
    _ensure_domain_mutation_allowed(config, "create_domain_snapshot", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.create_domain_snapshot(uri, domain_ref, snapshot_xml)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def revert_domain_snapshot(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    snapshot_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "revert_domain_snapshot")
    _ensure_domain_mutation_allowed(config, "revert_domain_snapshot", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.revert_domain_snapshot(uri, domain_ref, snapshot_name)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def delete_domain_snapshot(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    snapshot_name: str,
    hypervisor_ref: str | None,
) -> dict:
    _ensure_mutations_allowed(config, "delete_domain_snapshot")
    _ensure_domain_mutation_allowed(config, "delete_domain_snapshot", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.delete_domain_snapshot(uri, domain_ref, snapshot_name)
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def _ensure_mutations_allowed(config: ServerConfig, tool_name: str) -> None:
    if not config.allow_mutations:
        raise MCPError(
            code="MUTATION_DISABLED",
            message=f"Tool '{tool_name}' is disabled while allow_mutations=false",
            details={"tool_name": tool_name, "policy": "allow_mutations"},
        )


def _ensure_domain_mutation_allowed(config: ServerConfig, tool_name: str, domain_ref: str) -> None:
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
