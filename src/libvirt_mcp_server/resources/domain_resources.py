"""Resource helpers for domain reads."""

from __future__ import annotations

from libvirt_mcp_server.server import LibvirtMCPServer


async def read_domain(server: LibvirtMCPServer, domain_ref: str, hypervisor_ref: str | None = None) -> dict:
    args = {"domain_ref": domain_ref}
    if hypervisor_ref:
        args["hypervisor_ref"] = hypervisor_ref
    return await server.call_tool("get_domain", args)


async def read_domain_xml(server: LibvirtMCPServer, domain_ref: str, hypervisor_ref: str | None = None) -> dict:
    args = {"domain_ref": domain_ref, "inactive": True, "live": False}
    if hypervisor_ref:
        args["hypervisor_ref"] = hypervisor_ref
    return await server.call_tool("get_domain_xml", args)
