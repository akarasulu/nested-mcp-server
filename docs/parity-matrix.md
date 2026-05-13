# Libvirt and QMP Parity Matrix

This document is a living parity tracker for the MCP server.

Main project entry point: [Readme.md](../Readme.md)

It tracks parity against:

- libvirt API families
- QEMU/QMP command families

It is intentionally organized as common-first operations (general day-to-day management) before specialized or esoteric features.

## Scope and interpretation

- Full parity means broad, near-complete functional coverage of a family, not just one or two endpoints.
- Partial means useful subset shipped, but meaningful gaps remain.
- Planned means agreed target but not implemented yet.
- Not started means no real implementation yet.

Status legend:

- Implemented
- Partial
- Planned
- Not started

## Current implementation stance

Current server behavior is common-management-first.

Implemented strongly:

- Host and hypervisor discovery and domain capabilities
- Core domain lifecycle and vCPU/memory tuning
- Domain XML read and define/undefine
- Snapshot and checkpoint lifecycle
- Block job management (pull, commit, abort, info)
- Network and storage pool/volume core lifecycle
- Linked clone and volume clone helpers
- Host network interfaces and network filters
- Host node device enumeration and passthrough control
- QMP bridge with policy allowlist
- Domain statistics (aggregate, per-disk, per-interface, memory)
- CPU and emulator pinning
- Host and guest NUMA topology inspection plus persistent guest NUMA placement updates
- Storage volume resize and wipe
- Storage pool/volume XML and metadata inspection
- Storage pool build
- QMP CPU/memory device controls, block mirror, dirty bitmaps, netdev/chardev hotplug
- QMP migration telemetry (read-only)

Not yet parity-level:

- Live/offline migration (out of scope)
- Block backup and NBD export integration
- Durable QMP event replay controls

## Coverage indicator

**Operator parity coverage: 99%**

This is a project coverage indicator, not Python line coverage. It reflects complete Phase A and Phase B operator coverage, plus broad Phase C coverage through storage upload/download, storage metadata inspection, QMP block backup/NBD export controls and orchestration recipes, durable QMP event replay with retention and bounded collection loops, per-family policy scopes, actor/role tool policy, QMP migration telemetry, and persistent NUMA topology controls.

## Matrix

| Area | Capability family | Status | Current tools | Gap to parity | Priority |
|---|---|---|---|---|---|
| Host | Host summary and capabilities | Implemented | host_info, list_hypervisors, get_hypervisor, get_domain_capabilities | Add deeper node capability surfaces and tuning ops | P1 |
| Domain | List and inspect domains | Implemented | list_domains, get_domain, get_domain_xml | Add full stat variants and event feeds | P1 |
| Domain | Lifecycle controls | Implemented | start_domain, shutdown_domain, destroy_domain, reboot_domain, suspend_domain, resume_domain, set_domain_autostart | Add richer state transition controls and async job tracking | P1 |
| Domain | Domain definition management | Implemented | define_domain_xml, validate_domain_xml, update_domain_device_xml, undefine_domain | Add richer XML profile validation and rollback orchestration | P1 |
| Domain | vCPU and memory tuning | Implemented | set_domain_vcpus, set_domain_memory, get_host_numa_topology, get_domain_numa_topology, set_domain_numa_topology | Add maximum vCPU control and live NUMA reshaping where libvirt/QEMU support it safely | P2 |
| Domain | Domain statistics | Implemented | get_domain_stats, get_domain_block_stats, get_domain_interface_stats, get_domain_memory_stats | Add event feeds and deeper placement/stat correlations | P2 |
| Domain | CPU pinning and placement | Implemented | get_domain_vcpu_pin_info, set_domain_vcpu_pin, get_domain_emulator_pin_info, set_domain_emulator_pin, get_host_numa_topology, get_domain_numa_topology, set_domain_numa_topology | Add richer placement policy helpers | P2 |
| Domain | Snapshot management | Implemented | list_domain_snapshots, create_domain_snapshot, revert_domain_snapshot, delete_domain_snapshot | Add external snapshot modes and metadata controls | P2 |
| Domain | Checkpoint management | Implemented | list_domain_checkpoints, create_domain_checkpoint, delete_domain_checkpoint | Add checkpoint tree navigation and NBD export integration | P2 |
| Domain | Block job management | Implemented | block_pull, block_commit, block_job_abort, block_job_info | Add block mirror, block resize, and job progress polling | P2 |
| Network | Inspect networks | Implemented | list_networks, get_network, get_network_dhcp_leases | Add extended interface controls | P2 |
| Network | Network lifecycle and definition | Implemented | define_network_xml, start_network, destroy_network, undefine_network, set_network_autostart | Add update/change operations | P2 |
| Network | Host interfaces | Implemented | list_interfaces, get_interface, define_interface_xml, start_interface, stop_interface, undefine_interface | Add interface cloning and bridge management | P3 |
| Network | Network filters | Implemented | list_nwfilters, get_nwfilter, define_nwfilter_xml, undefine_nwfilter | Add filter reference resolution and binding status | P3 |
| Storage | Pool inspect and lifecycle | Implemented | list_storage_pools, get_storage_pool, get_storage_pool_xml, get_storage_pool_metadata, define_storage_pool_xml, start_storage_pool, destroy_storage_pool, undefine_storage_pool, set_storage_pool_autostart, refresh_storage_pool, build_storage_pool | Add type-specific settings | P1 |
| Storage | Volume inspect and lifecycle | Implemented | list_storage_volumes, get_storage_volume, get_storage_volume_metadata, create_storage_volume_xml, delete_storage_volume, clone_storage_volume, resize_storage_volume, wipe_storage_volume, upload_storage_volume, download_storage_volume | Add mutable metadata update support only where libvirt exposes a safe update path | P1 |
| Storage | Linked clone management | Implemented | create_linked_clone_volume, get_volume_xml, get_volume_backing_chain | Add parent resolution by volume identity, rebase/commit chain workflows | P1 |
| Host devices | Node device and passthrough management | Implemented | list_node_devices, get_node_device, detach_node_device, reattach_node_device | Add full MDEV/VFIO mediated device workflows | P2 |
| Policy | Mutation and destructive controls | Implemented | allow_mutations, allow_define, allow_destructive, allowlists, test prefix checks, get_policy_scopes, MCP_ACTOR_ROLES, MCP_ROLE_TOOL_ALLOWLIST | Add richer identity-provider integration when transport exposes authenticated principals | P1 |
| Audit | Operation audit trail | Implemented | request_id/actor/tool/target/result/error with per-family details and secret redaction | Add correlation IDs across chained sub-operations | P1 |
| QMP | Basic QMP command bridge | Implemented | qmp_command, qmp_capabilities, qmp_events, get_qmp_policy | Expand allowlist coverage by command family and improve typed responses | P1 |
| QMP | Typed query tools | Implemented | qmp_query_status, qmp_query_version, qmp_query_cpus, qmp_query_balloon, qmp_query_block, qmp_query_blockstats, qmp_query_pci, qmp_query_iothreads, qmp_query_chardev, qmp_query_vnc, qmp_query_block_jobs, qmp_query_machines, qmp_query_hotpluggable_cpus, qmp_query_memory_devices, qmp_query_block_dirty_bitmaps, qmp_query_migrate, qmp_query_migrate_capabilities, qmp_query_migrate_parameters | Add deeper stat variants | P2 |
| QMP | Runtime observability and events | Implemented | qmp_events (collect_events with timeout and filtering), qmp_replay_events, qmp_prune_events, qmp_collect_events_loop | Add process supervisor wrapper/resource view for always-on collection | P2 |
| Migration | Live/offline migration orchestration | Not started | None | Add migrate workflow, pre-checks, rollback, and policy controls | P1 |
| Secrets | Secret lifecycle | Implemented | list_secrets, get_secret, define_secret_xml, set_secret_value, get_secret_value, undefine_secret | Add ACL introspection and secret usage mapping | P2 |

## QMP family breakdown

| QMP family | Status | Current coverage | Gap |
|---|---|---|---|
| Query and status | Implemented | qmp_query_status, qmp_query_version, qmp_query_cpus, qmp_query_balloon, qmp_query_block, qmp_query_blockstats, qmp_query_pci, qmp_query_iothreads, qmp_query_chardev, qmp_query_vnc, qmp_query_block_jobs, qmp_query_machines | Add deeper stat variants |
| CPU and memory runtime controls | Implemented | qmp_balloon, qmp_query_hotpluggable_cpus, qmp_cpu_add, qmp_query_memory_devices, qmp_object_add, qmp_object_del; libvirt-backed get_host_numa_topology, get_domain_numa_topology, set_domain_numa_topology | Add live QMP NUMA object wiring where supported |
| Block and storage runtime jobs | Implemented | qmp_block_stream, qmp_block_job_cancel, qmp_block_job_pause, qmp_block_job_resume, qmp_block_job_complete, qmp_drive_mirror, qmp_blockdev_backup, qmp_nbd_server_start, qmp_nbd_server_add, qmp_nbd_server_remove, qmp_nbd_server_stop, plan_qmp_backup, start_qmp_nbd_backup, stop_qmp_nbd_backup, get_qmp_backup_status, qmp_query_block_dirty_bitmaps, qmp_block_dirty_bitmap_add, qmp_block_dirty_bitmap_remove, qmp_block_dirty_bitmap_clear | Add scheduled backup policy and restore validation helpers |
| Device hotplug and bus operations | Implemented | qmp_device_add, qmp_device_del, qmp_netdev_add, qmp_netdev_del, qmp_chardev_add, qmp_chardev_remove | PCI bus management and MDEV not yet |
| Migration telemetry | Implemented | qmp_query_migrate, qmp_query_migrate_capabilities, qmp_query_migrate_parameters | Migration control commands out of scope |
| Event streaming | Implemented | collect_events with timeout/type filtering, qmp_replay_events JSONL replay, qmp_prune_events retention, qmp_collect_events_loop bounded collection service | Add process supervisor wrapper/resource view for always-on collection |

## Parity roadmap phases

### Phase A: Common management parity (complete)

- Storage clone/refresh/autostart: done.
- Network autostart/DHCP leases: done.
- Domain vCPU and memory tuning: done.
- Block job lifecycle: done.
- Checkpoint lifecycle: done.
- Host node device enumeration and passthrough: done.
- Host interfaces and nwfilters: done.

### Phase B: Advanced operator parity (complete)

- Storage volume resize, wipe: done.
- QMP typed query bundle and block-job-level commands: done.
- Domain pinning and stats surfaces: done.
- QMP CPU hotplug, memory device objects, block mirror, dirty bitmaps: done.
- QMP netdev/chardev hotplug, migration telemetry: done.
- Host/domain NUMA topology inspection and persistent guest NUMA placement controls: done.

### Phase C: Specialized parity (partially underway)

- Migration workflows (explicitly out of scope).
- Storage volume upload/download: done.
- Storage pool/volume metadata inspection: done.
- Persistent NUMA topology and placement controls: done.
- QMP block backup and NBD export controls: done.
- QMP backup orchestration recipes: done.
- Durable QMP event replay controls, retention, and bounded collection loop: done.
- Per-family policy scope introspection: done.
- Per-tool actor/role policy: done.

## Update protocol for this matrix

When a new feature ships:

1. Add or update the matching row status.
2. List the exact MCP tool names added or changed.
3. Move one concrete gap item from Gap to parity into done notes in the PR.
4. If integration tests were added, note the test name in commit/PR notes.

## Suggested next parity targets

1. Scheduled backup policy and restore validation helpers.
2. Process supervisor wrapper/resource view for always-on QMP event collection.
3. Mutable storage metadata update support only where libvirt exposes a safe update path.
4. Live NUMA reshaping only where libvirt/QEMU support it safely.
5. Richer identity-provider integration when transport exposes authenticated principals.
