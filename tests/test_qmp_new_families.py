"""Unit tests for new QMP tool families: CPU hotplug, memory devices,
block mirror/backup/bitmaps, NBD export, netdev/chardev, migration telemetry."""

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
    cfg.qmp_event_log_path = "./qmp-events.log"
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
# 6B. qmp_blockdev_backup / NBD export helpers
# ---------------------------------------------------------------------------


def test_qmp_blockdev_backup_arguments_include_job_and_speed():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("blockdev-backup"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_blockdev_backup(
            config,
            adapter,
            domain_ref="vm1",
            device="drive0",
            target="backup0",
            sync="incremental",
            job_id="backup-job-1",
            speed=1048576,
            hypervisor_ref=None,
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="blockdev-backup",
            arguments={
                "device": "drive0",
                "target": "backup0",
                "sync": "incremental",
                "job-id": "backup-job-1",
                "speed": 1048576,
            },
        )

    asyncio.run(_run())


def test_qmp_blockdev_backup_mutations_gate():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        config = _config(allow_qmp=True, allow_mutations=False)
        with pytest.raises(MCPError) as exc:
            await qmp_tools.qmp_blockdev_backup(
                config,
                adapter,
                domain_ref="vm1",
                device="drive0",
                target="backup0",
                hypervisor_ref=None,
            )
        assert exc.value.code == "MUTATIONS_DISABLED"

    asyncio.run(_run())


def test_qmp_nbd_server_start_arguments():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("nbd-server-start"))
        config = _config(allow_qmp=True, allow_mutations=True)
        address = {"type": "unix", "data": {"path": "/tmp/mcp_test_nbd.sock"}}
        await qmp_tools.qmp_nbd_server_start(
            config,
            adapter,
            domain_ref="vm1",
            address=address,
            tls_creds="tls0",
            tls_authz="authz0",
            hypervisor_ref=None,
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="nbd-server-start",
            arguments={"addr": address, "tls-creds": "tls0", "tls-authz": "authz0"},
        )

    asyncio.run(_run())


def test_qmp_nbd_server_add_arguments():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("nbd-server-add"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_nbd_server_add(
            config,
            adapter,
            domain_ref="vm1",
            device="drive0",
            export_name="rootfs",
            writable=False,
            bitmap="dirty0",
            hypervisor_ref=None,
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="nbd-server-add",
            arguments={"device": "drive0", "writable": False, "name": "rootfs", "bitmap": "dirty0"},
        )

    asyncio.run(_run())


def test_qmp_nbd_server_remove_and_stop_arguments():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("nbd-server-remove"))
        config = _config(allow_qmp=True, allow_mutations=True)
        await qmp_tools.qmp_nbd_server_remove(
            config,
            adapter,
            domain_ref="vm1",
            export_name="rootfs",
            mode="hard",
            hypervisor_ref=None,
        )
        adapter.execute.assert_called_once_with(
            domain_ref="vm1",
            command="nbd-server-remove",
            arguments={"name": "rootfs", "mode": "hard"},
        )

        adapter.execute = AsyncMock(return_value=_mock_execute_return("nbd-server-stop"))
        await qmp_tools.qmp_nbd_server_stop(config, adapter, domain_ref="vm1", hypervisor_ref=None)
        adapter.execute.assert_called_once_with(domain_ref="vm1", command="nbd-server-stop", arguments={})

    asyncio.run(_run())


def test_plan_qmp_backup_returns_ordered_steps():
    config = _config(allow_qmp=True)
    address = {"type": "unix", "data": {"path": "/tmp/mcp_test_nbd.sock"}}

    result = qmp_tools.plan_qmp_backup(
        config,
        domain_ref="vm1",
        device="drive0",
        export_name="rootfs",
        address=address,
        bitmap="dirty0",
        writable=False,
        backup_target="backup0",
        sync="incremental",
        job_id="job0",
        speed=0,
        hypervisor_ref=None,
    )

    assert result["requires_mutations"] is True
    assert [step["tool"] for step in result["steps"]] == [
        "qmp_nbd_server_start",
        "qmp_nbd_server_add",
        "qmp_blockdev_backup",
        "stop_qmp_nbd_backup",
    ]
    assert result["steps"][2]["arguments"]["target"] == "backup0"


def test_start_qmp_nbd_backup_runs_export_and_backup():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(side_effect=[
            _mock_execute_return("nbd-server-start"),
            _mock_execute_return("nbd-server-add"),
            _mock_execute_return("blockdev-backup"),
        ])
        config = _config(allow_qmp=True, allow_mutations=True)
        address = {"type": "unix", "data": {"path": "/tmp/mcp_test_nbd.sock"}}

        result = await qmp_tools.start_qmp_nbd_backup(
            config,
            adapter,
            domain_ref="vm1",
            device="drive0",
            export_name="rootfs",
            address=address,
            bitmap="dirty0",
            writable=False,
            backup_target="backup0",
            sync="incremental",
            job_id="job0",
            speed=4096,
            cleanup_on_failure=True,
            hypervisor_ref=None,
        )

        assert result["status"] == "started"
        assert [call.kwargs["command"] for call in adapter.execute.call_args_list] == [
            "nbd-server-start",
            "nbd-server-add",
            "blockdev-backup",
        ]

    asyncio.run(_run())


def test_stop_qmp_nbd_backup_removes_export_and_stops_server():
    async def _run():
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(side_effect=[
            _mock_execute_return("nbd-server-remove"),
            _mock_execute_return("nbd-server-stop"),
        ])
        config = _config(allow_qmp=True, allow_mutations=True)

        result = await qmp_tools.stop_qmp_nbd_backup(
            config,
            adapter,
            domain_ref="vm1",
            export_name="rootfs",
            remove_export=True,
            stop_server=True,
            mode="safe",
            hypervisor_ref=None,
        )

        assert result["status"] == "stopped"
        assert [call.kwargs["command"] for call in adapter.execute.call_args_list] == [
            "nbd-server-remove",
            "nbd-server-stop",
        ]

    asyncio.run(_run())


def test_get_qmp_backup_status_combines_jobs_and_events(tmp_path):
    async def _run():
        event_log = tmp_path / "qmp-events.log"
        event_log.write_text(
            '{"domain_ref":"vm1","event":{"event":"BLOCK_JOB_COMPLETED"},"source":"qmp","timestamp":"2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8",
        )
        adapter = MagicMock(spec=QMPAdapter)
        adapter.execute = AsyncMock(return_value=_mock_execute_return("query-block-jobs"))
        config = _config(allow_qmp=True)
        config.qmp_event_log_path = str(event_log)

        result = await qmp_tools.get_qmp_backup_status(
            config,
            adapter,
            domain_ref="vm1",
            job_id="job0",
            event_limit=10,
            hypervisor_ref=None,
        )

        assert result["job_id"] == "job0"
        assert result["block_jobs"]["command"] == "query-block-jobs"
        assert result["event_count"] == 1

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
