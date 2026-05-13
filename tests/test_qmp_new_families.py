"""Unit tests for new QMP tool families: CPU hotplug, memory devices,
block mirror/bitmaps, netdev/chardev, migration telemetry."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
from libvirt_mcp_server.config import ServerConfig
from libvirt_mcp_server.errors import MCPError
from libvirt_mcp_server.tools import qmp_tools


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(*, allow_qmp: bool = True, allow_mutations: bool = False) -> ServerConfig:
    cfg = MagicMock(spec=ServerConfig)
    cfg.allow_qmp = allow_qmp
    cfg.allow_mutations = allow_mutations
    return cfg


def _mock_execute_return(command: str, domain_ref: str = "vm1") -> dict:
    return {
        "source": "qmp",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "domain_ref": domain_ref,
        "command": command,
        "response": {},
    }


# ---------------------------------------------------------------------------
# 1. qmp_query_migrate — disabled / allowed
# ---------------------------------------------------------------------------


def test_qmp_query_migrate_disabled():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_query_migrate(config, adapter, domain_ref="vm1", hypervisor_ref=None)
        assert exc.value.code == "QMP_DISABLED"

    asyncio.run(_run())


def test_qmp_query_migrate_calls_correct_command():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("query-migrate"))
        config = _config(allow_qmp=True)
        result = await qmp_tools.qmp_query_migrate(config, adapter, domain_ref="vm1", hypervisor_ref="hv1")
        adapter.execute.assert_called_once_with(domain_ref="vm1", command="query-migrate", arguments={})
        assert result["hypervisor_ref"] == "hv1"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. qmp_query_migrate_capabilities
# ---------------------------------------------------------------------------


def test_qmp_query_migrate_capabilities_calls_correct_command():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("query-migrate-capabilities"))
        config = _config(allow_qmp=True)
        result = await qmp_tools.qmp_query_migrate_capabilities(config, adapter, domain_ref="vm1", hypervisor_ref=None)
        adapter.execute.assert_called_once_with(domain_ref="vm1", command="query-migrate-capabilities", arguments={})
        assert result["source"] == "qmp"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. qmp_cpu_add — mutations disabled / allowed
# ---------------------------------------------------------------------------


def test_qmp_cpu_add_mutations_disabled():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_cpu_add(config, adapter, domain_ref="vm1", cpu_index=1, hypervisor_ref=None)
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


def test_qmp_cpu_add_calls_correct_command():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("cpu-add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        result = await qmp_tools.qmp_cpu_add(config, adapter, domain_ref="vm1", cpu_index=2, hypervisor_ref=None)
        adapter.execute.assert_called_once_with(domain_ref="vm1", command="cpu-add", arguments={"id": 2})
        assert result["hypervisor_ref"] == "default"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. qmp_object_add — props merged correctly
# ---------------------------------------------------------------------------


def test_qmp_object_add_props_merged():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("object-add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_object_add(
            config, adapter,
            domain_ref="vm1",
            qom_type="memory-backend-ram",
            obj_id="mem0",
            props={"size": 1073741824},
            hypervisor_ref=None,
        )
        call_args = adapter.execute.call_args
        assert call_args.kwargs["command"] == "object-add"
        arguments = call_args.kwargs["arguments"]
        assert arguments["qom-type"] == "memory-backend-ram"
        assert arguments["id"] == "mem0"
        assert arguments["size"] == 1073741824

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. qmp_object_del — correct arguments
# ---------------------------------------------------------------------------


def test_qmp_object_del_correct_arguments():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("object-del"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_object_del(config, adapter, domain_ref="vm1", obj_id="mem0", hypervisor_ref=None)
        adapter.execute.assert_called_once_with(domain_ref="vm1", command="object-del", arguments={"id": "mem0"})

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. qmp_drive_mirror — mutations gate + format/sync in arguments
# ---------------------------------------------------------------------------


def test_qmp_drive_mirror_mutations_gate():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_drive_mirror(
                config, adapter,
                domain_ref="vm1", device="vda", target="/tmp/mirror.qcow2", hypervisor_ref=None
            )
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


def test_qmp_drive_mirror_arguments_include_format_sync():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("drive-mirror"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_drive_mirror(
            config, adapter,
            domain_ref="vm1",
            device="vda",
            target="/tmp/mirror.qcow2",
            format="raw",
            sync="top",
            speed=0,
            hypervisor_ref=None,
        )
        call_args = adapter.execute.call_args
        arguments = call_args.kwargs["arguments"]
        assert arguments["device"] == "vda"
        assert arguments["format"] == "raw"
        assert arguments["sync"] == "top"
        assert "speed" not in arguments  # speed=0 should not be included

    asyncio.run(_run())


def test_qmp_drive_mirror_speed_included_when_nonzero():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("drive-mirror"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_drive_mirror(
            config, adapter,
            domain_ref="vm1",
            device="vda",
            target="/tmp/mirror.qcow2",
            speed=1048576,
            hypervisor_ref=None,
        )
        call_args = adapter.execute.call_args
        assert call_args.kwargs["arguments"]["speed"] == 1048576

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. qmp_block_dirty_bitmap_add — mutations gate + persistent in args
# ---------------------------------------------------------------------------


def test_qmp_block_dirty_bitmap_add_mutations_gate():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_block_dirty_bitmap_add(
                config, adapter, domain_ref="vm1", node="vda", name="backup", hypervisor_ref=None
            )
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


def test_qmp_block_dirty_bitmap_add_persistent_flag():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("block-dirty-bitmap-add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_block_dirty_bitmap_add(
            config, adapter,
            domain_ref="vm1", node="vda", name="backup", persistent=False, hypervisor_ref=None
        )
        arguments = adapter.execute.call_args.kwargs["arguments"]
        assert arguments["node"] == "vda"
        assert arguments["name"] == "backup"
        assert arguments["persistent"] is False

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. qmp_netdev_add — netdev_opts merged into arguments
# ---------------------------------------------------------------------------


def test_qmp_netdev_add_opts_merged():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("netdev_add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_netdev_add(
            config, adapter,
            domain_ref="vm1",
            netdev_type="user",
            netdev_id="net0",
            netdev_opts={"hostfwd": "tcp::2222-:22"},
            hypervisor_ref=None,
        )
        arguments = adapter.execute.call_args.kwargs["arguments"]
        assert arguments["type"] == "user"
        assert arguments["id"] == "net0"
        assert arguments["hostfwd"] == "tcp::2222-:22"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. qmp_chardev_add — backend dict in arguments
# ---------------------------------------------------------------------------


def test_qmp_chardev_add_backend_in_arguments():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("chardev-add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        backend = {"type": "socket", "data": {"path": "/tmp/serial.sock", "server": True}}
        await qmp_tools.qmp_chardev_add(
            config, adapter,
            domain_ref="vm1",
            chardev_id="serial0",
            backend=backend,
            hypervisor_ref="hv1",
        )
        arguments = adapter.execute.call_args.kwargs["arguments"]
        assert arguments["id"] == "serial0"
        assert arguments["backend"] == backend
        assert adapter.execute.call_args.kwargs["command"] == "chardev-add"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 10. qmp_chardev_remove — correct command and id
# ---------------------------------------------------------------------------


def test_qmp_chardev_remove_correct_command():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("chardev-remove"))
        config = _config(allow_qmp=True, allow_mutations=True)
        result = await qmp_tools.qmp_chardev_remove(
            config, adapter, domain_ref="vm1", chardev_id="serial0", hypervisor_ref=None
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1", command="chardev-remove", arguments={"id": "serial0"}
        )
        assert result["hypervisor_ref"] == "default"

    asyncio.run(_run())
