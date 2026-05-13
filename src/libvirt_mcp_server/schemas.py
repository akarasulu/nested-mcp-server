"""Strict tool input schemas and shared response shaping models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base schema with unknown field rejection."""

    model_config = ConfigDict(extra="forbid")


class DomainRefInput(StrictModel):
    domain_ref: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class ListDomainsInput(StrictModel):
    active_only: bool = False
    inactive_only: bool = False
    name_prefix: str | None = Field(default=None, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class DomainXmlInput(DomainRefInput):
    live: bool = False
    inactive: bool = True


class SetAutostartInput(DomainRefInput):
    autostart: bool


class LifecycleInput(DomainRefInput):
    dry_run: bool = False


class QmpCommandInput(DomainRefInput):
    command: str = Field(min_length=1, max_length=255)
    arguments: dict[str, Any] = Field(default_factory=dict)


class QmpEventsInput(DomainRefInput):
    event_types: list[str] = Field(default_factory=list)
    since: str | None = Field(default=None, max_length=255)
    timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)


class QmpReplayEventsInput(StrictModel):
    domain_ref: str | None = Field(default=None, max_length=255)
    event_types: list[str] = Field(default_factory=list)
    since: str | None = Field(default=None, max_length=255)
    limit: int = Field(default=100, ge=1, le=10000)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class QmpPruneEventsInput(StrictModel):
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    max_records: int | None = Field(default=None, ge=1, le=10000000)
    dry_run: bool = False
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class QmpCollectEventsLoopInput(StrictModel):
    domain_refs: list[str] = Field(min_length=1)
    event_types: list[str] = Field(default_factory=list)
    iterations: int = Field(default=1, ge=1, le=1000)
    interval_seconds: float = Field(default=1.0, ge=0.0, le=3600.0)
    timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class NetworkRefInput(StrictModel):
    network_name: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class StoragePoolRefInput(StrictModel):
    pool_name: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class StorageVolumeRefInput(StoragePoolRefInput):
    volume_name: str = Field(min_length=1, max_length=255)


class SnapshotRefInput(DomainRefInput):
    snapshot_name: str = Field(min_length=1, max_length=255)


class CreateSnapshotInput(DomainRefInput):
    snapshot_xml: str = Field(min_length=1)


class DomainDefineInput(StrictModel):
    domain_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)
    dry_run: bool = False


class NetworkDefineInput(StrictModel):
    network_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class StoragePoolDefineInput(StrictModel):
    pool_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class StorageVolumeCreateInput(StoragePoolRefInput):
    volume_xml: str = Field(min_length=1)


class QmpBalloonInput(DomainRefInput):
    balloon_mb: int = Field(gt=0, le=4194304)  # max 4TB


class QmpBlockStreamInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=255)
    base: str | None = Field(default=None, max_length=1024)
    speed: int = Field(default=0, ge=0)


class QmpBlockJobDeviceInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=255)


class QmpBlockJobCancelInput(QmpBlockJobDeviceInput):
    force: bool = False


class QmpDeviceAddInput(DomainRefInput):
    driver: str = Field(min_length=1, max_length=255)
    device_id: str = Field(min_length=1, max_length=255)
    device_opts: dict[str, Any] = Field(default_factory=dict)


class QmpDeviceDelInput(DomainRefInput):
    device_id: str = Field(min_length=1, max_length=255)


class StorageLinkedCloneCreateInput(StoragePoolRefInput):
    volume_name: str = Field(min_length=1, max_length=255)
    backing_file: str = Field(min_length=1, max_length=1024)
    capacity_bytes: int = Field(default=107374182400, gt=0)
    format: str = Field(default="qcow2", min_length=1, max_length=32)
    backing_format: str = Field(default="qcow2", min_length=1, max_length=32)
    relative_backing: bool = True


# ---------------------------------------------------------------------------
# New schemas for extended API families
# ---------------------------------------------------------------------------


class NodeDeviceRefInput(StrictModel):
    device_name: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class ListNodeDevicesInput(StrictModel):
    capability: str | None = Field(default=None, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class InterfaceRefInput(StrictModel):
    iface_name: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class InterfaceDefineInput(StrictModel):
    interface_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class NWFilterRefInput(StrictModel):
    filter_name: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class NWFilterDefineInput(StrictModel):
    filter_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class SetNetworkAutostartInput(StrictModel):
    network_name: str = Field(min_length=1, max_length=255)
    autostart: bool
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class BlockJobInput(DomainRefInput):
    disk: str = Field(min_length=1, max_length=255)
    bandwidth: int = Field(default=0, ge=0)


class BlockCommitInput(BlockJobInput):
    base: str | None = Field(default=None, max_length=1024)
    top: str | None = Field(default=None, max_length=1024)


class CheckpointRefInput(DomainRefInput):
    checkpoint_name: str = Field(min_length=1, max_length=255)


class CreateCheckpointInput(DomainRefInput):
    checkpoint_xml: str = Field(min_length=1)


class StorageVolumeCloneInput(StrictModel):
    pool_name: str = Field(min_length=1, max_length=255)
    volume_name: str = Field(min_length=1, max_length=255)
    src_pool_name: str = Field(min_length=1, max_length=255)
    src_volume_name: str = Field(min_length=1, max_length=255)
    volume_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class SetStoragePoolAutostartInput(StoragePoolRefInput):
    autostart: bool


class DomainCapabilitiesInput(StrictModel):
    emulatorbin: str | None = Field(default=None, max_length=1024)
    arch: str | None = Field(default=None, max_length=64)
    machine: str | None = Field(default=None, max_length=255)
    virttype: str | None = Field(default=None, max_length=64)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class SetVcpusInput(DomainRefInput):
    vcpu_count: int = Field(gt=0, le=1024)
    live: bool = True
    persistent: bool = True


class SetMemoryInput(DomainRefInput):
    memory_kb: int = Field(gt=0)
    live: bool = True
    persistent: bool = True


class NumaCellInput(StrictModel):
    cell_id: int = Field(ge=0, le=1023)
    cpus: str = Field(min_length=1, max_length=255)
    memory_kb: int = Field(gt=0)


class DomainNumaTopologyInput(DomainRefInput):
    cells: list[NumaCellInput] = Field(min_length=1)
    live: bool = False
    persistent: bool = True


# ---------------------------------------------------------------------------
# QMP new family schemas
# ---------------------------------------------------------------------------


class QmpCpuAddInput(DomainRefInput):
    cpu_index: int = Field(ge=0, le=1023)


class QmpObjectAddInput(DomainRefInput):
    qom_type: str = Field(min_length=1, max_length=255)
    obj_id: str = Field(min_length=1, max_length=255)
    props: dict[str, Any] = Field(default_factory=dict)


class QmpObjectDelInput(DomainRefInput):
    obj_id: str = Field(min_length=1, max_length=255)


class QmpDriveMirrorInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=1024)
    target: str = Field(min_length=1, max_length=1024)
    format: str = Field(default="qcow2")
    sync: str = Field(default="full")
    speed: int = Field(default=0, ge=0)


class QmpBlockdevBackupInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=1024)
    target: str = Field(min_length=1, max_length=1024)
    sync: str = Field(default="full", min_length=1, max_length=32)
    job_id: str | None = Field(default=None, max_length=255)
    speed: int = Field(default=0, ge=0)


class QmpNbdServerStartInput(DomainRefInput):
    address: dict[str, Any]
    tls_creds: str | None = Field(default=None, max_length=255)
    tls_authz: str | None = Field(default=None, max_length=255)


class QmpNbdServerAddInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=1024)
    export_name: str | None = Field(default=None, max_length=255)
    writable: bool = False
    bitmap: str | None = Field(default=None, max_length=255)


class QmpNbdServerRemoveInput(DomainRefInput):
    export_name: str = Field(min_length=1, max_length=255)
    mode: str = Field(default="safe", max_length=32)


class QmpBackupPlanInput(DomainRefInput):
    device: str = Field(min_length=1, max_length=1024)
    export_name: str | None = Field(default=None, max_length=255)
    address: dict[str, Any]
    bitmap: str | None = Field(default=None, max_length=255)
    writable: bool = False
    backup_target: str | None = Field(default=None, max_length=1024)
    sync: str = Field(default="full", min_length=1, max_length=32)
    job_id: str | None = Field(default=None, max_length=255)
    speed: int = Field(default=0, ge=0)


class QmpBackupStartInput(QmpBackupPlanInput):
    cleanup_on_failure: bool = True


class QmpBackupStopInput(DomainRefInput):
    export_name: str | None = Field(default=None, max_length=255)
    remove_export: bool = True
    stop_server: bool = True
    mode: str = Field(default="safe", max_length=32)


class QmpBackupStatusInput(DomainRefInput):
    job_id: str | None = Field(default=None, max_length=255)
    event_limit: int = Field(default=50, ge=1, le=10000)


class QmpBitmapInput(DomainRefInput):
    node: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)


class QmpBitmapAddInput(QmpBitmapInput):
    persistent: bool = True


class QmpNetdevAddInput(DomainRefInput):
    netdev_type: str = Field(min_length=1, max_length=255)
    netdev_id: str = Field(min_length=1, max_length=255)
    netdev_opts: dict[str, Any] = Field(default_factory=dict)


class QmpNetdevDelInput(DomainRefInput):
    netdev_id: str = Field(min_length=1, max_length=255)


class QmpChardevAddInput(DomainRefInput):
    chardev_id: str = Field(min_length=1, max_length=255)
    backend: dict[str, Any]


class QmpChardevRemoveInput(DomainRefInput):
    chardev_id: str = Field(min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# Domain stats and pinning schemas
# ---------------------------------------------------------------------------


class DomainDiskRefInput(DomainRefInput):
    disk: str = Field(min_length=1, max_length=255)


class DomainInterfaceRefInput(DomainRefInput):
    interface: str = Field(min_length=1, max_length=255)


class SetVcpuPinInput(DomainRefInput):
    vcpu: int = Field(ge=0, le=1023)
    cpumap: list[int] = Field(min_length=1)


class SetEmulatorPinInput(DomainRefInput):
    cpumap: list[int] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Storage volume resize schema
# ---------------------------------------------------------------------------


class StorageVolumeResizeInput(StorageVolumeRefInput):
    capacity_bytes: int = Field(gt=0)


class StorageVolumeUploadInput(StorageVolumeRefInput):
    source_path: str = Field(min_length=1, max_length=4096)
    offset: int = Field(default=0, ge=0)
    length: int | None = Field(default=None, gt=0)


class StorageVolumeDownloadInput(StorageVolumeRefInput):
    target_path: str = Field(min_length=1, max_length=4096)
    offset: int = Field(default=0, ge=0)
    length: int | None = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# Domain validation and device update schemas
# ---------------------------------------------------------------------------


class DomainValidateInput(StrictModel):
    domain_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class DomainUpdateDeviceInput(DomainRefInput):
    device_xml: str = Field(min_length=1)
    live: bool = True
    persistent: bool = True


# ---------------------------------------------------------------------------
# Audit log query schema
# ---------------------------------------------------------------------------


class AuditLogQueryInput(StrictModel):
    limit: int = Field(default=100, ge=1, le=10000)
    tool_name: str | None = Field(default=None, max_length=255)
    result_filter: str | None = Field(default=None, max_length=64)
    since: str | None = Field(default=None, max_length=64)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


# ---------------------------------------------------------------------------
# Secret schemas
# ---------------------------------------------------------------------------


class SecretRefInput(StrictModel):
    secret_ref: str = Field(min_length=1, max_length=255)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class SecretDefineInput(StrictModel):
    secret_xml: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)


class SecretSetValueInput(StrictModel):
    secret_ref: str = Field(min_length=1, max_length=255)
    value_b64: str = Field(min_length=1)
    hypervisor_ref: str | None = Field(default=None, max_length=255)
