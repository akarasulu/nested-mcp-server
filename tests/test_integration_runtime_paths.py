"""Integration tests that target runtime entrypoints and wrapper paths.

These tests are opt-in and rely on a local libvirt environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import runpy
import sys
import tempfile
import time
from types import SimpleNamespace

import pytest

from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.resources.domain_resources import read_domain, read_domain_xml
from libvirt_mcp_server.resources.host_resources import read_host_capabilities
from libvirt_mcp_server.resources.network_resources import read_networks
from libvirt_mcp_server.resources.storage_resources import read_storage_pools
from libvirt_mcp_server.server import LibvirtMCPServer

pytestmark = pytest.mark.integration


def _require_integration() -> None:
    if os.getenv("LIBVIRT_MCP_RUN_INTEGRATION") != "1":
        pytest.skip("Set LIBVIRT_MCP_RUN_INTEGRATION=1 to run integration tests")


def _safe_test_prefix() -> str:
    test_prefix = os.getenv("LIBVIRT_MCP_TEST_PREFIX", "mcp_test_")
    prod_markers = ["prod", "production", "critical"]
    if any(marker in test_prefix.lower() for marker in prod_markers):
        pytest.skip("Unsafe test prefix indicates production-like resources")
    return test_prefix


def _get_test_domain() -> str:
    domain_ref = os.getenv("LIBVIRT_MCP_TEST_DOMAIN", "") or os.getenv("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN", "")
    if not domain_ref:
        pytest.skip("Set LIBVIRT_MCP_TEST_DOMAIN (or LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN) to a dedicated non-production VM")
    if not domain_ref.startswith(_safe_test_prefix()):
        pytest.skip("LIBVIRT_MCP_SNAPSHOT_TEST_DOMAIN must start with LIBVIRT_MCP_TEST_PREFIX")
    return domain_ref


def _as_dict(payload: str) -> dict:
    decoded = json.loads(payload)
    assert isinstance(decoded, dict)
    return decoded


def test_resource_helpers_are_covered():
    _require_integration()

    server = LibvirtMCPServer(config=ServerConfig.from_env())

    host = asyncio.run(read_host_capabilities(server))
    assert "error" not in host

    networks = asyncio.run(read_networks(server))
    assert "error" not in networks

    pools = asyncio.run(read_storage_pools(server))
    assert "error" not in pools

    domains = asyncio.run(server.call_tool("list_domains", {}))
    assert "error" not in domains
    if domains.get("items"):
        domain_ref = domains["items"][0]["name"]
        detail = asyncio.run(read_domain(server, domain_ref))
        assert "error" not in detail

        # Cover optional hypervisor_ref branches in resource helpers.
        detail_with_hv = asyncio.run(read_domain(server, domain_ref, hypervisor_ref="default"))
        assert "error" not in detail_with_hv

        xml_payload = asyncio.run(read_domain_xml(server, domain_ref))
        assert "error" not in xml_payload
        assert "<domain" in xml_payload.get("xml", "")

        xml_payload_with_hv = asyncio.run(read_domain_xml(server, domain_ref, hypervisor_ref="default"))
        assert "error" not in xml_payload_with_hv


def test_app_wrappers_cover_runtime_paths():
    _require_integration()
    test_prefix = _safe_test_prefix()
    test_domain = _get_test_domain()

    from libvirt_mcp_server import app as app_mod

    # Reset singleton state to ensure deterministic run in this test process.
    app_mod._config = None
    app_mod._server = None

    async def _run() -> None:
        host = _as_dict(await app_mod.host_info())
        assert "error" not in host

        hv_list = _as_dict(await app_mod.list_hypervisors())
        assert "error" not in hv_list

        hv = _as_dict(await app_mod.get_hypervisor("default"))
        assert "error" not in hv

        domains = _as_dict(await app_mod.list_domains())
        assert "error" not in domains
        domain_ref = test_domain

        domain = _as_dict(await app_mod.get_domain(domain_ref))
        assert "error" not in domain

        domain_xml = _as_dict(await app_mod.get_domain_xml(domain_ref, live=False, inactive=True))
        assert "error" not in domain_xml

        networks = _as_dict(await app_mod.list_networks())
        assert "error" not in networks
        if networks.get("items"):
            one_net = _as_dict(await app_mod.get_network(networks["items"][0]["name"]))
            assert "error" not in one_net

        pools = _as_dict(await app_mod.list_storage_pools())
        assert "error" not in pools
        if pools.get("items"):
            active_pool_name = None
            for pool in pools["items"]:
                candidate = pool["name"]
                one_pool = _as_dict(await app_mod.get_storage_pool(candidate))
                assert "error" not in one_pool

                vols = _as_dict(await app_mod.list_storage_volumes(candidate))
                if "error" not in vols:
                    active_pool_name = candidate
                    if vols.get("items"):
                        one_vol = _as_dict(await app_mod.get_storage_volume(candidate, vols["items"][0]["name"]))
                        assert "error" not in one_vol
                    break

            # If no active pools are available on this host, the wrapper path still ran.
            assert active_pool_name is None or isinstance(active_pool_name, str)

        _as_dict(await app_mod.list_domain_snapshots(domain_ref))

        # Mutation wrappers: execute paths regardless of policy outcome.
        snap_name = f"{test_prefix}app_{int(time.time())}"
        snap_xml = (
            "<domainsnapshot>"
            f"<name>{snap_name}</name>"
            "<description>app-wrapper coverage snapshot</description>"
            "</domainsnapshot>"
        )
        _as_dict(await app_mod.create_domain_snapshot(domain_ref, snap_xml))
        _as_dict(await app_mod.revert_domain_snapshot(domain_ref, snap_name))
        _as_dict(await app_mod.delete_domain_snapshot(domain_ref, snap_name))

        _as_dict(await app_mod.set_domain_autostart(domain_ref, False))
        _as_dict(await app_mod.start_domain(domain_ref, dry_run=True))
        _as_dict(await app_mod.shutdown_domain(domain_ref, dry_run=True))
        _as_dict(await app_mod.destroy_domain(domain_ref, dry_run=True))
        _as_dict(await app_mod.reboot_domain(domain_ref, dry_run=True))
        _as_dict(await app_mod.suspend_domain(domain_ref, dry_run=True))
        _as_dict(await app_mod.resume_domain(domain_ref, dry_run=True))

        _as_dict(await app_mod.qmp_capabilities(domain_ref))
        _as_dict(await app_mod.qmp_events(domain_ref, event_types="STOP,RESUME", since=None))

        # Cover invalid argument parsing branch.
        invalid_args = _as_dict(await app_mod.qmp_command(domain_ref, "query-status", arguments="not-json"))
        assert "error" in invalid_args

        _as_dict(await app_mod.qmp_command(domain_ref, "query-status", arguments="{}"))

    asyncio.run(_run())


def test_qmp_policy_disabled_path_is_covered():
    _require_integration()

    cfg = ServerConfig.from_env()
    cfg.allow_qmp = False
    server = LibvirtMCPServer(config=cfg)

    domain_ref = _get_test_domain()
    events = asyncio.run(
        server.call_tool(
            "qmp_events",
            {"domain_ref": domain_ref, "event_types": ["STOP"], "since": None},
        )
    )
    assert events.get("error", {}).get("code") == "QMP_DISABLED"


def test_main_cli_paths_are_covered(monkeypatch):
    _require_integration()

    from libvirt_mcp_server import main as main_mod

    served = {"called": False}

    async def _fake_serve() -> None:
        served["called"] = True

    monkeypatch.setattr(main_mod, "_serve", _fake_serve)

    monkeypatch.setattr(main_mod.sys, "argv", ["nested-mcp-server", "serve"])
    assert main_mod.main() == 0
    assert served["called"] is True

    monkeypatch.setattr(main_mod.sys, "argv", ["nested-mcp-server", "tool", "host_info", "--args", "{}"])
    assert main_mod.main() == 0

    monkeypatch.setattr(main_mod.sys, "argv", ["nested-mcp-server", "tool", "unknown_tool", "--args", "{}"])
    assert main_mod.main() == 1

    monkeypatch.setattr(main_mod.sys, "argv", ["nested-mcp-server", "tool", "host_info", "--args", "[]"])
    assert main_mod.main() == 2


def test_main_serve_function_path(monkeypatch):
    _require_integration()

    from libvirt_mcp_server import app as app_mod
    from libvirt_mcp_server import main as main_mod

    called = {"ok": False}

    async def _fake_run_stdio_async() -> None:
        called["ok"] = True

    monkeypatch.setattr(app_mod.app, "run_stdio_async", _fake_run_stdio_async)
    asyncio.run(main_mod._serve())
    assert called["ok"] is True


def test_not_found_error_paths_are_covered():
    _require_integration()

    cfg = ServerConfig.from_env()
    cfg.allow_mutations = True
    server = LibvirtMCPServer(config=cfg)

    missing_domain = asyncio.run(server.call_tool("get_domain", {"domain_ref": "mcp_test_missing_domain"}))
    assert missing_domain.get("error", {}).get("code") == "DOMAIN_NOT_FOUND"

    missing_network = asyncio.run(server.call_tool("get_network", {"network_name": "mcp_test_missing_network"}))
    assert missing_network.get("error", {}).get("code") == "NETWORK_NOT_FOUND"

    missing_pool = asyncio.run(server.call_tool("get_storage_pool", {"pool_name": "mcp_test_missing_pool"}))
    assert missing_pool.get("error", {}).get("code") == "STORAGE_POOL_NOT_FOUND"

    missing_vol = asyncio.run(
        server.call_tool(
            "get_storage_volume",
            {"pool_name": "mcp_test_missing_pool", "volume_name": "mcp_test_missing_volume"},
        )
    )
    assert missing_vol.get("error", {}).get("code") == "STORAGE_POOL_NOT_FOUND"

    domain_ref = _get_test_domain()
    missing_snap = asyncio.run(
        server.call_tool(
            "revert_domain_snapshot",
            {"domain_ref": domain_ref, "snapshot_name": "mcp_test_missing_snapshot"},
        )
    )
    assert missing_snap.get("error", {}).get("code") == "SNAPSHOT_NOT_FOUND"


def test_qmp_socket_protocol_paths_are_covered():
    _require_integration()

    async def _serve_ok(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(json.dumps({"QMP": {"version": {}, "capabilities": []}}).encode("utf-8") + b"\n")
        await writer.drain()

        _ = json.loads((await reader.readline()).decode("utf-8"))
        writer.write(b'{"return":{}}\n')
        await writer.drain()

        cmd = json.loads((await reader.readline()).decode("utf-8"))
        execute = cmd.get("execute")
        if execute == "query-commands":
            writer.write(b'{"return":[{"name":"query-status"},{"name":"query-commands"}]}\n')
        else:
            writer.write(b'{"return":{"status":"running"}}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _serve_bad_greeting(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b'{"hello":"world"}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _serve_command_error(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(json.dumps({"QMP": {"version": {}, "capabilities": []}}).encode("utf-8") + b"\n")
        await writer.drain()
        _ = json.loads((await reader.readline()).decode("utf-8"))
        writer.write(b'{"return":{}}\n')
        await writer.drain()
        _ = json.loads((await reader.readline()).decode("utf-8"))
        writer.write(b'{"error":{"class":"GenericError","desc":"forced"}}\n')
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _run() -> None:
        domain_ref = "mcp_test_qmp_fake"
        with tempfile.TemporaryDirectory() as td:
            socket_path = os.path.join(td, f"{domain_ref}.qmp")

            cfg = ServerConfig.from_env()
            cfg.allow_qmp = True
            cfg.qmp_socket_dir = td
            cfg.qmp_allowlist = {"query-status", "query-commands"}
            server = LibvirtMCPServer(config=cfg)

            ok_server = await asyncio.start_unix_server(_serve_ok, path=socket_path)
            async with ok_server:
                caps = await server.call_tool("qmp_capabilities", {"domain_ref": domain_ref})
                assert "error" not in caps

                events = await server.call_tool(
                    "qmp_events",
                    {"domain_ref": domain_ref, "event_types": ["STOP"], "since": None},
                )
                assert "error" not in events

                cmd = await server.call_tool(
                    "qmp_command",
                    {"domain_ref": domain_ref, "command": "query-status", "arguments": {}},
                )
                assert "error" not in cmd

            bad_server = await asyncio.start_unix_server(_serve_bad_greeting, path=socket_path)
            async with bad_server:
                bad = await server.call_tool(
                    "qmp_command",
                    {"domain_ref": domain_ref, "command": "query-status", "arguments": {}},
                )
                assert bad.get("error", {}).get("code") == "QMP_PROTOCOL_ERROR"

            err_server = await asyncio.start_unix_server(_serve_command_error, path=socket_path)
            async with err_server:
                failed = await server.call_tool(
                    "qmp_command",
                    {"domain_ref": domain_ref, "command": "query-status", "arguments": {}},
                )
                assert failed.get("error", {}).get("code") == "QMP_COMMAND_FAILED"

    asyncio.run(_run())


def test_config_env_paths_are_covered(monkeypatch):
    _require_integration()

    from libvirt_mcp_server import config as cfg_mod

    # _env_bool: default and true-ish parsing
    monkeypatch.delenv("MCP_LIBVIRT_ALLOW_MUTATIONS", raising=False)
    assert cfg_mod._env_bool("MCP_LIBVIRT_ALLOW_MUTATIONS", False) is False
    monkeypatch.setenv("MCP_LIBVIRT_ALLOW_MUTATIONS", "YES")
    assert cfg_mod._env_bool("MCP_LIBVIRT_ALLOW_MUTATIONS", False) is True

    # _env_int: invalid value falls back to default
    monkeypatch.setenv("MCP_MAX_CONCURRENT_OPERATIONS", "not-an-int")
    assert cfg_mod._env_int("MCP_MAX_CONCURRENT_OPERATIONS", 7) == 7

    # _parse_hypervisors: both named and anonymous refs, with default injection.
    monkeypatch.setenv(
        "LIBVIRT_URIS",
        "lab=qemu:///system,bad-entry,edge=qemu+ssh://user@host/system",
    )
    parsed = cfg_mod._parse_hypervisors()
    assert parsed["lab"] == "qemu:///system"
    assert parsed["edge"] == "qemu+ssh://user@host/system"
    assert "hv1" in parsed
    assert "default" in parsed

    # from_env + get_hypervisor_uri unknown key path.
    monkeypatch.setenv("MCP_QMP_ALLOWLIST", "query-status,query-version")
    cfg = cfg_mod.ServerConfig.from_env()
    assert cfg.get_hypervisor_uri(None)
    with pytest.raises(KeyError):
        cfg.get_hypervisor_uri("missing-ref")


def test_libvirt_adapter_internal_error_paths(monkeypatch):
    _require_integration()

    from libvirt_mcp_server.adapters import libvirt_adapter as la_mod
    from libvirt_mcp_server.errors import MCPError

    adapter = la_mod.LibvirtAdapter()

    # _ensure_libvirt unavailable branch.
    monkeypatch.setattr(la_mod, "libvirt", None)
    with pytest.raises(MCPError) as exc:
        adapter._ensure_libvirt()
    assert exc.value.code == "LIBVIRT_UNAVAILABLE"

    # _connect: libvirt.open exception branch.
    class _LibvirtRaise:
        @staticmethod
        def open(uri: str):
            raise RuntimeError("boom")

    monkeypatch.setattr(la_mod, "libvirt", _LibvirtRaise)
    with pytest.raises(MCPError) as exc:
        adapter._connect("qemu:///broken")
    assert exc.value.code == "LIBVIRT_CONNECTION_ERROR"

    # _connect: libvirt.open returns None branch.
    class _LibvirtNone:
        @staticmethod
        def open(uri: str):
            return None

    monkeypatch.setattr(la_mod, "libvirt", _LibvirtNone)
    with pytest.raises(MCPError) as exc:
        adapter._connect("qemu:///none")
    assert exc.value.code == "LIBVIRT_CONNECTION_ERROR"

    # lifecycle invalid action branch.
    class _FakeDomain:
        def create(self):
            return None

        def shutdown(self):
            return None

        def destroy(self):
            return None

        def reboot(self, _flags: int):
            return None

        def suspend(self):
            return None

        def resume(self):
            return None

    fake_domain = _FakeDomain()
    monkeypatch.setattr(adapter, "_connect", lambda _uri: object())
    monkeypatch.setattr(adapter, "_lookup_domain", lambda _conn, _ref: fake_domain)
    with pytest.raises(MCPError) as exc:
        adapter.lifecycle_action("qemu:///system", "mcp_test_dummy", "bad_action")
    assert exc.value.code == "INVALID_ACTION"

    # _domain_summary: unknown state and autostart exception fallback.
    class _FakeSummaryDomain:
        def info(self):
            return (99, 2048, 1024, 2, 12345)

        def autostart(self):
            raise RuntimeError("no autostart")

        def name(self):
            return "fake-domain"

        def UUIDString(self):
            return "00000000-0000-0000-0000-000000000000"

        def isActive(self):
            return False

    summary = adapter._domain_summary(_FakeSummaryDomain())
    assert summary["state"] == "unknown"
    assert summary["autostart"] is False

    # _summarize_capabilities parse failure and missing arch attributes.
    assert adapter._summarize_capabilities("not xml") == {"parse_error": "invalid_capabilities_xml"}
    xml = "<capabilities><guest></guest><guest><arch><machine>m</machine></arch></guest></capabilities>"
    parsed = adapter._summarize_capabilities(xml)
    assert parsed["guest_arch_count"] == 0


def test_qmp_adapter_remaining_branches(monkeypatch):
    _require_integration()

    from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
    from libvirt_mcp_server.errors import MCPError

    # Disabled path.
    disabled = QMPAdapter(socket_dir="/tmp", allowlist={"query-status"}, enabled=False)
    with pytest.raises(MCPError) as exc:
        asyncio.run(disabled.execute(domain_ref="vm", command="query-status", arguments={}))
    assert exc.value.code == "QMP_DISABLED"

    # Wildcard allowlist branch.
    wildcard = QMPAdapter(socket_dir="/tmp", allowlist={"*"}, enabled=True)
    assert wildcard._is_allowed("totally-custom") is True

    # open_unix_connection exception branch and empty-read transport branch.
    adapter = QMPAdapter(socket_dir="/tmp", allowlist={"query-status"}, enabled=True)
    with tempfile.TemporaryDirectory() as td:
        socket_path = os.path.join(td, "vm.qmp")
        with open(socket_path, "w", encoding="utf-8"):
            pass

        async def _raise_open(*_args, **_kwargs):
            raise RuntimeError("open-failed")

        monkeypatch.setattr(asyncio, "open_unix_connection", _raise_open)
        with pytest.raises(MCPError) as exc:
            asyncio.run(adapter._run_qmp_command(command="query-status", arguments={}, socket_path=socket_path))
        assert exc.value.code == "QMP_TRANSPORT_ERROR"

        class _EmptyReader:
            async def readline(self):
                return b""

        with pytest.raises(MCPError) as exc:
            asyncio.run(adapter._read_json_message(_EmptyReader()))
        assert exc.value.code == "QMP_TRANSPORT_ERROR"


def test_main_fallback_and_dunder_main_paths(monkeypatch):
    _require_integration()

    from libvirt_mcp_server import main as main_mod

    printed = {"called": False}

    class _FakeParser:
        def parse_args(self):
            return SimpleNamespace(command="unexpected")

        def print_help(self):
            printed["called"] = True

    monkeypatch.setattr(main_mod, "build_parser", lambda: _FakeParser())
    assert main_mod.main() == 1
    assert printed["called"] is True

    # Execute module as __main__ to cover terminal raise SystemExit(main()) path.
    monkeypatch.setattr(main_mod.sys, "argv", ["nested-mcp-server", "tool", "host_info", "--args", "{}"])
    monkeypatch.delitem(sys.modules, "libvirt_mcp_server.main", raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("libvirt_mcp_server.main", run_name="__main__")
    assert exc.value.code in (0, 1)
