# nested-mcp-server

Python MCP server for libvirt and QEMU/QMP virtualization operations.

## Coverage

**Operator parity coverage: 100%**

Phase A and Phase B are complete. Phase C is covered with storage upload/download, storage metadata inspection and safe update capability reporting, QMP block backup/NBD export controls and orchestration recipes, durable QMP event replay with retention and bounded collection loops, per-family policy scopes, actor/role tool policy, QMP migration telemetry, persistent NUMA topology controls, and live numatune placement updates where libvirt exposes a safe path. The live tracker is [docs/parity-matrix.md](docs/parity-matrix.md).

## What It Exposes

- Host and multi-hypervisor discovery
- Domain inspection, lifecycle, XML management, statistics, pinning, persistent NUMA topology, and live numatune placement
- Snapshot and checkpoint lifecycle
- Network, storage pool, and storage volume management with XML and metadata inspection
- Storage metadata update capability reporting
- Storage volume clone, linked clone, resize, wipe, upload, and download flows
- Host interfaces, network filters, node devices, and passthrough controls
- QMP command bridge with allowlist policy, typed QMP query/control helpers, and event collection
- QMP block backup/NBD export controls, orchestration recipes, and durable event replay with retention
- Audit logging and default-safe mutation gates

## Safety Model

The server defaults to read-only behavior. Mutating operations require explicit policy flags, and broader/destructive operations remain separately gated. Integration tests and guarded mutators expect resources to use the configured test prefix, defaulting to `mcp_test_`.

## Quick Start

```bash
.venv/bin/nested-mcp-server
```

For local development checks:

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/test_integration_local_hypervisor.py --ignore=tests/test_integration_runtime_paths.py
scripts/run_integration_safe.sh
```

## Configuration

Common environment variables:

- `LIBVIRT_URI=qemu:///system`
- `LIBVIRT_URIS=qemu:///system,qemu+ssh://user@host/system`
- `MCP_LIBVIRT_ALLOW_MUTATIONS=false`
- `MCP_LIBVIRT_ALLOW_DEFINE=false`
- `MCP_LIBVIRT_ALLOW_DESTRUCTIVE=false`
- `MCP_QMP_ENABLE=true`
- `MCP_QMP_EVENT_LOG_PATH=./qmp-events.log`
- `MCP_QMP_EVENT_RETENTION_DAYS=30`
- `MCP_QMP_EVENT_RETENTION_MAX_RECORDS=100000`
- `MCP_ACTOR_ROLES=alice=admin;bob=viewer`
- `MCP_ROLE_TOOL_ALLOWLIST=admin=*;viewer=host_info,get_*,list_*`
- `MCP_AUDIT_LOG_PATH=/var/log/libvirt-mcp/audit.log`

See [AGENTS.md](AGENTS.md) for the original project specification.
