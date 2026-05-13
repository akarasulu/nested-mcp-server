"""Server core with MCP-style tool dispatch and audit logging."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from libvirt_mcp_server.adapters.libvirt_adapter import LibvirtAdapter
from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError, error_envelope
from libvirt_mcp_server.schemas import (
    BlockCommitInput,
    BlockJobInput,
    CheckpointRefInput,
    CreateCheckpointInput,
    CreateSnapshotInput,
    DomainCapabilitiesInput,
    DomainDefineInput,
    DomainDiskRefInput,
    DomainInterfaceRefInput,
    DomainNumaTopologyInput,
    DomainRefInput,
    DomainXmlInput,
    InterfaceDefineInput,
    InterfaceRefInput,
    LifecycleInput,
    ListDomainsInput,
    ListNodeDevicesInput,
    NetworkRefInput,
    NodeDeviceRefInput,
    NWFilterDefineInput,
    NWFilterRefInput,
    QmpBalloonInput,
    QmpBitmapAddInput,
    QmpBitmapInput,
    QmpBlockJobCancelInput,
    QmpBlockJobDeviceInput,
    QmpBlockStreamInput,
    QmpChardevAddInput,
    QmpChardevRemoveInput,
    QmpCommandInput,
    QmpCpuAddInput,
    QmpDeviceAddInput,
    QmpDeviceDelInput,
    QmpDriveMirrorInput,
    QmpEventsInput,
    QmpNetdevAddInput,
    QmpNetdevDelInput,
    QmpObjectAddInput,
    QmpObjectDelInput,
    SetAutostartInput,
    SetEmulatorPinInput,
    SetMemoryInput,
    SetNetworkAutostartInput,
    SetStoragePoolAutostartInput,
    SetVcpuPinInput,
    SetVcpusInput,
    SnapshotRefInput,
    StoragePoolRefInput,
    StoragePoolDefineInput,
    StorageLinkedCloneCreateInput,
    StorageVolumeCloneInput,
    StorageVolumeCreateInput,
    StorageVolumeDownloadInput,
    StorageVolumeRefInput,
    StorageVolumeResizeInput,
    StorageVolumeUploadInput,
    NetworkDefineInput,
)
from libvirt_mcp_server.schemas import (
    AuditLogQueryInput,
    DomainUpdateDeviceInput,
    DomainValidateInput,
    SecretDefineInput,
    SecretRefInput,
    SecretSetValueInput,
)
from libvirt_mcp_server.tools import (
    block_job_tools,
    checkpoint_tools,
    domain_tools,
    host_tools,
    network_tools,
    node_device_tools,
    qmp_tools,
    snapshot_tools,
    storage_tools,
    secret_tools,
)


class LibvirtMCPServer:
    """In-process MCP-compatible server core.

    This class can be mounted into an MCP transport implementation.
    """

    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig.from_env()
        self.libvirt_adapter = LibvirtAdapter()
        _effective_qmp_allowlist = self.config.qmp_allowlist.copy()
        if self.config.allow_mutations:
            _effective_qmp_allowlist |= self.config.qmp_mutation_allowlist
        self.qmp_adapter = QMPAdapter(
            socket_dir=self.config.qmp_socket_dir,
            allowlist=_effective_qmp_allowlist,
            enabled=self.config.allow_qmp,
        )
        self._audit_path = Path(self.config.audit_log_path)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    def list_tools(self) -> list[str]:
        return [
            "host_info",
            "get_host_numa_topology",
            "list_hypervisors",
            "get_hypervisor",
            "list_domains",
            "get_domain",
            "get_domain_xml",
            "define_domain_xml",
            "undefine_domain",
            "set_domain_autostart",
            "start_domain",
            "shutdown_domain",
            "destroy_domain",
            "reboot_domain",
            "suspend_domain",
            "resume_domain",
            "list_networks",
            "get_network",
            "define_network_xml",
            "start_network",
            "destroy_network",
            "undefine_network",
            "list_storage_pools",
            "get_storage_pool",
            "get_storage_pool_xml",
            "get_storage_pool_metadata",
            "list_storage_volumes",
            "get_storage_volume",
            "get_storage_volume_metadata",
            "define_storage_pool_xml",
            "start_storage_pool",
            "destroy_storage_pool",
            "undefine_storage_pool",
            "create_storage_volume_xml",
            "create_linked_clone_volume",
            "upload_storage_volume",
            "download_storage_volume",
            "delete_storage_volume",
            "list_domain_snapshots",
            "create_domain_snapshot",
            "revert_domain_snapshot",
            "delete_domain_snapshot",
            "qmp_command",
            "qmp_capabilities",
            "qmp_events",
            # Typed QMP query tools
            "qmp_query_status",
            "qmp_query_version",
            "qmp_query_cpus",
            "qmp_query_balloon",
            "qmp_query_block",
            "qmp_query_blockstats",
            "qmp_query_pci",
            "qmp_query_iothreads",
            "qmp_query_chardev",
            "qmp_query_vnc",
            "qmp_query_block_jobs",
            "qmp_query_machines",
            # QMP mutation tools
            "qmp_balloon",
            "qmp_block_stream",
            "qmp_block_job_cancel",
            "qmp_block_job_pause",
            "qmp_block_job_resume",
            "qmp_block_job_complete",
            "qmp_device_add",
            "qmp_device_del",
            # Node devices
            "list_node_devices",
            "get_node_device",
            "detach_node_device",
            "reattach_node_device",
            # Host network interfaces
            "list_interfaces",
            "get_interface",
            "define_interface_xml",
            "start_interface",
            "stop_interface",
            "undefine_interface",
            # Network filters
            "list_nwfilters",
            "get_nwfilter",
            "define_nwfilter_xml",
            "undefine_nwfilter",
            # Network DHCP leases
            "get_network_dhcp_leases",
            # Network autostart
            "set_network_autostart",
            # Block jobs
            "block_pull",
            "block_commit",
            "block_job_abort",
            "block_job_info",
            # Checkpoints
            "list_domain_checkpoints",
            "create_domain_checkpoint",
            "delete_domain_checkpoint",
            # Storage volume clone
            "clone_storage_volume",
            # Storage pool autostart and refresh
            "set_storage_pool_autostart",
            "refresh_storage_pool",
            # Domain capabilities
            "get_domain_capabilities",
            # Domain vCPU and memory tuning
            "set_domain_vcpus",
            "set_domain_memory",
            "get_domain_numa_topology",
            "set_domain_numa_topology",
            # Domain statistics
            "get_domain_stats",
            "get_domain_block_stats",
            "get_domain_interface_stats",
            "get_domain_memory_stats",
            # CPU pinning
            "get_domain_vcpu_pin_info",
            "set_domain_vcpu_pin",
            "get_domain_emulator_pin_info",
            "set_domain_emulator_pin",
            # Storage volume resize and wipe
            "resize_storage_volume",
            "wipe_storage_volume",
            # Storage pool build
            "build_storage_pool",
            # QMP new families
            "qmp_query_hotpluggable_cpus",
            "qmp_query_memory_devices",
            "qmp_query_block_dirty_bitmaps",
            "qmp_query_migrate",
            "qmp_query_migrate_capabilities",
            "qmp_query_migrate_parameters",
            "qmp_cpu_add",
            "qmp_object_add",
            "qmp_object_del",
            "qmp_drive_mirror",
            "qmp_block_dirty_bitmap_add",
            "qmp_block_dirty_bitmap_remove",
            "qmp_block_dirty_bitmap_clear",
            "qmp_netdev_add",
            "qmp_netdev_del",
            "qmp_chardev_add",
            "qmp_chardev_remove",
            # Domain definition management
            "validate_domain_xml",
            "update_domain_device_xml",
            # Volume inspection
            "get_volume_xml",
            "get_volume_backing_chain",
            # Audit and policy
            "get_audit_log",
            "get_qmp_policy",
            # Secrets lifecycle
            "list_secrets",
            "get_secret",
            "define_secret_xml",
            "set_secret_value",
            "get_secret_value",
            "undefine_secret",
        ]


    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None, *, actor: str = "unknown") -> dict[str, Any]:
        args = arguments or {}
        request_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        try:
            if tool_name == "host_info":
                result = host_tools.host_info(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "get_host_numa_topology":
                result = host_tools.get_host_numa_topology(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "list_hypervisors":
                result = host_tools.list_hypervisors(self.config)
            elif tool_name == "get_hypervisor":
                hypervisor_ref = str(args["hypervisor_ref"])
                result = host_tools.get_hypervisor(self.config, hypervisor_ref)
            elif tool_name == "list_domains":
                data = ListDomainsInput.model_validate(args)
                result = domain_tools.list_domains(
                    self.config,
                    self.libvirt_adapter,
                    active_only=data.active_only,
                    inactive_only=data.inactive_only,
                    name_prefix=data.name_prefix,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_xml":
                data = DomainXmlInput.model_validate(args)
                result = domain_tools.get_domain_xml(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                    live=data.live,
                    inactive=data.inactive,
                )
            elif tool_name == "define_domain_xml":
                data = DomainDefineInput.model_validate(args)
                result = domain_tools.define_domain_xml(
                    self.config,
                    self.libvirt_adapter,
                    domain_xml=data.domain_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_domain":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.undefine_domain(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_domain_autostart":
                data = SetAutostartInput.model_validate(args)
                result = domain_tools.set_domain_autostart(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                    autostart=data.autostart,
                )
            elif tool_name in domain_tools.LIFECYCLE_TOOLS:
                data = LifecycleInput.model_validate(args)
                result = domain_tools.lifecycle_action(
                    self.config,
                    self.libvirt_adapter,
                    tool_name=tool_name,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                    dry_run=data.dry_run,
                )
            elif tool_name == "list_networks":
                result = network_tools.list_networks(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "get_network":
                data = NetworkRefInput.model_validate(args)
                result = network_tools.get_network(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "define_network_xml":
                data = NetworkDefineInput.model_validate(args)
                result = network_tools.define_network_xml(
                    self.config,
                    self.libvirt_adapter,
                    network_xml=data.network_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "start_network":
                data = NetworkRefInput.model_validate(args)
                result = network_tools.start_network(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "destroy_network":
                data = NetworkRefInput.model_validate(args)
                result = network_tools.destroy_network(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_network":
                data = NetworkRefInput.model_validate(args)
                result = network_tools.undefine_network(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "list_storage_pools":
                result = storage_tools.list_storage_pools(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "get_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.get_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_storage_pool_xml":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.get_storage_pool_xml(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_storage_pool_metadata":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.get_storage_pool_metadata(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "list_storage_volumes":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.list_storage_volumes(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_storage_volume":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.get_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_storage_volume_metadata":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.get_storage_volume_metadata(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "define_storage_pool_xml":
                data = StoragePoolDefineInput.model_validate(args)
                result = storage_tools.define_storage_pool_xml(
                    self.config,
                    self.libvirt_adapter,
                    pool_xml=data.pool_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "start_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.start_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "destroy_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.destroy_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.undefine_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "create_storage_volume_xml":
                data = StorageVolumeCreateInput.model_validate(args)
                result = storage_tools.create_storage_volume_xml(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_xml=data.volume_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "create_linked_clone_volume":
                data = StorageLinkedCloneCreateInput.model_validate(args)
                result = storage_tools.create_linked_clone_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    backing_file=data.backing_file,
                    capacity_bytes=data.capacity_bytes,
                    format=data.format,
                    backing_format=data.backing_format,
                    relative_backing=data.relative_backing,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "upload_storage_volume":
                data = StorageVolumeUploadInput.model_validate(args)
                result = storage_tools.upload_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    source_path=data.source_path,
                    offset=data.offset,
                    length=data.length,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "download_storage_volume":
                data = StorageVolumeDownloadInput.model_validate(args)
                result = storage_tools.download_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    target_path=data.target_path,
                    offset=data.offset,
                    length=data.length,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "delete_storage_volume":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.delete_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "list_domain_snapshots":
                data = DomainRefInput.model_validate(args)
                result = snapshot_tools.list_domain_snapshots(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "create_domain_snapshot":
                data = CreateSnapshotInput.model_validate(args)
                result = snapshot_tools.create_domain_snapshot(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    snapshot_xml=data.snapshot_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "revert_domain_snapshot":
                data = SnapshotRefInput.model_validate(args)
                result = snapshot_tools.revert_domain_snapshot(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    snapshot_name=data.snapshot_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "delete_domain_snapshot":
                data = SnapshotRefInput.model_validate(args)
                result = snapshot_tools.delete_domain_snapshot(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    snapshot_name=data.snapshot_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_command":
                data = QmpCommandInput.model_validate(args)
                result = await qmp_tools.qmp_command(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    command=data.command,
                    arguments=data.arguments,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_capabilities":
                data = DomainRefInput.model_validate(args)
                result = await qmp_tools.qmp_capabilities(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_events":
                data = QmpEventsInput.model_validate(args)
                result = await qmp_tools.qmp_events(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    event_types=data.event_types,
                    since=data.since,
                    timeout_seconds=data.timeout_seconds,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name in {
                "qmp_query_status", "qmp_query_version", "qmp_query_cpus", "qmp_query_balloon",
                "qmp_query_block", "qmp_query_blockstats", "qmp_query_pci", "qmp_query_iothreads",
                "qmp_query_chardev", "qmp_query_vnc", "qmp_query_block_jobs", "qmp_query_machines",
                "qmp_query_hotpluggable_cpus", "qmp_query_memory_devices",
                "qmp_query_block_dirty_bitmaps",
                "qmp_query_migrate", "qmp_query_migrate_capabilities", "qmp_query_migrate_parameters",
            }:
                data = DomainRefInput.model_validate(args)
                fn = getattr(qmp_tools, tool_name)
                result = await fn(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_balloon":
                data = QmpBalloonInput.model_validate(args)
                result = await qmp_tools.qmp_balloon(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    balloon_mb=data.balloon_mb,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_stream":
                data = QmpBlockStreamInput.model_validate(args)
                result = await qmp_tools.qmp_block_stream(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    base=data.base,
                    speed=data.speed,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_job_cancel":
                data = QmpBlockJobCancelInput.model_validate(args)
                result = await qmp_tools.qmp_block_job_cancel(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    force=data.force,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_job_pause":
                data = QmpBlockJobDeviceInput.model_validate(args)
                result = await qmp_tools.qmp_block_job_pause(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_job_resume":
                data = QmpBlockJobDeviceInput.model_validate(args)
                result = await qmp_tools.qmp_block_job_resume(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_job_complete":
                data = QmpBlockJobDeviceInput.model_validate(args)
                result = await qmp_tools.qmp_block_job_complete(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_device_add":
                data = QmpDeviceAddInput.model_validate(args)
                result = await qmp_tools.qmp_device_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    driver=data.driver,
                    device_id=data.device_id,
                    device_opts=data.device_opts,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_device_del":
                data = QmpDeviceDelInput.model_validate(args)
                result = await qmp_tools.qmp_device_del(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device_id=data.device_id,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_cpu_add":
                data = QmpCpuAddInput.model_validate(args)
                result = await qmp_tools.qmp_cpu_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    cpu_index=data.cpu_index,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_object_add":
                data = QmpObjectAddInput.model_validate(args)
                result = await qmp_tools.qmp_object_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    qom_type=data.qom_type,
                    obj_id=data.obj_id,
                    props=data.props,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_object_del":
                data = QmpObjectDelInput.model_validate(args)
                result = await qmp_tools.qmp_object_del(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    obj_id=data.obj_id,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_drive_mirror":
                data = QmpDriveMirrorInput.model_validate(args)
                result = await qmp_tools.qmp_drive_mirror(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    device=data.device,
                    target=data.target,
                    format=data.format,
                    sync=data.sync,
                    speed=data.speed,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_block_dirty_bitmap_add":
                data = QmpBitmapAddInput.model_validate(args)
                result = await qmp_tools.qmp_block_dirty_bitmap_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    node=data.node,
                    name=data.name,
                    persistent=data.persistent,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name in {"qmp_block_dirty_bitmap_remove", "qmp_block_dirty_bitmap_clear"}:
                data = QmpBitmapInput.model_validate(args)
                fn = getattr(qmp_tools, tool_name)
                result = await fn(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    node=data.node,
                    name=data.name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_netdev_add":
                data = QmpNetdevAddInput.model_validate(args)
                result = await qmp_tools.qmp_netdev_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    netdev_type=data.netdev_type,
                    netdev_id=data.netdev_id,
                    netdev_opts=data.netdev_opts,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_netdev_del":
                data = QmpNetdevDelInput.model_validate(args)
                result = await qmp_tools.qmp_netdev_del(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    netdev_id=data.netdev_id,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_chardev_add":
                data = QmpChardevAddInput.model_validate(args)
                result = await qmp_tools.qmp_chardev_add(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    chardev_id=data.chardev_id,
                    backend=data.backend,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "qmp_chardev_remove":
                data = QmpChardevRemoveInput.model_validate(args)
                result = await qmp_tools.qmp_chardev_remove(
                    self.config,
                    self.qmp_adapter,
                    domain_ref=data.domain_ref,
                    chardev_id=data.chardev_id,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Node devices
            # ------------------------------------------------------------------
            elif tool_name == "list_node_devices":
                data = ListNodeDevicesInput.model_validate(args)
                result = node_device_tools.list_node_devices(
                    self.config,
                    self.libvirt_adapter,
                    capability=data.capability,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_node_device":
                data = NodeDeviceRefInput.model_validate(args)
                result = node_device_tools.get_node_device(
                    self.config,
                    self.libvirt_adapter,
                    device_name=data.device_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "detach_node_device":
                data = NodeDeviceRefInput.model_validate(args)
                result = node_device_tools.detach_node_device(
                    self.config,
                    self.libvirt_adapter,
                    device_name=data.device_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "reattach_node_device":
                data = NodeDeviceRefInput.model_validate(args)
                result = node_device_tools.reattach_node_device(
                    self.config,
                    self.libvirt_adapter,
                    device_name=data.device_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Host network interfaces
            # ------------------------------------------------------------------
            elif tool_name == "list_interfaces":
                result = network_tools.list_interfaces(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "get_interface":
                data = InterfaceRefInput.model_validate(args)
                result = network_tools.get_interface(
                    self.config,
                    self.libvirt_adapter,
                    iface_name=data.iface_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "define_interface_xml":
                data = InterfaceDefineInput.model_validate(args)
                result = network_tools.define_interface_xml(
                    self.config,
                    self.libvirt_adapter,
                    interface_xml=data.interface_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "start_interface":
                data = InterfaceRefInput.model_validate(args)
                result = network_tools.start_interface(
                    self.config,
                    self.libvirt_adapter,
                    iface_name=data.iface_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "stop_interface":
                data = InterfaceRefInput.model_validate(args)
                result = network_tools.stop_interface(
                    self.config,
                    self.libvirt_adapter,
                    iface_name=data.iface_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_interface":
                data = InterfaceRefInput.model_validate(args)
                result = network_tools.undefine_interface(
                    self.config,
                    self.libvirt_adapter,
                    iface_name=data.iface_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Network filters
            # ------------------------------------------------------------------
            elif tool_name == "list_nwfilters":
                result = network_tools.list_nwfilters(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=args.get("hypervisor_ref"),
                )
            elif tool_name == "get_nwfilter":
                data = NWFilterRefInput.model_validate(args)
                result = network_tools.get_nwfilter(
                    self.config,
                    self.libvirt_adapter,
                    filter_name=data.filter_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "define_nwfilter_xml":
                data = NWFilterDefineInput.model_validate(args)
                result = network_tools.define_nwfilter_xml(
                    self.config,
                    self.libvirt_adapter,
                    filter_xml=data.filter_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_nwfilter":
                data = NWFilterRefInput.model_validate(args)
                result = network_tools.undefine_nwfilter(
                    self.config,
                    self.libvirt_adapter,
                    filter_name=data.filter_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Network DHCP leases
            # ------------------------------------------------------------------
            elif tool_name == "get_network_dhcp_leases":
                data = NetworkRefInput.model_validate(args)
                result = network_tools.get_network_dhcp_leases(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Network autostart
            # ------------------------------------------------------------------
            elif tool_name == "set_network_autostart":
                data = SetNetworkAutostartInput.model_validate(args)
                result = network_tools.set_network_autostart(
                    self.config,
                    self.libvirt_adapter,
                    network_name=data.network_name,
                    autostart=data.autostart,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Block jobs
            # ------------------------------------------------------------------
            elif tool_name == "block_pull":
                data = BlockJobInput.model_validate(args)
                result = block_job_tools.block_pull(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    disk=data.disk,
                    bandwidth=data.bandwidth,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "block_commit":
                data = BlockCommitInput.model_validate(args)
                result = block_job_tools.block_commit(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    disk=data.disk,
                    base=data.base,
                    top=data.top,
                    bandwidth=data.bandwidth,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "block_job_abort":
                data = BlockJobInput.model_validate(args)
                result = block_job_tools.block_job_abort(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    disk=data.disk,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "block_job_info":
                data = BlockJobInput.model_validate(args)
                result = block_job_tools.block_job_info(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    disk=data.disk,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Checkpoints
            # ------------------------------------------------------------------
            elif tool_name == "list_domain_checkpoints":
                data = DomainRefInput.model_validate(args)
                result = checkpoint_tools.list_domain_checkpoints(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "create_domain_checkpoint":
                data = CreateCheckpointInput.model_validate(args)
                result = checkpoint_tools.create_domain_checkpoint(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    checkpoint_xml=data.checkpoint_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "delete_domain_checkpoint":
                data = CheckpointRefInput.model_validate(args)
                result = checkpoint_tools.delete_domain_checkpoint(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    checkpoint_name=data.checkpoint_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Storage volume clone
            # ------------------------------------------------------------------
            elif tool_name == "clone_storage_volume":
                data = StorageVolumeCloneInput.model_validate(args)
                result = storage_tools.clone_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    src_pool_name=data.src_pool_name,
                    src_volume_name=data.src_volume_name,
                    volume_xml=data.volume_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Storage pool autostart and refresh
            # ------------------------------------------------------------------
            elif tool_name == "set_storage_pool_autostart":
                data = SetStoragePoolAutostartInput.model_validate(args)
                result = storage_tools.set_storage_pool_autostart(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    autostart=data.autostart,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "refresh_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.refresh_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Domain capabilities
            # ------------------------------------------------------------------
            elif tool_name == "get_domain_capabilities":
                data = DomainCapabilitiesInput.model_validate(args)
                result = host_tools.get_domain_capabilities(
                    self.config,
                    self.libvirt_adapter,
                    emulatorbin=data.emulatorbin,
                    arch=data.arch,
                    machine=data.machine,
                    virttype=data.virttype,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Domain vCPU and memory tuning
            # ------------------------------------------------------------------
            elif tool_name == "set_domain_vcpus":
                data = SetVcpusInput.model_validate(args)
                result = domain_tools.set_domain_vcpus(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    vcpu_count=data.vcpu_count,
                    live=data.live,
                    persistent=data.persistent,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_domain_memory":
                data = SetMemoryInput.model_validate(args)
                result = domain_tools.set_domain_memory(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    memory_kb=data.memory_kb,
                    live=data.live,
                    persistent=data.persistent,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_numa_topology":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain_numa_topology(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_domain_numa_topology":
                data = DomainNumaTopologyInput.model_validate(args)
                result = domain_tools.set_domain_numa_topology(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    cells=[cell.model_dump() for cell in data.cells],
                    live=data.live,
                    persistent=data.persistent,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Domain statistics
            # ------------------------------------------------------------------
            elif tool_name == "get_domain_stats":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain_stats(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_block_stats":
                data = DomainDiskRefInput.model_validate(args)
                result = domain_tools.get_domain_block_stats(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    disk=data.disk,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_interface_stats":
                data = DomainInterfaceRefInput.model_validate(args)
                result = domain_tools.get_domain_interface_stats(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    interface=data.interface,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_memory_stats":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain_memory_stats(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # CPU pinning
            # ------------------------------------------------------------------
            elif tool_name == "get_domain_vcpu_pin_info":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain_vcpu_pin_info(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_domain_vcpu_pin":
                data = SetVcpuPinInput.model_validate(args)
                result = domain_tools.set_domain_vcpu_pin(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    vcpu=data.vcpu,
                    cpumap=data.cpumap,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_domain_emulator_pin_info":
                data = DomainRefInput.model_validate(args)
                result = domain_tools.get_domain_emulator_pin_info(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_domain_emulator_pin":
                data = SetEmulatorPinInput.model_validate(args)
                result = domain_tools.set_domain_emulator_pin(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    cpumap=data.cpumap,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Storage volume resize and wipe
            # ------------------------------------------------------------------
            elif tool_name == "resize_storage_volume":
                data = StorageVolumeResizeInput.model_validate(args)
                result = storage_tools.resize_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    capacity_bytes=data.capacity_bytes,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "wipe_storage_volume":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.wipe_storage_volume(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Storage pool build
            # ------------------------------------------------------------------
            elif tool_name == "build_storage_pool":
                data = StoragePoolRefInput.model_validate(args)
                result = storage_tools.build_storage_pool(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Domain definition management
            # ------------------------------------------------------------------
            elif tool_name == "validate_domain_xml":
                data = DomainValidateInput.model_validate(args)
                result = domain_tools.validate_domain_xml(
                    self.config,
                    self.libvirt_adapter,
                    domain_xml=data.domain_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "update_domain_device_xml":
                data = DomainUpdateDeviceInput.model_validate(args)
                result = domain_tools.update_domain_device_xml(
                    self.config,
                    self.libvirt_adapter,
                    domain_ref=data.domain_ref,
                    device_xml=data.device_xml,
                    live=data.live,
                    persistent=data.persistent,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Volume inspection
            # ------------------------------------------------------------------
            elif tool_name == "get_volume_xml":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.get_volume_xml(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_volume_backing_chain":
                data = StorageVolumeRefInput.model_validate(args)
                result = storage_tools.get_volume_backing_chain(
                    self.config,
                    self.libvirt_adapter,
                    pool_name=data.pool_name,
                    volume_name=data.volume_name,
                    hypervisor_ref=data.hypervisor_ref,
                )
            # ------------------------------------------------------------------
            # Audit log and QMP policy
            # ------------------------------------------------------------------
            elif tool_name == "get_audit_log":
                data = AuditLogQueryInput.model_validate(args)
                result = host_tools.get_audit_log(
                    self.config,
                    str(self._audit_path),
                    limit=data.limit,
                    tool_name=data.tool_name,
                    result_filter=data.result_filter,
                    since=data.since,
                )
            elif tool_name == "get_qmp_policy":
                result = host_tools.get_qmp_policy(self.config)
            # ------------------------------------------------------------------
            # Secrets lifecycle
            # ------------------------------------------------------------------
            elif tool_name == "list_secrets":
                hypervisor_ref = args.get("hypervisor_ref")
                result = secret_tools.list_secrets(
                    self.config,
                    self.libvirt_adapter,
                    hypervisor_ref=hypervisor_ref,
                )
            elif tool_name == "get_secret":
                data = SecretRefInput.model_validate(args)
                result = secret_tools.get_secret(
                    self.config,
                    self.libvirt_adapter,
                    secret_ref=data.secret_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "define_secret_xml":
                data = SecretDefineInput.model_validate(args)
                result = secret_tools.define_secret_xml(
                    self.config,
                    self.libvirt_adapter,
                    secret_xml=data.secret_xml,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "set_secret_value":
                data = SecretSetValueInput.model_validate(args)
                result = secret_tools.set_secret_value(
                    self.config,
                    self.libvirt_adapter,
                    secret_ref=data.secret_ref,
                    value_b64=data.value_b64,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "get_secret_value":
                data = SecretRefInput.model_validate(args)
                result = secret_tools.get_secret_value(
                    self.config,
                    self.libvirt_adapter,
                    secret_ref=data.secret_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            elif tool_name == "undefine_secret":
                data = SecretRefInput.model_validate(args)
                result = secret_tools.undefine_secret(
                    self.config,
                    self.libvirt_adapter,
                    secret_ref=data.secret_ref,
                    hypervisor_ref=data.hypervisor_ref,
                )
            else:
                raise MCPError(code="UNKNOWN_TOOL", message=f"Unknown tool '{tool_name}'")
        except MCPError as exc:
            envelope = exc.to_envelope()
            self._append_audit(
                request_id=request_id,
                actor=actor,
                tool_name=tool_name,
                target_ref=self._target_ref_from_args(args),
                hypervisor_ref=args.get("hypervisor_ref"),
                timestamp=ts,
                result="error",
                error_code=exc.code,
                details=envelope,
            )
            return envelope
        except Exception as exc:
            envelope = error_envelope("INTERNAL_ERROR", str(exc), retryable=False, source="server")
            self._append_audit(
                request_id=request_id,
                actor=actor,
                tool_name=tool_name,
                target_ref=self._target_ref_from_args(args),
                hypervisor_ref=args.get("hypervisor_ref"),
                timestamp=ts,
                result="error",
                error_code="INTERNAL_ERROR",
                details=envelope,
            )
            return envelope

        self._append_audit(
            request_id=request_id,
            actor=actor,
            tool_name=tool_name,
            target_ref=self._target_ref_from_args(args),
            hypervisor_ref=args.get("hypervisor_ref"),
            timestamp=ts,
            result="success",
            error_code=None,
            details=self._success_audit_details(tool_name, args, result),
        )
        return result

    def _target_ref_from_args(self, args: dict[str, Any]) -> str | None:
        for key in (
            "domain_ref",
            "network_name",
            "pool_name",
            "volume_name",
            "snapshot_name",
            "secret_ref",
            "hypervisor_ref",
        ):
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _success_audit_details(self, tool_name: str, args: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        details: dict[str, Any] = {"summary": "ok"}
        if not isinstance(result, dict):
            details["result_type"] = type(result).__name__
            return details
        if tool_name == "set_secret_value":
            details["secret_ref"] = args.get("secret_ref")
            details["value_redacted"] = True
            if isinstance(result.get("status"), str):
                details["status"] = result["status"]
            return details
        if tool_name == "get_secret_value":
            details["secret_ref"] = args.get("secret_ref")
            details["value_redacted"] = True
            if isinstance(result.get("status"), str):
                details["status"] = result["status"]
            return details

        for key in ("domain_ref", "network_name", "pool_name", "volume_name", "snapshot_name", "secret_ref"):
            if key in args:
                details[key] = args[key]
        if tool_name == "create_linked_clone_volume":
            for key in ("pool_name", "volume_name", "backing_file", "relative_backing"):
                if key in args:
                    details[key] = args[key]
        if "status" in result:
            details["status"] = result["status"]
        return details

    def _append_audit(
        self,
        *,
        request_id: str,
        actor: str,
        tool_name: str,
        target_ref: str | None,
        hypervisor_ref: str | None,
        timestamp: str,
        result: str,
        error_code: str | None,
        details: dict[str, Any],
    ) -> None:
        record = {
            "request_id": request_id,
            "actor": actor,
            "timestamp": timestamp,
            "tool_name": tool_name,
            "target_ref": target_ref,
            "hypervisor_ref": hypervisor_ref,
            "result": result,
            "error_code": error_code,
            "details": details,
        }
        with self._audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")


def run_tool_sync(tool_name: str, arguments: dict[str, Any] | None = None, *, actor: str = "cli") -> dict[str, Any]:
    """Helper for environments that invoke tools synchronously."""
    server = LibvirtMCPServer()
    return asyncio.run(server.call_tool(tool_name, arguments, actor=actor))
