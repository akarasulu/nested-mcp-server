"""Resource helpers for host capabilities."""

from __future__ import annotations

from libvirt_mcp_server.server import LibvirtMCPServer


async def read_host_capabilities(server: LibvirtMCPServer, hypervisor_ref: str | None = None) -> dict:
    return await server.call_tool("host_info", {"hypervisor_ref": hypervisor_ref} if hypervisor_ref else {})
