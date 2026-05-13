import asyncio
import json
from pathlib import Path

import pytest

from libvirt_mcp_server.adapters.qmp_adapter import QMPAdapter
from libvirt_mcp_server.errors import MCPError


async def _qmp_mock_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    writer.write(json.dumps({"QMP": {"version": {"qemu": {"major": 8, "minor": 2, "micro": 0}}}}).encode() + b"\n")
    await writer.drain()

    line = await reader.readline()
    msg = json.loads(line.decode())
    if msg.get("execute") == "qmp_capabilities":
        writer.write(json.dumps({"return": {}}).encode() + b"\n")
        await writer.drain()

    line = await reader.readline()
    msg = json.loads(line.decode())
    if msg.get("execute") == "query-status":
        writer.write(json.dumps({"return": {"status": "running"}}).encode() + b"\n")
    else:
        writer.write(json.dumps({"error": {"class": "CommandNotFound"}}).encode() + b"\n")

    await writer.drain()
    writer.close()


def test_qmp_adapter_execute(tmp_path: Path):
    async def _run() -> None:
        socket_path = tmp_path / "vm1.qmp"
        server = await asyncio.start_unix_server(_qmp_mock_server, path=str(socket_path))
        try:
            adapter = QMPAdapter(socket_dir=str(tmp_path), allowlist={"query-status"}, enabled=True)
            result = await adapter.execute(domain_ref="vm1", command="query-status")
            assert result["response"]["return"]["status"] == "running"
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(_run())


def test_qmp_adapter_denies_non_allowlisted(tmp_path: Path):
    async def _run() -> None:
        adapter = QMPAdapter(socket_dir=str(tmp_path), allowlist={"query-status"}, enabled=True)

        with pytest.raises(MCPError) as exc:
            await adapter.execute(domain_ref="vm1", command="query-block")

        assert exc.value.code == "QMP_COMMAND_DENIED"

    asyncio.run(_run())


def test_qmp_adapter_capabilities_negotiation_failure(tmp_path: Path, monkeypatch):
    async def _run() -> None:
        adapter = QMPAdapter(socket_dir=str(tmp_path), allowlist={"query-status"}, enabled=True)

        class _Writer:
            def write(self, _line):
                return None

            async def drain(self):
                return None

            def close(self):
                return None

            async def wait_closed(self):
                return None

        async def _open_unix_connection(*, path: str):
            return object(), _Writer()

        monkeypatch.setattr(asyncio, "open_unix_connection", _open_unix_connection)
        monkeypatch.setattr(Path, "exists", lambda _self: True)
        monkeypatch.setattr(adapter, "_read_json_message", lambda _reader: asyncio.sleep(0, {"QMP": {}}))
        monkeypatch.setattr(adapter, "_send", lambda _writer, _payload: asyncio.sleep(0, None))
        monkeypatch.setattr(adapter, "_read_terminal_message", lambda _reader: asyncio.sleep(0, {"error": {"class": "GenericError"}}))

        with pytest.raises(MCPError) as exc:
            await adapter._run_qmp_command(command="query-status", arguments={}, socket_path="/tmp/fake.qmp")

        assert exc.value.code == "QMP_PROTOCOL_ERROR"

    asyncio.run(_run())


def test_qmp_adapter_read_terminal_message_skips_events():
    class _Reader:
        def __init__(self):
            self._lines = [
                b'{"event":"STOP","data":{}}\n',
                b'{"return":{"status":"running"}}\n',
            ]

        async def readline(self):
            return self._lines.pop(0)

    async def _run() -> None:
        adapter = QMPAdapter(socket_dir="/tmp", allowlist={"query-status"}, enabled=True)
        msg = await adapter._read_terminal_message(_Reader())
        assert msg["return"]["status"] == "running"

    asyncio.run(_run())
