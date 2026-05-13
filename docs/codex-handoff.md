# Codex Handoff Notes

This file is only for continuing work in another coding service with minimal context loss.

## Current state

- Repository: nested-mcp-server
- Integration runner is green: `scripts/run_integration_safe.sh`
- Non-integration tests are green: `192 passed`
- `runpy` integration warning has been resolved
- Phase 4 contract/snapshot tests have been added
- Storage volume upload/download tools have been implemented
- Phase B is complete, including host/domain NUMA topology and persistent guest NUMA placement controls
- Phase C is partially underway rather than deferred

## What was completed

- Implemented remaining Phase 4 completion tools, including:
	- domain XML validation and device update
	- volume XML and backing-chain inspection
	- audit log query and QMP policy introspection
	- full secrets lifecycle tools
- Added integration helper script: `scripts/run_integration_safe.sh`
- Fixed regression in `set_domain_autostart` return path
- Hardened server audit success-details handling for unexpected non-dict tool results
- Fixed the `runpy` integration warning in `test_integration_runtime_paths.py`
- Added snapshot-style contract tests for Phase 4 domain, storage, audit, QMP policy, and secret outputs
- Added guarded storage volume upload/download via libvirt streams with unit and integration coverage
- Added host/domain NUMA topology inspection plus persistent guest NUMA placement updates with unit, dispatch, and integration coverage
- Added root `Readme.md` and linked it to the parity matrix coverage indicator

## Start here in Codex

1. Read these files first:
	 - `src/libvirt_mcp_server/server.py`
	 - `src/libvirt_mcp_server/tools/domain_tools.py`
	 - `src/libvirt_mcp_server/tools/secret_tools.py`
	 - `src/libvirt_mcp_server/app.py`
	 - `tests/test_integration_runtime_paths.py`
	 - `tests/test_server.py`
	 - `tests/test_tools_new_completions.py`
	 - `docs/parity-matrix.md`
	 - `docs/testing.md`

2. Reproduce baseline checks:

```bash
scripts/run_integration_safe.sh
.venv/bin/python -m pytest tests/ --ignore=tests/test_integration_local_hypervisor.py --ignore=tests/test_integration_runtime_paths.py
```

3. Continue with next tasks:
	 1. Implement next parity gaps from `docs/parity-matrix.md`:
			- Storage metadata operations
			- Block backup and NBD export integration
			- Durable QMP event replay controls

## Copy-paste handoff message

Use this when handing off:

Working state is green. Integration passes cleanly with `scripts/run_integration_safe.sh`, and non-integration suite is passing (`192 passed` before the latest NUMA/readme additions). Phase 4 completion tools are implemented and wired, including secrets lifecycle. Recent fixes included `set_domain_autostart` return regression, audit hardening for non-dict results, removal of the `runpy` warning in integration runtime-path tests, Phase 4 contract snapshots, guarded storage volume upload/download, and host/domain NUMA topology with persistent guest NUMA placement controls. Phase B is complete; Phase C is partially underway. Next: storage metadata operations, block backup/NBD export integration, or durable QMP event replay controls.
