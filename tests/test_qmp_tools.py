"""Unit tests for QMP typed tool wrappers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import qmp_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_QUERY_TOOLS = [
    ("qmp_query_status", "query-status"),
    ("qmp_query_version", "query-version"),
    ("qmp_query_cpus", "query-cpus-fast"),
    ("qmp_query_balloon", "query-balloon"),
    ("qmp_query_block", "query-block"),
    ("qmp_query_blockstats", "query-blockstats"),
    ("qmp_query_pci", "query-pci"),
    ("qmp_query_iothreads", "query-iothreads"),
    ("qmp_query_chardev", "query-chardev"),
    ("qmp_query_vnc", "query-vnc"),
    ("qmp_query_block_jobs", "query-block-jobs"),
    ("qmp_query_machines", "query-machines"),
]


def _config(*, allow_qmp: bool = True, allow_mutations: bool = False) -> ServerConfig:
    cfg = MagicMock(spec=ServerConfig)
    cfg.allow_qmp = allow_qmp
    cfg.allow_mutations = allow_mutations
    cfg.qmp_event_log_path = "./qmp-events.log"
    return cfg


def _mock_execute_return(command: str) -> dict:
    return {
        "source": "qmp",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": "vm1",
        "command": command,
        "response": {},
    }


# ---------------------------------------------------------------------------
# Test 1: All query tools call through and return hypervisor_ref
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name,qmp_command", _QUERY_TOOLS)
def test_qmp_query_tools_read_only(tool_name: str, qmp_command: str):
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return(qmp_command))
        config = _config(allow_qmp=True)
        fn = getattr(qmp_tools, tool_name)
        result = await fn(config, adapter, domain_ref="vm1", hypervisor_ref="hv1")
        adapter.execute.assert_called_once_with(domain_ref="vm1", command=qmp_command, arguments={})
        assert result["hypervisor_ref"] == "hv1"
        assert result["source"] == "qmp"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 2: All query tools raise QMP_DISABLED when allow_qmp=False
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name,_", _QUERY_TOOLS)
def test_qmp_query_tools_disabled(tool_name: str, _):
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=False)
        fn = getattr(qmp_tools, tool_name)
        with pytest.raises(MCPError) as exc:
            await fn(config, adapter, domain_ref="vm1", hypervisor_ref=None)
        assert exc.value.code == "QMP_DISABLED"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 3: qmp_balloon raises MUTATIONS_DISABLED when allow_mutations=False
# ---------------------------------------------------------------------------


def test_qmp_balloon_disabled():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_balloon(config, adapter, domain_ref="vm1", balloon_mb=512, hypervisor_ref=None)
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 4: qmp_balloon calls execute with correct byte value
# ---------------------------------------------------------------------------


def test_qmp_balloon_allowed():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("balloon"))
        config = _config(allow_qmp=True, allow_mutations=True)
        result = await qmp_tools.qmp_balloon(config, adapter, domain_ref="vm1", balloon_mb=512, hypervisor_ref="hv1")
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="balloon",
            arguments={"value": 512 * 1024 * 1024},
        )
        assert result["hypervisor_ref"] == "hv1"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 5: qmp_block_stream raises MUTATIONS_DISABLED when allow_mutations=False
# ---------------------------------------------------------------------------


def test_qmp_block_stream_mutation_gate():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_block_stream(config, adapter, domain_ref="vm1", device="vda", hypervisor_ref=None)
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 6: qmp_block_job_cancel passes force=True through
# ---------------------------------------------------------------------------


def test_qmp_block_job_cancel_force():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("block-job-cancel"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_block_job_cancel(config, adapter, domain_ref="vm1", device="vda", force=True, hypervisor_ref=None)
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="block-job-cancel",
            arguments={"device": "vda", "force": True},
        )

    asyncio.run(_run())


def test_qmp_events_persist_and_replay(tmp_path: Path):
    async def _run():
        event_log = tmp_path / "qmp-events.log"
        adapter = MagicMock(spec=QMPAdapter)
        adapter.collect_events = AsyncMock(
            return_value={
                "source": "qmp",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "domain_ref": "vm1",
                "events": [{"event": "BLOCK_JOB_COMPLETED", "data": {"device": "vda"}}],
                "total_count": 1,
            }
        )
        config = _config(allow_qmp=True)
        config.qmp_event_log_path = str(event_log)

        result = await qmp_tools.qmp_events(
            config,
            adapter,
            domain_ref="vm1",
            event_types=[],
            since=None,
            timeout_seconds=0.1,
            hypervisor_ref=None,
        )
        assert result["total_count"] == 1

        replay = qmp_tools.qmp_replay_events(
            config,
            domain_ref="vm1",
            event_types=["BLOCK_JOB_COMPLETED"],
            since=None,
            limit=10,
            hypervisor_ref=None,
        )
        assert replay["total_count"] == 1
        assert replay["items"][0]["event"]["event"] == "BLOCK_JOB_COMPLETED"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 7: qmp_device_add merges driver, device_id, and device_opts
# ---------------------------------------------------------------------------


def test_qmp_device_add():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("device_add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_device_add(
            config, adapter,
            domain_ref="vm1",
            driver="virtio-net-pci",
            device_id="net0",
            device_opts={"netdev": "hostnet0"},
            hypervisor_ref=None,
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="device_add",
            arguments={"driver": "virtio-net-pci", "id": "net0", "netdev": "hostnet0"},
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 8: qmp_device_del passes {"id": device_id}
# ---------------------------------------------------------------------------


def test_qmp_device_del():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("device_del"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_device_del(config, adapter, domain_ref="vm1", device_id="net0", hypervisor_ref=None)
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="device_del",
            arguments={"id": "net0"},
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 9: QMPAdapter.collect_events gathers events from mock socket
# ---------------------------------------------------------------------------


def test_collect_events_method(tmp_path: Path):
    async def _event_mock_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        writer.write(
            json.dumps({"QMP": {"version": {"qemu": {"major": 8, "minor": 2, "micro": 0}}}}).encode() + b"\n"
        )
        await writer.drain()
        _line = await reader.readline()  # read qmp_capabilities
        writer.write(json.dumps({"return": {}}).encode() + b"\n")
        await writer.drain()
        writer.write(
            json.dumps({"event": "STOP", "timestamp": {"seconds": 1, "microseconds": 0}, "data": {}}).encode() + b"\n"
        )
        await writer.drain()
        writer.write(
            json.dumps({"event": "RESUME", "timestamp": {"seconds": 2, "microseconds": 0}, "data": {}}).encode() + b"\n"
        )
        await writer.drain()
        writer.close()

    async def _run():
        socket_path = tmp_path / "vm1.qmp"
        server = await asyncio.start_unix_server(_event_mock_server, path=str(socket_path))
        try:
            adapter = QMPAdapter(
                socket_dir=str(tmp_path),
                allowlist={"query-status"},
                enabled=True,
            )
            result = await adapter.collect_events(domain_ref="vm1", timeout_seconds=2.0)
            assert result["source"] == "qmp"
            assert result["domain_ref"] == "vm1"
            assert result["total_count"] == 2
            event_names = [e["event"] for e in result["events"]]
            assert "STOP" in event_names
            assert "RESUME" in event_names
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test 10: qmp_events tool calls collect_events and passes timeout_seconds
# ---------------------------------------------------------------------------


def test_qmp_events_tool():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.collect_events = AsyncMock(return_value={
            "source": "qmp",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "domain_ref": "vm1",
            "event_types_filter": [],
            "events": [],
            "total_count": 0,
        })
        config = _config(allow_qmp=True)
        result = await qmp_tools.qmp_events(
            config, adapter,
            domain_ref="vm1",
            event_types=[],
            since=None,
            hypervisor_ref="hv1",
            timeout_seconds=5.0,
        )
        adapter.collect_events.assert_called_once_with(
            domain_ref="vm1",
            timeout_seconds=5.0,
            event_types=None,
        )
        assert result["hypervisor_ref"] == "hv1"
        assert result["since"] is None

    asyncio.run(_run())
