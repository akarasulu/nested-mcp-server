# AGENTS.md: MCP Server Specification for libvirt and QEMU

## 0) Current Implementation Profile (Agreed Defaults)

These defaults reflect current project direction and should be treated as normative unless explicitly overridden:

- Host OS targets: Debian and Manjaro.
- Runtime stack: latest distro-provided libvirt/QEMU, or newer custom rebuilds from local virt-stack.
- Hypervisor topology: multi-hypervisor support is required.
- libvirt transport defaults: qemu:///system first; qemu:///session supported as optional mode.
- Remote access: libvirt over SSH using local SSH keys.
- Safety posture: read-only-first rollout; destructive and broad mutation actions enabled later after stabilization.
- QMP posture: enabled from early milestones, with staged expansion from safe query commands to wider protocol operations.
- Output style: snake_case keys.
- Observability: audit logging is mandatory and must preserve incident-grade operation history.
- Testing: both unit and integration tests are required; integration must use dedicated non-production resources.

## 1) Purpose

Build a Python-based MCP server that exposes virtualization operations and state from:

- libvirt (primary control plane)
- QEMU APIs/protocols (primarily QMP for operations not covered well by libvirt)

The server should allow an MCP client to safely inspect and operate virtual machines, storage, networks, and host virtualization metadata.

## 2) Why Python

Python is the implementation language because:

- libvirt-python provides direct bindings to libvirt objects and APIs.
- Python has mature JSON and async tooling for QMP communications.
- Python supports rapid schema-first tool development and strong test ergonomics.

## 3) Scope

### In scope

- Read-only VM and host introspection via libvirt.
- Controlled VM lifecycle actions (start, stop, reboot, pause, resume), initially guarded by policy while read-only mode is default.
- Domain XML retrieval and optionally validated XML updates.
- Snapshot listing and selected snapshot operations.
- Storage pool and volume inspection.
- Network inspection and controlled network state operations.
- QMP passthrough for command sets not fully represented by libvirt, with staged allowlist expansion.
- Exposing resources representing domains, pools, networks, and capability documents.
- Multi-hypervisor discovery and operations via configured libvirt URIs and SSH-backed connections.

### Out of scope (initial milestone)

- Live migration orchestration across hosts.
- Full VM provisioning workflows (cloud image customization, OS install pipelines).
- Unrestricted shell or monitor command execution.
- Any operation requiring broad host root access beyond libvirt policy.
- Destructive operations by default.

## 4) High-Level Architecture

### Layers

1. MCP transport layer
	 - Handles MCP initialization, tool registration, tool invocation, resources listing, and reading.

2. Orchestration layer
	 - Input validation.
	 - Authorization/policy checks.
	 - Routing between libvirt and QMP adapters.
	 - Error normalization.

3. Provider adapters
	 - libvirt adapter: wraps libvirt connection/object APIs.
	 - QMP adapter: manages QMP session(s), handshake, command execution, and event filtering.

4. Serialization layer
	 - Converts libvirt/QMP objects and XML into stable JSON outputs for MCP clients.

### Connection model

- Preferred libvirt URI configured at startup (default: qemu:///system).
- Session mode (qemu:///session) supported when user services and policy permit it.
- Optional per-request URI override only if explicitly enabled by policy.
- Support multiple configured hypervisor endpoints, including SSH-based libvirt URIs.
- QMP endpoint mapping resolved from domain metadata or server config.

## 5) Core Entities and Resource Model

Expose MCP resources with stable identifiers and JSON payloads:

- hypervisor://capabilities
	- Host capabilities, libvirt version, hypervisor type, supported features.

- domain://{name-or-uuid}
	- Domain summary, state, vCPU/memory, autostart, metadata.

- domain://{name-or-uuid}/xml
	- Domain XML (inactive and optionally live variants).

- network://{name}
	- Network definition, active state, bridge info, DHCP ranges when available.

- storage-pool://{name}
	- Pool type/state/capacity/allocation/available.

- storage-volume://{pool}/{volume}
	- Volume path, key, capacity, allocation.

- qmp://{domain}/status
	- QMP-reported runtime status and selected feature flags.

## 6) Tool Catalog (Initial)

All tools must define strict input/output schemas and deterministic error envelopes.

### Host and discovery

- host_info
	- Returns host and hypervisor summary, capabilities, and server policy mode.
	- Includes active libvirt URI and endpoint identity.

- list_hypervisors
	- Lists configured hypervisor endpoints and connection health.

- get_hypervisor
	- Input: hypervisor_ref.
	- Returns endpoint details, connection mode, and capabilities summary.

- list_domains
	- Filters: active_only, inactive_only, name_prefix, hypervisor_ref.

- get_domain
	- Input: domain_ref (name or UUID), optional hypervisor_ref.
	- Returns normalized domain summary.

### Domain lifecycle

- start_domain
- shutdown_domain
- destroy_domain
- reboot_domain
- suspend_domain
- resume_domain

All lifecycle tools should support dry_run where feasible.
All lifecycle tools must enforce allow_mutations=false by default.

### Domain configuration

- get_domain_xml
	- Inputs: domain_ref, live (bool), inactive (bool), optional hypervisor_ref.

- define_domain_xml
	- Input: xml string.
	- Requires policy flag allow_define=true.

- set_domain_autostart
	- Input: domain_ref, autostart(bool).

### Snapshots

- list_domain_snapshots
- create_domain_snapshot
- revert_domain_snapshot
- delete_domain_snapshot

### Storage and networking

- list_storage_pools
- get_storage_pool
- list_storage_volumes
- get_storage_volume
- list_networks
- get_network

### QMP bridge (controlled)

- qmp_command
	- Inputs: domain_ref, command, arguments, optional hypervisor_ref.
	- command must be in an allowlist.
	- Returns QMP response with normalized metadata.

- qmp_capabilities
	- Input: domain_ref, optional hypervisor_ref.
	- Returns available QMP commands/features discovered for the domain endpoint.

- qmp_events
	- Input: domain_ref, event_types (optional), since (optional).
	- Returns filtered QMP events for diagnostics/audit contexts.

Suggested initial QMP allowlist:

- query-status
- query-version
- query-machines
- query-cpus-fast
- query-balloon
- query-block

Staged expansion policy:

- Stage A: read-only query-* commands and status inspection.
- Stage B: controlled non-destructive runtime controls, explicitly reviewed.
- Stage C: broader protocol operations enabled only behind explicit policy toggles and audit guarantees.

## 7) Input and Output Contract

### Input principles

- Prefer explicit domain_ref over implicit current context.
- Validate all strings for size and character constraints.
- Reject unknown fields in tool input.

### Output principles

- Stable snake_case JSON keys.
- Include source field: libvirt or qmp.
- Include timestamp in ISO-8601 UTC.
- For list operations: return items plus total_count.
- Include hypervisor_ref for multi-hypervisor operations.

### Standard error envelope

{
	"error": {
		"code": "DOMAIN_NOT_FOUND",
		"message": "Domain 'vm1' was not found",
		"retryable": false,
		"details": {"domain_ref": "vm1", "source": "libvirt"}
	}
}

## 8) Safety, Security, and Policy

### Security baseline

- Run with least privilege.
- Prefer libvirt ACL/polkit enforcement over ad-hoc checks.
- No arbitrary shell command execution tools.
- Strictly bound QMP access to configured sockets/endpoints.

### Policy toggles (server config)

- allow_mutations (default false)
- allow_define (default false)
- allow_qmp (default true)
- qmp_command_allowlist (explicit list)
- allowed_libvirt_uris
- max_concurrent_operations (default 0 for adaptive/unbounded)
- allow_destructive_actions (default false)
- allow_uri_override (default false)
- audit_log_path (required)

### Auditability

- Log every mutating operation with caller, target, and result.
- Redact secrets and host-sensitive material from logs.
- Record immutable operation timeline fields: request_id, actor, timestamp, tool_name, target_ref, hypervisor_ref, result, and error code.
- Persist audit records to durable local storage suitable for incident reconstruction.

## 9) Error Mapping Strategy

Normalize provider exceptions to MCP-friendly codes:

- libvirt.libvirtError with no matching domain -> DOMAIN_NOT_FOUND
- permission denied -> PERMISSION_DENIED
- timeout -> OPERATION_TIMEOUT
- invalid XML -> INVALID_DOMAIN_XML
- QMP command not allowed -> QMP_COMMAND_DENIED
- QMP transport/socket failure -> QMP_TRANSPORT_ERROR

## 10) Configuration

Use environment variables and/or config file:

- LIBVIRT_URI=qemu:///system
- LIBVIRT_URIS=qemu:///system,qemu+ssh://user@host/system
- LIBVIRT_SSH_IDENTITY=~/.ssh/id_ed25519
- MCP_LIBVIRT_SUPPORT_SESSION=true
- MCP_LIBVIRT_ALLOW_MUTATIONS=false
- MCP_LIBVIRT_ALLOW_DEFINE=false
- MCP_LIBVIRT_ALLOW_DESTRUCTIVE=false
- MCP_QMP_ENABLE=true
- MCP_QMP_SOCKET_DIR=/var/run/qemu-server
- MCP_QMP_ALLOWLIST=query-status,query-version
- MCP_AUDIT_LOG_PATH=/var/log/libvirt-mcp/audit.log
- MCP_LOG_LEVEL=INFO
- MCP_MAX_CONCURRENT_OPERATIONS=0

## 11) Suggested Python Project Layout

src/
	libvirt_mcp_server/
		__init__.py
		server.py                # MCP entrypoint and registration
		config.py                # config parsing and policy
		schemas.py               # pydantic/dataclass input-output models
		errors.py                # normalized error definitions
		adapters/
			libvirt_adapter.py     # libvirt operations
			qmp_adapter.py         # QMP session and commands
		tools/
			host_tools.py
			domain_tools.py
			snapshot_tools.py
			storage_tools.py
			network_tools.py
			qmp_tools.py
		resources/
			domain_resources.py
			host_resources.py
			storage_resources.py
			network_resources.py
tests/
	test_tools_domain.py
	test_tools_host.py
	test_qmp_adapter.py
	fixtures/

## 12) Testing Strategy

### Unit tests

- Mock libvirt and QMP adapters.
- Validate schema and error mapping.
- Verify policy enforcement blocks disallowed operations.

### Integration tests

- Run against a local test hypervisor and disposable domains.
- Validate lifecycle idempotency and non-happy path behavior.
- Create dedicated test resources (network, storage pool, and VMs) with test-specific prefixes and strict cleanup.
- Explicitly block tests from running against production-tagged resources.

### Contract tests

- Snapshot expected JSON outputs for each tool.
- Ensure backward compatibility of response keys.

## 13) Incremental Delivery Plan

### Milestone 1: Read-only foundation

- host_info, list_hypervisors, get_hypervisor, list_domains, get_domain, get_domain_xml, list_networks, list_storage_pools, qmp_capabilities.
- Resource endpoints for host/domain summaries.

### Milestone 2: Controlled mutations

- start/shutdown/reboot/suspend/resume.
- allow_mutations gating and audit logging.

### Milestone 3: QMP bridge

- qmp_command with strict allowlist plus staged expansion.
- QMP status resource and transport hardening.

### Milestone 4: Snapshots and refinement

- Snapshot tools and stronger contract testing.
- Performance and concurrency tuning.

## 14) Practical Notes for libvirt + QEMU Coverage

- Prefer libvirt first for canonical VM lifecycle and configuration.
- Use QMP only for capabilities not surfaced adequately in libvirt.
- When both paths can return similar data, document precedence and include source in output.
- Keep XML handling explicit: avoid opaque passthrough without validation for mutating flows.

## 15) Definition of Done

The MCP server is considered ready for initial use when:

- Milestone 1 and Milestone 2 tools are implemented with schemas and tests.
- Policy toggles are enforced and default-safe.
- Error envelope is consistent across all tools.
- Basic resource listing and reading works for host and domains.
- Documentation includes setup, required permissions, and example MCP client calls.
- Integration tests run against dedicated non-production fixtures with guaranteed cleanup.
