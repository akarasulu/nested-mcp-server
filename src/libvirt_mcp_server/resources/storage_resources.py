"""Resource helpers for storage pool reads."""

from __future__ import annotations

from libvirt_mcp_server.server import LibvirtMCPServer


async def read_storage_pools(server: LibvirtMCPServer, hypervisor_ref: str | None = None) -> dict:
    args = {"hypervisor_ref": hypervisor_ref} if hypervisor_ref else {}
    return await server.call_tool("list_storage_pools", args)
