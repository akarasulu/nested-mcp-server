"""Block job tools for domain disk operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.errors import MCPError


def block_pull(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    disk: str,
    bandwidth: int = 0,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "block_pull")
    _ensure_domain_mutation_allowed(config, "block_pull", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.block_pull(uri, domain_ref, disk, bandwidth)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def block_commit(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    disk: str,
    base: str | None = None,
    top: str | None = None,
    bandwidth: int = 0,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "block_commit")
    _ensure_domain_mutation_allowed(config, "block_commit", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.block_commit(uri, domain_ref, disk, base=base, top=top, bandwidth=bandwidth)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def block_job_abort(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    disk: str,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    _ensure_mutations_allowed(config, "block_job_abort")
    _ensure_domain_mutation_allowed(config, "block_job_abort", domain_ref)
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.block_job_abort(uri, domain_ref, disk)
    payload["hypervisor_ref"] = hypervisor_ref or "default"
    return payload


def block_job_info(
    config: ServerConfig,
    libvirt_adapter: LibvirtAdapter,
    *,
    domain_ref: str,
    disk: str,
    hypervisor_ref: str | None = None,
) -> dict[str, Any]:
    uri = config.get_hypervisor_uri(hypervisor_ref)
    payload = libvirt_adapter.block_job_info(uri, domain_ref, disk)
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
