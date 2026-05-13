"""FastMCP application – registers all tools and exposes the app for transport mounting."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.server import LibvirtMCPServer

# ---------------------------------------------------------------------------
# Module-level singletons – created once on import so the FastMCP @tool
# decorators can reference them at decoration time.
# ---------------------------------------------------------------------------

_config: ServerConfig | None = None
_server: LibvirtMCPServer | None = None
app: FastMCP = FastMCP("nested-mcp-server")


def _get_server() -> LibvirtMCPServer:
    global _config, _server
    if _server is None:
        _config = ServerConfig.from_env()
        _server = LibvirtMCPServer(config=_config)
    return _server


# ---------------------------------------------------------------------------
# Helper – every tool returns a JSON-serialisable dict; we return it as a
# text string so MCP clients receive structured content.
# ---------------------------------------------------------------------------

def _render(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Host / discovery tools
# ---------------------------------------------------------------------------


@app.tool(description="Return host and hypervisor summary, capabilities, and server policy mode.")
async def host_info(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("host_info", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Return host NUMA topology from libvirt capabilities.")
async def get_host_numa_topology(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("get_host_numa_topology", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="List all configured hypervisor endpoints and their connection health.")
async def list_hypervisors() -> str:
    result = await _get_server().call_tool("list_hypervisors", {})
    return _render(result)


@app.tool(description="Return details for a single hypervisor endpoint.")
async def get_hypervisor(hypervisor_ref: str) -> str:
    result = await _get_server().call_tool("get_hypervisor", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="List domains (VMs) on a hypervisor. Filters: active_only, inactive_only, name_prefix.")
async def list_domains(
    active_only: bool = False,
    inactive_only: bool = False,
    name_prefix: str | None = None,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "list_domains",
        {
            "active_only": active_only,
            "inactive_only": inactive_only,
            "name_prefix": name_prefix,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Return a normalised summary for a single domain (VM).")
async def get_domain(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("get_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


# ---------------------------------------------------------------------------
# Domain configuration
# ---------------------------------------------------------------------------


@app.tool(description="Retrieve the XML definition for a domain. Pass live=True for running config.")
async def get_domain_xml(
    domain_ref: str,
    hypervisor_ref: str | None = None,
    live: bool = False,
    inactive: bool = True,
) -> str:
    result = await _get_server().call_tool(
        "get_domain_xml",
        {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "live": live, "inactive": inactive},
    )
    return _render(result)


@app.tool(description="Define a domain from XML. Restricted to test-prefixed domain names.")
async def define_domain_xml(domain_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_domain_xml",
        {"domain_xml": domain_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Undefine a domain. Restricted to test-prefixed domain names.")
async def undefine_domain(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_domain",
        {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Enable or disable autostart for a domain.")
async def set_domain_autostart(domain_ref: str, autostart: bool, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "set_domain_autostart",
        {"domain_ref": domain_ref, "autostart": autostart, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Domain lifecycle
# ---------------------------------------------------------------------------


@app.tool(description="Start (boot) a domain. Requires allow_mutations=true in server config.")
async def start_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "start_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


@app.tool(description="Send ACPI shutdown signal to a domain. Requires allow_mutations=true.")
async def shutdown_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "shutdown_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


@app.tool(description="Immediately terminate (destroy) a domain. Requires allow_destructive=true.")
async def destroy_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "destroy_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


@app.tool(description="Reboot a domain. Requires allow_mutations=true.")
async def reboot_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "reboot_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


@app.tool(description="Suspend (pause) a domain. Requires allow_mutations=true.")
async def suspend_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "suspend_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


@app.tool(description="Resume a suspended domain. Requires allow_mutations=true.")
async def resume_domain(domain_ref: str, hypervisor_ref: str | None = None, dry_run: bool = False) -> str:
    result = await _get_server().call_tool(
        "resume_domain", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref, "dry_run": dry_run}
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


@app.tool(description="List all storage pools on a hypervisor.")
async def list_storage_pools(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("list_storage_pools", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Return details for a single storage pool.")
async def get_storage_pool(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_storage_pool",
        {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="List all storage volumes in a storage pool.")
async def list_storage_volumes(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "list_storage_volumes",
        {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Return details for a single storage volume.")
async def get_storage_volume(pool_name: str, volume_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_storage_volume",
        {"pool_name": pool_name, "volume_name": volume_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Define a storage pool from XML. Restricted to test-prefixed pool names.")
async def define_storage_pool_xml(pool_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_storage_pool_xml",
        {"pool_xml": pool_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Start a storage pool. Restricted to test-prefixed pool names.")
async def start_storage_pool(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "start_storage_pool",
        {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Destroy a storage pool. Restricted to test-prefixed pool names.")
async def destroy_storage_pool(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "destroy_storage_pool",
        {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Undefine a storage pool. Restricted to test-prefixed pool names.")
async def undefine_storage_pool(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_storage_pool",
        {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Create a storage volume in a pool from XML. Restricted to test-prefixed names.")
async def create_storage_volume_xml(pool_name: str, volume_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "create_storage_volume_xml",
        {"pool_name": pool_name, "volume_xml": volume_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Create a linked-clone qcow2 volume with backingStore metadata. Restricted to test-prefixed names.")
async def create_linked_clone_volume(
    pool_name: str,
    volume_name: str,
    backing_file: str,
    capacity_bytes: int = 107374182400,
    format: str = "qcow2",
    backing_format: str = "qcow2",
    relative_backing: bool = True,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "create_linked_clone_volume",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "backing_file": backing_file,
            "capacity_bytes": capacity_bytes,
            "format": format,
            "backing_format": backing_format,
            "relative_backing": relative_backing,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Upload a local file into a storage volume. Restricted to test-prefixed names.")
async def upload_storage_volume(
    pool_name: str,
    volume_name: str,
    source_path: str,
    offset: int = 0,
    length: int | None = None,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "upload_storage_volume",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "source_path": source_path,
            "offset": offset,
            "length": length,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Download a storage volume range into a safe local path.")
async def download_storage_volume(
    pool_name: str,
    volume_name: str,
    target_path: str,
    offset: int = 0,
    length: int | None = None,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "download_storage_volume",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "target_path": target_path,
            "offset": offset,
            "length": length,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Delete a storage volume from a pool. Restricted to test-prefixed names.")
async def delete_storage_volume(pool_name: str, volume_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "delete_storage_volume",
        {"pool_name": pool_name, "volume_name": volume_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------


@app.tool(description="List all virtual networks on a hypervisor.")
async def list_networks(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("list_networks", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Return details for a single virtual network.")
async def get_network(network_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_network",
        {"network_name": network_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Define a virtual network from XML. Restricted to test-prefixed network names.")
async def define_network_xml(network_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_network_xml",
        {"network_xml": network_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Start a virtual network. Restricted to test-prefixed network names.")
async def start_network(network_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "start_network",
        {"network_name": network_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Destroy a virtual network. Restricted to test-prefixed network names.")
async def destroy_network(network_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "destroy_network",
        {"network_name": network_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Undefine a virtual network. Restricted to test-prefixed network names.")
async def undefine_network(network_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_network",
        {"network_name": network_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@app.tool(description="List all snapshots for a domain.")
async def list_domain_snapshots(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "list_domain_snapshots",
        {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Create a snapshot for a domain from snapshot XML.")
async def create_domain_snapshot(domain_ref: str, snapshot_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "create_domain_snapshot",
        {"domain_ref": domain_ref, "snapshot_xml": snapshot_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Revert a domain to an existing snapshot.")
async def revert_domain_snapshot(domain_ref: str, snapshot_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "revert_domain_snapshot",
        {"domain_ref": domain_ref, "snapshot_name": snapshot_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Delete an existing domain snapshot.")
async def delete_domain_snapshot(domain_ref: str, snapshot_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "delete_domain_snapshot",
        {"domain_ref": domain_ref, "snapshot_name": snapshot_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# QMP bridge
# ---------------------------------------------------------------------------


@app.tool(
    description=(
        "Execute a QMP command against a domain. The command must be in the "
        "server's qmp_allowlist. Requires allow_qmp=true."
    )
)
async def qmp_command(
    domain_ref: str,
    command: str,
    arguments: str = "{}",
    hypervisor_ref: str | None = None,
) -> str:
    try:
        parsed_args: dict[str, Any] = json.loads(arguments)
    except Exception:
        return _render({"error": {"code": "INVALID_ARGUMENTS", "message": "arguments must be a JSON object string"}})
    result = await _get_server().call_tool(
        "qmp_command",
        {"domain_ref": domain_ref, "command": command, "arguments": parsed_args, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Return available QMP commands/features discovered for a domain endpoint.")
async def qmp_capabilities(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "qmp_capabilities", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Collect async QMP events from a running domain. Polls socket for up to timeout_seconds.")
async def qmp_events(
    domain_ref: str,
    event_types: list[str] | None = None,
    since: str | None = None,
    timeout_seconds: float = 2.0,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "qmp_events",
        {"domain_ref": domain_ref, "event_types": event_types or [], "since": since, "timeout_seconds": timeout_seconds, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Typed QMP query tools
# ---------------------------------------------------------------------------


@app.tool(description="Query running status of a domain via QMP.")
async def qmp_query_status(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_status", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query QEMU version for a domain via QMP.")
async def qmp_query_version(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_version", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query CPU information for a domain via QMP.")
async def qmp_query_cpus(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_cpus", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query balloon device status for a domain via QMP.")
async def qmp_query_balloon(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_balloon", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query block device information for a domain via QMP.")
async def qmp_query_block(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_block", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query block device statistics for a domain via QMP.")
async def qmp_query_blockstats(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_blockstats", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query PCI device information for a domain via QMP.")
async def qmp_query_pci(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_pci", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query IOThread configuration for a domain via QMP.")
async def qmp_query_iothreads(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_iothreads", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query character device configuration for a domain via QMP.")
async def qmp_query_chardev(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_chardev", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query VNC server configuration for a domain via QMP.")
async def qmp_query_vnc(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_vnc", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query active block jobs for a domain via QMP.")
async def qmp_query_block_jobs(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_block_jobs", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Query available machine types via QMP.")
async def qmp_query_machines(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_query_machines", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref})
    return _render(result)


# ---------------------------------------------------------------------------
# QMP mutation tools
# ---------------------------------------------------------------------------


@app.tool(description="Set balloon memory target for a domain via QMP. Requires allow_mutations=true.")
async def qmp_balloon(domain_ref: str, balloon_mb: int, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_balloon", {"domain_ref": domain_ref, "balloon_mb": balloon_mb, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Start a block stream (image pull) for a domain disk via QMP. Requires allow_mutations=true.")
async def qmp_block_stream(domain_ref: str, device: str, base: str | None = None, speed: int = 0, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_block_stream", {"domain_ref": domain_ref, "device": device, "base": base, "speed": speed, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Cancel a running block job for a domain disk via QMP. Requires allow_mutations=true.")
async def qmp_block_job_cancel(domain_ref: str, device: str, force: bool = False, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_block_job_cancel", {"domain_ref": domain_ref, "device": device, "force": force, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Pause a running block job for a domain disk via QMP. Requires allow_mutations=true.")
async def qmp_block_job_pause(domain_ref: str, device: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_block_job_pause", {"domain_ref": domain_ref, "device": device, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Resume a paused block job for a domain disk via QMP. Requires allow_mutations=true.")
async def qmp_block_job_resume(domain_ref: str, device: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_block_job_resume", {"domain_ref": domain_ref, "device": device, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Complete (finalize) a block job for a domain disk via QMP. Requires allow_mutations=true.")
async def qmp_block_job_complete(domain_ref: str, device: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_block_job_complete", {"domain_ref": domain_ref, "device": device, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Hot-add a device to a running domain via QMP. Requires allow_mutations=true.")
async def qmp_device_add(domain_ref: str, driver: str, device_id: str, device_opts: dict | None = None, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_device_add", {"domain_ref": domain_ref, "driver": driver, "device_id": device_id, "device_opts": device_opts or {}, "hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Hot-remove a device from a running domain via QMP. Requires allow_mutations=true.")
async def qmp_device_del(domain_ref: str, device_id: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("qmp_device_del", {"domain_ref": domain_ref, "device_id": device_id, "hypervisor_ref": hypervisor_ref})
    return _render(result)
    return _render(result)


# ---------------------------------------------------------------------------
# Node devices
# ---------------------------------------------------------------------------


@app.tool(description="List host node devices (PCI, USB, etc). Optionally filter by capability.")
async def list_node_devices(capability: str | None = None, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "list_node_devices", {"capability": capability, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Return details for a single host node device.")
async def get_node_device(device_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_node_device", {"device_name": device_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Detach a host node device from the host driver. Requires allow_mutations=true.")
async def detach_node_device(device_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "detach_node_device", {"device_name": device_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Reattach a host node device to the host driver. Requires allow_mutations=true.")
async def reattach_node_device(device_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "reattach_node_device", {"device_name": device_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Host network interfaces
# ---------------------------------------------------------------------------


@app.tool(description="List all host network interfaces.")
async def list_interfaces(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("list_interfaces", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Return details for a single host network interface.")
async def get_interface(iface_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_interface", {"iface_name": iface_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Define a host network interface from XML. Restricted to test-prefixed names.")
async def define_interface_xml(interface_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_interface_xml", {"interface_xml": interface_xml, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Start a host network interface. Restricted to test-prefixed names.")
async def start_interface(iface_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "start_interface", {"iface_name": iface_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Stop a host network interface. Restricted to test-prefixed names.")
async def stop_interface(iface_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "stop_interface", {"iface_name": iface_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Undefine a host network interface. Restricted to test-prefixed names.")
async def undefine_interface(iface_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_interface", {"iface_name": iface_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Network filters
# ---------------------------------------------------------------------------


@app.tool(description="List all network filters (nwfilters).")
async def list_nwfilters(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool("list_nwfilters", {"hypervisor_ref": hypervisor_ref})
    return _render(result)


@app.tool(description="Return details for a single network filter.")
async def get_nwfilter(filter_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_nwfilter", {"filter_name": filter_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Define a network filter from XML. Restricted to test-prefixed names.")
async def define_nwfilter_xml(filter_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_nwfilter_xml", {"filter_xml": filter_xml, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Undefine a network filter. Restricted to test-prefixed names.")
async def undefine_nwfilter(filter_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_nwfilter", {"filter_name": filter_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Network DHCP leases and autostart
# ---------------------------------------------------------------------------


@app.tool(description="Return DHCP leases for a virtual network.")
async def get_network_dhcp_leases(network_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_network_dhcp_leases", {"network_name": network_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Enable or disable autostart for a virtual network. Restricted to test-prefixed names.")
async def set_network_autostart(network_name: str, autostart: bool, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "set_network_autostart",
        {"network_name": network_name, "autostart": autostart, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Block jobs
# ---------------------------------------------------------------------------


@app.tool(description="Start a block pull operation for a domain disk. Requires allow_mutations=true.")
async def block_pull(
    domain_ref: str, disk: str, bandwidth: int = 0, hypervisor_ref: str | None = None
) -> str:
    result = await _get_server().call_tool(
        "block_pull",
        {"domain_ref": domain_ref, "disk": disk, "bandwidth": bandwidth, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Start a block commit operation for a domain disk. Requires allow_mutations=true.")
async def block_commit(
    domain_ref: str,
    disk: str,
    base: str | None = None,
    top: str | None = None,
    bandwidth: int = 0,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "block_commit",
        {
            "domain_ref": domain_ref,
            "disk": disk,
            "base": base,
            "top": top,
            "bandwidth": bandwidth,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Abort an in-progress block job for a domain disk. Requires allow_mutations=true.")
async def block_job_abort(domain_ref: str, disk: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "block_job_abort",
        {"domain_ref": domain_ref, "disk": disk, "bandwidth": 0, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Return block job status for a domain disk.")
async def block_job_info(domain_ref: str, disk: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "block_job_info",
        {"domain_ref": domain_ref, "disk": disk, "bandwidth": 0, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


@app.tool(description="List all checkpoints for a domain.")
async def list_domain_checkpoints(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "list_domain_checkpoints", {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


@app.tool(description="Create a checkpoint for a domain from checkpoint XML. Requires allow_mutations=true.")
async def create_domain_checkpoint(domain_ref: str, checkpoint_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "create_domain_checkpoint",
        {"domain_ref": domain_ref, "checkpoint_xml": checkpoint_xml, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Delete a domain checkpoint. Requires allow_mutations=true.")
async def delete_domain_checkpoint(domain_ref: str, checkpoint_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "delete_domain_checkpoint",
        {"domain_ref": domain_ref, "checkpoint_name": checkpoint_name, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Storage volume clone and pool management
# ---------------------------------------------------------------------------


@app.tool(description="Clone a storage volume. Restricted to test-prefixed destination volume name.")
async def clone_storage_volume(
    pool_name: str,
    volume_name: str,
    src_pool_name: str,
    src_volume_name: str,
    volume_xml: str,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "clone_storage_volume",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "src_pool_name": src_pool_name,
            "src_volume_name": src_volume_name,
            "volume_xml": volume_xml,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Enable or disable autostart for a storage pool. Restricted to test-prefixed names.")
async def set_storage_pool_autostart(pool_name: str, autostart: bool, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "set_storage_pool_autostart",
        {"pool_name": pool_name, "autostart": autostart, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Refresh a storage pool to sync its volume list. Requires allow_mutations=true.")
async def refresh_storage_pool(pool_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "refresh_storage_pool", {"pool_name": pool_name, "hypervisor_ref": hypervisor_ref}
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Domain capabilities
# ---------------------------------------------------------------------------


@app.tool(description="Return domain capabilities XML and summary for the given emulator/arch/machine.")
async def get_domain_capabilities(
    emulatorbin: str | None = None,
    arch: str | None = None,
    machine: str | None = None,
    virttype: str | None = None,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "get_domain_capabilities",
        {
            "emulatorbin": emulatorbin,
            "arch": arch,
            "machine": machine,
            "virttype": virttype,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Domain vCPU and memory tuning
# ---------------------------------------------------------------------------


@app.tool(description="Set vCPU count for a domain. Requires allow_mutations=true.")
async def set_domain_vcpus(
    domain_ref: str,
    vcpu_count: int,
    live: bool = True,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "set_domain_vcpus",
        {
            "domain_ref": domain_ref,
            "vcpu_count": vcpu_count,
            "live": live,
            "persistent": persistent,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Set memory (in KiB) for a domain. Requires allow_mutations=true.")
async def set_domain_memory(
    domain_ref: str,
    memory_kb: int,
    live: bool = True,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "set_domain_memory",
        {
            "domain_ref": domain_ref,
            "memory_kb": memory_kb,
            "live": live,
            "persistent": persistent,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Return configured guest NUMA topology for a domain.")
async def get_domain_numa_topology(domain_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_domain_numa_topology",
        {"domain_ref": domain_ref, "hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Set persistent guest NUMA topology for a test-prefixed domain.")
async def set_domain_numa_topology(
    domain_ref: str,
    cells: list[dict[str, int | str]],
    live: bool = False,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "set_domain_numa_topology",
        {
            "domain_ref": domain_ref,
            "cells": cells,
            "live": live,
            "persistent": persistent,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Domain definition management
# ---------------------------------------------------------------------------


@app.tool(description="Validate domain XML structure and libvirt schema compatibility.")
async def validate_domain_xml(domain_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "validate_domain_xml",
        {
            "domain_xml": domain_xml,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Update a domain device XML definition. Requires allow_mutations=true.")
async def update_domain_device_xml(
    domain_ref: str,
    device_xml: str,
    live: bool = True,
    persistent: bool = True,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "update_domain_device_xml",
        {
            "domain_ref": domain_ref,
            "device_xml": device_xml,
            "live": live,
            "persistent": persistent,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Volume inspection
# ---------------------------------------------------------------------------


@app.tool(description="Return volume XML for a storage volume.")
async def get_volume_xml(pool_name: str, volume_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_volume_xml",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Return the backing chain for a storage volume.")
async def get_volume_backing_chain(pool_name: str, volume_name: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_volume_backing_chain",
        {
            "pool_name": pool_name,
            "volume_name": volume_name,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


# ---------------------------------------------------------------------------
# Audit and QMP policy
# ---------------------------------------------------------------------------


@app.tool(description="Query operation audit log entries with optional filters.")
async def get_audit_log(
    limit: int = 100,
    tool_name: str | None = None,
    result_filter: str | None = None,
    since: str | None = None,
    hypervisor_ref: str | None = None,
) -> str:
    result = await _get_server().call_tool(
        "get_audit_log",
        {
            "limit": limit,
            "tool_name": tool_name,
            "result_filter": result_filter,
            "since": since,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Return QMP policy toggles and allowlists.")
async def get_qmp_policy() -> str:
    result = await _get_server().call_tool("get_qmp_policy", {})
    return _render(result)


# ---------------------------------------------------------------------------
# Secret lifecycle
# ---------------------------------------------------------------------------


@app.tool(description="List all libvirt secrets.")
async def list_secrets(hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "list_secrets",
        {"hypervisor_ref": hypervisor_ref},
    )
    return _render(result)


@app.tool(description="Return details for a single libvirt secret.")
async def get_secret(secret_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_secret",
        {
            "secret_ref": secret_ref,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Define a libvirt secret from XML. Requires allow_define=true.")
async def define_secret_xml(secret_xml: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "define_secret_xml",
        {
            "secret_xml": secret_xml,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Set a libvirt secret value (base64-encoded). Requires allow_mutations=true.")
async def set_secret_value(secret_ref: str, value_b64: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "set_secret_value",
        {
            "secret_ref": secret_ref,
            "value_b64": value_b64,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Get a libvirt secret value (base64-encoded). Requires allow_secret_read=true.")
async def get_secret_value(secret_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "get_secret_value",
        {
            "secret_ref": secret_ref,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)


@app.tool(description="Undefine a libvirt secret. Requires allow_mutations=true.")
async def undefine_secret(secret_ref: str, hypervisor_ref: str | None = None) -> str:
    result = await _get_server().call_tool(
        "undefine_secret",
        {
            "secret_ref": secret_ref,
            "hypervisor_ref": hypervisor_ref,
        },
    )
    return _render(result)
