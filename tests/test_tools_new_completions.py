"""Unit tests for Phase 4 completion tools and policies."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.server import LibvirtMCPServer
from libvirt_mcp_server.tools import domain_tools, host_tools, secret_tools, storage_tools


@pytest.fixture
def cfg_readonly() -> ServerConfig:
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = False
    cfg.allow_define = False
    cfg.allow_secret_read = False
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


@pytest.fixture
def cfg_mutations() -> ServerConfig:
    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    cfg.allow_define = True
    cfg.allow_secret_read = True
    cfg.test_resource_prefix = "mcp_test_"
    return cfg


def _make_adapter(**methods):
    adapter = MagicMock()
    for name, retval in methods.items():
        getattr(adapter, name).return_value = retval
    return adapter


def _contract_snapshot(value):
    if isinstance(value, dict):
        return {
            key: "<timestamp>" if key == "timestamp" else _contract_snapshot(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_contract_snapshot(item) for item in value]
    return value


def test_define_domain_xml_dry_run_does_not_call_adapter(cfg_mutations: ServerConfig):
    adapter = MagicMock()
    xml = "<domain><name>mcp_test_vm1</name></domain>"
    result = domain_tools.define_domain_xml(cfg_mutations, adapter, domain_xml=xml, hypervisor_ref=None, dry_run=True)
    assert result["dry_run"] is True
    assert result["status"] == "approved"
    adapter.define_domain_xml.assert_not_called()


def test_validate_domain_xml_delegates_to_adapter(cfg_readonly: ServerConfig):
    adapter = _make_adapter(validate_domain_xml={"source": "libvirt", "status": "valid"})
    result = domain_tools.validate_domain_xml(cfg_readonly, adapter, domain_xml="<domain/>", hypervisor_ref=None)
    assert result["status"] == "valid"
    adapter.validate_domain_xml.assert_called_once()


def test_update_domain_device_xml_blocked_when_mutations_off(cfg_readonly: ServerConfig):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        domain_tools.update_domain_device_xml(
            cfg_readonly,
            adapter,
            domain_ref="mcp_test_vm1",
            device_xml="<disk/>",
            live=True,
            persistent=True,
            hypervisor_ref=None,
        )
    assert exc.value.code == "MUTATION_DISABLED"


def test_get_volume_xml_and_backing_chain(cfg_readonly: ServerConfig):
    adapter = _make_adapter(
        get_volume_xml={"source": "libvirt", "volume_name": "base.qcow2", "xml": "<volume/>"},
        get_volume_backing_chain={"source": "libvirt", "volume_name": "child.qcow2", "chain": [{"path": "/pool/base.qcow2"}]},
    )
    xml_res = storage_tools.get_volume_xml(cfg_readonly, adapter, pool_name="default", volume_name="base.qcow2", hypervisor_ref=None)
    chain_res = storage_tools.get_volume_backing_chain(cfg_readonly, adapter, pool_name="default", volume_name="child.qcow2", hypervisor_ref=None)
    assert xml_res["volume_name"] == "base.qcow2"
    assert chain_res["chain"][0]["path"] == "/pool/base.qcow2"


def test_get_qmp_policy_effective_allowlist(cfg_mutations: ServerConfig):
    cfg_mutations.qmp_allowlist = {"query-status"}
    cfg_mutations.qmp_mutation_allowlist = {"device_add"}
    result = host_tools.get_qmp_policy(cfg_mutations)
    assert result["qmp_enabled"] is True
    assert "query-status" in result["effective_allowlist"]
    assert "device_add" in result["effective_allowlist"]


def test_get_policy_scopes_reports_family_gates(cfg_readonly: ServerConfig):
    result = host_tools.get_policy_scopes(cfg_readonly)
    scopes = {item["scope"]: item for item in result["items"]}
    assert scopes["read_only"]["enabled"] is True
    assert scopes["mutation"]["enabled"] is False
    assert scopes["mutation"]["policy_gate"] == "allow_mutations"
    assert "storage_lifecycle" in scopes["mutation"]["families"]


def test_secret_get_value_requires_policy(cfg_readonly: ServerConfig):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        secret_tools.get_secret_value(cfg_readonly, adapter, secret_ref="my-secret", hypervisor_ref=None)
    assert exc.value.code == "SECRET_READ_DISABLED"


def test_set_secret_value_rejects_invalid_base64(cfg_mutations: ServerConfig):
    adapter = MagicMock()
    with pytest.raises(MCPError) as exc:
        secret_tools.set_secret_value(cfg_mutations, adapter, secret_ref="my-secret", value_b64="not-base64!", hypervisor_ref=None)
    assert exc.value.code == "INVALID_SECRET_VALUE"


def test_server_audit_redacts_secret_values(tmp_path: Path, monkeypatch):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    cfg.allow_mutations = True
    cfg.allow_secret_read = True
    server = LibvirtMCPServer(config=cfg)

    def _fake_set_secret_value(*_args, **_kwargs):
        return {"source": "libvirt", "status": "updated"}

    def _fake_get_secret_value(*_args, **_kwargs):
        return {"source": "libvirt", "status": "ok", "value_b64": "dGVzdA=="}

    monkeypatch.setattr(secret_tools, "set_secret_value", _fake_set_secret_value)
    monkeypatch.setattr(secret_tools, "get_secret_value", _fake_get_secret_value)

    asyncio.run(server.call_tool("set_secret_value", {"secret_ref": "sec1", "value_b64": "dGVzdA=="}, actor="tester"))
    asyncio.run(server.call_tool("get_secret_value", {"secret_ref": "sec1"}, actor="tester"))

    lines = Path(cfg.audit_log_path).read_text(encoding="utf-8").strip().splitlines()
    set_record = json.loads(lines[-2])
    get_record = json.loads(lines[-1])

    assert set_record["tool_name"] == "set_secret_value"
    assert set_record["details"]["value_redacted"] is True
    assert "value_b64" not in set_record["details"]

    assert get_record["tool_name"] == "get_secret_value"
    assert get_record["details"]["value_redacted"] is True
    assert "value_b64" not in get_record["details"]


def test_phase4_domain_volume_and_policy_contract_snapshots(cfg_mutations: ServerConfig):
    cfg_mutations.mutation_domain_allowlist = set()
    cfg_mutations.qmp_allowlist = {"query-status", "query-version"}
    cfg_mutations.qmp_mutation_allowlist = {"device_add"}
    adapter = _make_adapter(
        validate_domain_xml={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "domain_ref": "mcp_test_vm1",
            "domain_type": "kvm",
            "valid": True,
            "issues": [],
            "element_count": 3,
        },
        update_domain_device_xml={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "domain_ref": "mcp_test_vm1",
            "status": "updated",
            "live": True,
            "config": True,
        },
        get_volume_xml={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "pool_name": "mcp_test_pool",
            "volume_name": "mcp_test_child.qcow2",
            "xml": "<volume/>",
        },
        get_volume_backing_chain={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "pool_name": "mcp_test_pool",
            "volume_name": "mcp_test_child.qcow2",
            "chain_depth": 2,
            "chain": [
                {
                    "depth": 0,
                    "pool": "mcp_test_pool",
                    "name": "mcp_test_child.qcow2",
                    "path": "/pool/child.qcow2",
                    "format": "qcow2",
                    "resolved": True,
                },
                {
                    "depth": 1,
                    "path": "/pool/base.qcow2",
                    "format": "qcow2",
                    "resolved": False,
                },
            ],
        },
    )

    snapshots = {
        "validate_domain_xml": domain_tools.validate_domain_xml(
            cfg_mutations,
            adapter,
            domain_xml="<domain><name>mcp_test_vm1</name><memory/><vcpu/></domain>",
            hypervisor_ref=None,
        ),
        "update_domain_device_xml": domain_tools.update_domain_device_xml(
            cfg_mutations,
            adapter,
            domain_ref="mcp_test_vm1",
            device_xml="<disk/>",
            live=True,
            persistent=True,
            hypervisor_ref=None,
        ),
        "get_volume_xml": storage_tools.get_volume_xml(
            cfg_mutations,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_child.qcow2",
            hypervisor_ref=None,
        ),
        "get_volume_backing_chain": storage_tools.get_volume_backing_chain(
            cfg_mutations,
            adapter,
            pool_name="mcp_test_pool",
            volume_name="mcp_test_child.qcow2",
            hypervisor_ref=None,
        ),
        "get_qmp_policy": host_tools.get_qmp_policy(cfg_mutations),
    }

    assert _contract_snapshot(snapshots) == {
        "validate_domain_xml": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "domain_ref": "mcp_test_vm1",
            "domain_type": "kvm",
            "valid": True,
            "issues": [],
            "element_count": 3,
            "hypervisor_ref": "default",
        },
        "update_domain_device_xml": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "domain_ref": "mcp_test_vm1",
            "status": "updated",
            "live": True,
            "config": True,
            "hypervisor_ref": "default",
        },
        "get_volume_xml": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "pool_name": "mcp_test_pool",
            "volume_name": "mcp_test_child.qcow2",
            "xml": "<volume/>",
            "hypervisor_ref": "default",
        },
        "get_volume_backing_chain": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "pool_name": "mcp_test_pool",
            "volume_name": "mcp_test_child.qcow2",
            "chain_depth": 2,
            "chain": [
                {
                    "depth": 0,
                    "pool": "mcp_test_pool",
                    "name": "mcp_test_child.qcow2",
                    "path": "/pool/child.qcow2",
                    "format": "qcow2",
                    "resolved": True,
                },
                {
                    "depth": 1,
                    "path": "/pool/base.qcow2",
                    "format": "qcow2",
                    "resolved": False,
                },
            ],
            "hypervisor_ref": "default",
        },
        "get_qmp_policy": {
            "source": "server",
            "timestamp": "<timestamp>",
            "qmp_enabled": True,
            "allow_mutations": True,
            "read_allowlist": ["query-status", "query-version"],
            "mutation_allowlist": ["device_add"],
            "effective_allowlist": ["device_add", "query-status", "query-version"],
        },
    }


def test_phase4_secret_contract_snapshots(cfg_mutations: ServerConfig):
    adapter = _make_adapter(
        list_secrets=[
            {
                "source": "libvirt",
                "uuid": "00000000-0000-0000-0000-000000000001",
                "usage_type": "volume",
                "usage_id": "mcp_test_volume",
            }
        ],
        get_secret={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "usage_type": "volume",
            "usage_id": "mcp_test_volume",
            "xml": "<secret/>",
        },
        define_secret_xml={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "defined",
        },
        set_secret_value={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "value_set",
        },
        get_secret_value={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "value_b64": "dGVzdA==",
        },
        undefine_secret={
            "source": "libvirt",
            "timestamp": "2026-05-13T00:00:00+00:00",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "undefined",
        },
    )

    snapshots = {
        "list_secrets": secret_tools.list_secrets(cfg_mutations, adapter, hypervisor_ref=None),
        "get_secret": secret_tools.get_secret(
            cfg_mutations,
            adapter,
            secret_ref="00000000-0000-0000-0000-000000000001",
            hypervisor_ref=None,
        ),
        "define_secret_xml": secret_tools.define_secret_xml(
            cfg_mutations,
            adapter,
            secret_xml="<secret/>",
            hypervisor_ref=None,
        ),
        "set_secret_value": secret_tools.set_secret_value(
            cfg_mutations,
            adapter,
            secret_ref="00000000-0000-0000-0000-000000000001",
            value_b64="dGVzdA==",
            hypervisor_ref=None,
        ),
        "get_secret_value": secret_tools.get_secret_value(
            cfg_mutations,
            adapter,
            secret_ref="00000000-0000-0000-0000-000000000001",
            hypervisor_ref=None,
        ),
        "undefine_secret": secret_tools.undefine_secret(
            cfg_mutations,
            adapter,
            secret_ref="00000000-0000-0000-0000-000000000001",
            hypervisor_ref=None,
        ),
    }

    assert _contract_snapshot(snapshots) == {
        "list_secrets": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "hypervisor_ref": "default",
            "items": [
                {
                    "source": "libvirt",
                    "uuid": "00000000-0000-0000-0000-000000000001",
                    "usage_type": "volume",
                    "usage_id": "mcp_test_volume",
                }
            ],
            "total_count": 1,
        },
        "get_secret": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "usage_type": "volume",
            "usage_id": "mcp_test_volume",
            "xml": "<secret/>",
            "hypervisor_ref": "default",
        },
        "define_secret_xml": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "defined",
            "hypervisor_ref": "default",
        },
        "set_secret_value": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "value_set",
            "hypervisor_ref": "default",
        },
        "get_secret_value": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "value_b64": "dGVzdA==",
            "hypervisor_ref": "default",
        },
        "undefine_secret": {
            "source": "libvirt",
            "timestamp": "<timestamp>",
            "uuid": "00000000-0000-0000-0000-000000000001",
            "status": "undefined",
            "hypervisor_ref": "default",
        },
    }


def test_phase4_audit_log_contract_snapshot(tmp_path: Path, cfg_readonly: ServerConfig):
    audit_path = tmp_path / "audit.log"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "request_id": "req-1",
                        "actor": "tester",
                        "timestamp": "2026-05-13T00:00:00+00:00",
                        "tool_name": "get_domain",
                        "target_ref": "mcp_test_vm1",
                        "hypervisor_ref": "default",
                        "result": "success",
                    }
                ),
                "not-json",
                json.dumps(
                    {
                        "request_id": "req-2",
                        "actor": "tester",
                        "timestamp": "2026-05-13T00:01:00+00:00",
                        "tool_name": "set_secret_value",
                        "target_ref": "secret-1",
                        "hypervisor_ref": "default",
                        "result": "error",
                        "error_code": "MUTATION_DISABLED",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = host_tools.get_audit_log(
        cfg_readonly,
        str(audit_path),
        limit=2,
        tool_name=None,
        result_filter=None,
        since=None,
    )

    assert _contract_snapshot(result) == {
        "source": "server",
        "timestamp": "<timestamp>",
        "items": [
            {
                "request_id": "req-2",
                "actor": "tester",
                "timestamp": "<timestamp>",
                "tool_name": "set_secret_value",
                "target_ref": "secret-1",
                "hypervisor_ref": "default",
                "result": "error",
                "error_code": "MUTATION_DISABLED",
            },
            {
                "request_id": "req-1",
                "actor": "tester",
                "timestamp": "<timestamp>",
                "tool_name": "get_domain",
                "target_ref": "mcp_test_vm1",
                "hypervisor_ref": "default",
                "result": "success",
            },
        ],
        "total_count": 2,
        "filters": {
            "tool_name": None,
            "result": None,
            "since": None,
            "limit": 2,
        },
    }


def test_server_list_tools_contains_phase4_entries(tmp_path: Path):
    cfg = ServerConfig.from_env()
    cfg.audit_log_path = str(tmp_path / "audit.log")
    server = LibvirtMCPServer(config=cfg)
    tools = server.list_tools()

    for name in (
        "validate_domain_xml",
        "update_domain_device_xml",
        "get_volume_xml",
        "get_volume_backing_chain",
        "get_audit_log",
        "get_qmp_policy",
        "list_secrets",
        "get_secret",
        "define_secret_xml",
        "set_secret_value",
        "get_secret_value",
        "undefine_secret",
    ):
        assert name in tools
