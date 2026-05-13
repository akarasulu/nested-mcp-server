import json
from pathlib import Path
import asyncio
from types import SimpleNamespace
import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.server import LibvirtMCPServer, run_tool_sync


def test_unknown_tool_returns_error(tmp_path: Path):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    server = LibvirtMCPServer(config=cfg)

    result = asyncio.run(server.call_tool("not_real_tool", {}))

    assert "error" in result
    assert result["error"]["code"] == "UNKNOWN_TOOL"


def test_audit_is_written_on_failure(tmp_path: Path):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    server = LibvirtMCPServer(config=cfg)

    asyncio.run(server.call_tool("get_domain", {"domain_ref": "missing-vm"}, actor="tester"))

    line = Path(cfg.audit_log_path).read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["actor"] == "tester"
    assert record["result"] == "error"


def test_list_tools_contains_expected_entries(tmp_path: Path):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    server = LibvirtMCPServer(config=cfg)

    tools = server.list_tools()
    assert "host_info" in tools
    assert "get_host_numa_topology" in tools
    assert "qmp_events" in tools
    assert "define_domain_xml" in tools
    assert "get_domain_numa_topology" in tools
    assert "set_domain_numa_topology" in tools
    assert "define_network_xml" in tools
    assert "define_storage_pool_xml" in tools
    assert "get_storage_pool_xml" in tools
    assert "get_storage_pool_metadata" in tools
    assert "get_storage_volume_metadata" in tools
    assert "create_storage_volume_xml" in tools
    assert "create_linked_clone_volume" in tools
    assert "upload_storage_volume" in tools
    assert "download_storage_volume" in tools
    assert "qmp_blockdev_backup" in tools
    assert "qmp_nbd_server_start" in tools
    assert "qmp_nbd_server_add" in tools
    assert "qmp_nbd_server_remove" in tools
    assert "qmp_nbd_server_stop" in tools
    assert "plan_qmp_backup" in tools
    assert "start_qmp_nbd_backup" in tools
    assert "stop_qmp_nbd_backup" in tools
    assert "get_qmp_backup_status" in tools
    assert "qmp_replay_events" in tools
    assert "get_policy_scopes" in tools
    assert len(tools) >= 20


def test_fastmcp_app_uses_project_server_name():
    from libvirt_mcp_server.app import app

    assert app.name == "nested-mcp-server"


def test_run_tool_sync_invokes_server(monkeypatch):
    observed = {}

    class FakeServer:
        def __init__(self):
            observed["constructed"] = True

        async def call_tool(self, tool_name, arguments, actor="cli"):
            observed["tool_name"] = tool_name
            observed["arguments"] = arguments
            observed["actor"] = actor
            return {"ok": True}

    monkeypatch.setattr("libvirt_mcp_server.server.LibvirtMCPServer", FakeServer)

    result = run_tool_sync("host_info", {"hypervisor_ref": "default"}, actor="unit")
    assert result == {"ok": True}
    assert observed["constructed"] is True
    assert observed["tool_name"] == "host_info"
    assert observed["arguments"] == {"hypervisor_ref": "default"}
    assert observed["actor"] == "unit"


def test_linked_clone_success_audit_includes_backing_details(tmp_path: Path, monkeypatch):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    cfg.allow_mutations = True
    server = LibvirtMCPServer(config=cfg)

    from libvirt_mcp_server.tools import storage_tools

    def _fake_create_linked_clone_volume(*_args, **kwargs):
        return {
            "source": "libvirt",
            "status": "created",
            "pool_name": kwargs["pool_name"],
            "volume_name": kwargs["volume_name"],
            "backing_file": kwargs["backing_file"],
            "relative_backing": kwargs["relative_backing"],
        }

    monkeypatch.setattr(storage_tools, "create_linked_clone_volume", _fake_create_linked_clone_volume)

    payload = {
        "pool_name": "mcp_test_pool",
        "volume_name": "mcp_test_child.qcow2",
        "backing_file": "../vda.qcow2",
        "relative_backing": True,
        "capacity_bytes": 1048576,
        "format": "qcow2",
        "backing_format": "qcow2",
    }
    result = asyncio.run(server.call_tool("create_linked_clone_volume", payload, actor="tester"))
    assert "error" not in result

    line = Path(cfg.audit_log_path).read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["result"] == "success"
    assert record["details"]["pool_name"] == "mcp_test_pool"
    assert record["details"]["volume_name"] == "mcp_test_child.qcow2"
    assert record["details"]["backing_file"] == "../vda.qcow2"
    assert record["details"]["relative_backing"] is True


@pytest.mark.parametrize(
    "tool_name,args,module_path,func_name",
    [
        (
            "validate_domain_xml",
            {"domain_xml": "<domain><name>vm1</name></domain>"},
            "libvirt_mcp_server.tools.domain_tools",
            "validate_domain_xml",
        ),
        (
            "get_host_numa_topology",
            {},
            "libvirt_mcp_server.tools.host_tools",
            "get_host_numa_topology",
        ),
        (
            "get_domain_numa_topology",
            {"domain_ref": "vm1"},
            "libvirt_mcp_server.tools.domain_tools",
            "get_domain_numa_topology",
        ),
        (
            "set_domain_numa_topology",
            {
                "domain_ref": "mcp_test_vm1",
                "cells": [{"cell_id": 0, "cpus": "0", "memory_kb": 262144}],
            },
            "libvirt_mcp_server.tools.domain_tools",
            "set_domain_numa_topology",
        ),
        (
            "update_domain_device_xml",
            {
                "domain_ref": "vm1",
                "device_xml": "<disk/>",
                "live": True,
                "persistent": True,
            },
            "libvirt_mcp_server.tools.domain_tools",
            "update_domain_device_xml",
        ),
        (
            "get_volume_xml",
            {"pool_name": "pool0", "volume_name": "vol0"},
            "libvirt_mcp_server.tools.storage_tools",
            "get_volume_xml",
        ),
        (
            "get_storage_pool_xml",
            {"pool_name": "pool0"},
            "libvirt_mcp_server.tools.storage_tools",
            "get_storage_pool_xml",
        ),
        (
            "get_storage_pool_metadata",
            {"pool_name": "pool0"},
            "libvirt_mcp_server.tools.storage_tools",
            "get_storage_pool_metadata",
        ),
        (
            "get_storage_volume_metadata",
            {"pool_name": "pool0", "volume_name": "vol0"},
            "libvirt_mcp_server.tools.storage_tools",
            "get_storage_volume_metadata",
        ),
        (
            "get_volume_backing_chain",
            {"pool_name": "pool0", "volume_name": "vol0"},
            "libvirt_mcp_server.tools.storage_tools",
            "get_volume_backing_chain",
        ),
        (
            "upload_storage_volume",
            {"pool_name": "pool0", "volume_name": "vol0", "source_path": "/tmp/payload.bin"},
            "libvirt_mcp_server.tools.storage_tools",
            "upload_storage_volume",
        ),
        (
            "download_storage_volume",
            {"pool_name": "pool0", "volume_name": "vol0", "target_path": "/tmp/download.bin"},
            "libvirt_mcp_server.tools.storage_tools",
            "download_storage_volume",
        ),
        (
            "get_audit_log",
            {},
            "libvirt_mcp_server.tools.host_tools",
            "get_audit_log",
        ),
        (
            "get_qmp_policy",
            {},
            "libvirt_mcp_server.tools.host_tools",
            "get_qmp_policy",
        ),
        (
            "get_policy_scopes",
            {},
            "libvirt_mcp_server.tools.host_tools",
            "get_policy_scopes",
        ),
        (
            "list_secrets",
            {},
            "libvirt_mcp_server.tools.secret_tools",
            "list_secrets",
        ),
        (
            "get_secret",
            {"secret_ref": "sec0"},
            "libvirt_mcp_server.tools.secret_tools",
            "get_secret",
        ),
        (
            "define_secret_xml",
            {"secret_xml": "<secret/>"},
            "libvirt_mcp_server.tools.secret_tools",
            "define_secret_xml",
        ),
        (
            "set_secret_value",
            {"secret_ref": "sec0", "value_b64": "dGVzdA=="},
            "libvirt_mcp_server.tools.secret_tools",
            "set_secret_value",
        ),
        (
            "get_secret_value",
            {"secret_ref": "sec0"},
            "libvirt_mcp_server.tools.secret_tools",
            "get_secret_value",
        ),
        (
            "undefine_secret",
            {"secret_ref": "sec0"},
            "libvirt_mcp_server.tools.secret_tools",
            "undefine_secret",
        ),
    ],
)
def test_phase4_tool_dispatches_via_call_tool(
    tmp_path: Path,
    monkeypatch,
    tool_name: str,
    args: dict,
    module_path: str,
    func_name: str,
):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    cfg.allow_mutations = True
    cfg.allow_define = True
    cfg.allow_secret_read = True
    server = LibvirtMCPServer(config=cfg)

    called = {"value": False}

    def _fake_handler(*_args, **_kwargs):
        called["value"] = True
        return {"source": "test", "ok": tool_name}

    monkeypatch.setattr(f"{module_path}.{func_name}", _fake_handler)

    result = asyncio.run(server.call_tool(tool_name, args, actor="tester"))
    assert called["value"] is True
    assert result["ok"] == tool_name


def test_success_audit_details_tolerates_non_dict_result(tmp_path: Path):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    server = LibvirtMCPServer(config=cfg)

    details = server._success_audit_details("set_domain_autostart", {"domain_ref": "vm1"}, None)
    assert details["summary"] == "ok"
    assert details["result_type"] == "NoneType"
