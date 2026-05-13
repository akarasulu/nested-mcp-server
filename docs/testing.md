# MCP Test Sandbox

Use dedicated `mcp_test_*` resources for integration tests so mutation and destructive actions stay isolated.

## Setup

Run:

```bash
scripts/mcp_test_setup.sh
```

This script ensures:

- `mcp_test_network` exists and is active (NAT network)
- `mcp_test_dummy` exists with a qcow2 disk (linked clone by default when parent image exists)
- Domain XML is stored at the VM directory for reference

## Linked Clone Disk Layout

The setup script supports your qcow2 tree pattern with a root/template image and child overlays.

Default behavior:

- `LIBVIRT_MCP_TEST_VM_USE_LINKED_CLONE=true`
- Parent/root image path defaults to `${LIBVIRT_MCP_TEST_VM_BASE_DIR}/vda.qcow2`
- Child overlay path defaults to `${LIBVIRT_MCP_TEST_VM_DIR}/vda.qcow2`
- Backing reference is written as a relative path when `realpath` is available (for example `../vda.qcow2`)

Environment overrides:

```bash
export LIBVIRT_MCP_TEST_VM_USE_LINKED_CLONE=true
export LIBVIRT_MCP_TEST_VM_PARENT_DISK_PATH=/home/aok/Local/Vms/KVM/deb13/vda.qcow2
```

If linked-clone mode is enabled but the parent image is missing, setup falls back to creating a standalone qcow2 disk and prints a warning.

The script prints `export` statements for integration and policy env vars.

## Teardown

Run:

```bash
scripts/mcp_test_teardown.sh
```

By default it keeps the disk files. To remove them too:

```bash
LIBVIRT_MCP_TEST_DELETE_DISK=1 scripts/mcp_test_teardown.sh
```

## Recommended test env

```bash
export LIBVIRT_MCP_RUN_INTEGRATION=1
export LIBVIRT_MCP_TEST_PREFIX=mcp_test_
export LIBVIRT_MCP_TEST_DOMAIN=mcp_test_dummy
export LIBVIRT_MCP_TEST_NETWORK=mcp_test_network
export LIBVIRT_MCP_TEST_VM_USE_LINKED_CLONE=true
export LIBVIRT_MCP_TEST_VM_PARENT_DISK_PATH=/home/aok/Local/Vms/KVM/deb13/vda.qcow2

export MCP_LIBVIRT_ALLOW_MUTATIONS=true
export MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST=mcp_test_dummy
export MCP_LIBVIRT_ALLOW_DESTRUCTIVE=false
export MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST=mcp_test_dummy
```

Then run:

```bash
scripts/coverage_integration_first.sh
```

For continuation notes when handing off to another coding service, see [docs/codex-handoff.md](docs/codex-handoff.md).

## Safe integration runbook (both integration suites)

Use this flow when validating local hypervisor behavior for new tool families.

1. Prepare dedicated sandbox resources:

```bash
scripts/mcp_test_setup.sh
```

2. Export the minimum required env flags:

```bash
export LIBVIRT_MCP_RUN_INTEGRATION=1
export LIBVIRT_MCP_TEST_PREFIX=mcp_test_
export LIBVIRT_MCP_TEST_DOMAIN=mcp_test_dummy
export LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN=mcp_test_dummy
export LIBVIRT_MCP_TEST_NETWORK=mcp_test_network

export MCP_LIBVIRT_ALLOW_MUTATIONS=true
export MCP_LIBVIRT_MUTATION_DOMAIN_ALLOWLIST=mcp_test_dummy
export MCP_LIBVIRT_ALLOW_DESTRUCTIVE=false
export MCP_LIBVIRT_DESTRUCTIVE_DOMAIN_ALLOWLIST=mcp_test_dummy
```

3. Run both integration suites directly:

```bash
.venv/bin/python -m pytest tests/test_integration_local_hypervisor.py -q
.venv/bin/python -m pytest tests/test_integration_runtime_paths.py -q
```

4. Optional: run them together in one command:

```bash
.venv/bin/python -m pytest tests/test_integration_local_hypervisor.py tests/test_integration_runtime_paths.py -q
```

5. Teardown sandbox resources after validation:

```bash
scripts/mcp_test_teardown.sh
```

To also delete test disks/VM directory:

```bash
LIBVIRT_MCP_TEST_DELETE_DISK=1 scripts/mcp_test_teardown.sh
```
