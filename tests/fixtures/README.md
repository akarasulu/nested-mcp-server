# Integration fixture notes

Use disposable resources only.

Recommended naming:
- network: mcp_test_net
- storage pool: mcp_test_pool
- vm names: mcp_test_vm_* 

Run integration tests explicitly:

```bash
LIBVIRT_MCP_RUN_INTEGRATION=1 pytest -m integration
```
