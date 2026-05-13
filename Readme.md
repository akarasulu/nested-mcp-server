# nested-mcp-server

Python MCP server for libvirt and QEMU/QMP virtualization operations.

## Coverage

**Operator parity coverage: 90%**

Phase A and Phase B are complete. Phase C is partially underway with storage upload/download, QMP migration telemetry, and persistent NUMA topology controls already implemented. The live tracker is [docs/parity-matrix.md](docs/parity-matrix.md).

## What It Exposes

- Host and multi-hypervisor discovery
- Domain inspection, lifecycle, XML management, statistics, pinning, and persistent NUMA topology
- Snapshot and checkpoint lifecycle
- Network, storage pool, and storage volume management
- Storage volume clone, linked clone, resize, wipe, upload, and download flows
- Host interfaces, network filters, node devices, and passthrough controls
- QMP command bridge with allowlist policy, typed QMP query/control helpers, and event collection
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
- `MCP_AUDIT_LOG_PATH=/var/log/libvirt-mcp/audit.log`

See [AGENTS.md](AGENTS.md) for the original project specification and [docs/codex-handoff.md](docs/codex-handoff.md) for current implementation notes.
