"""QMP adapter for controlled command execution over UNIX sockets."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from libvirt_mcp_server.errors import MCPError


class QMPAdapter:
    def __init__(self, *, socket_dir: str, allowlist: set[str], enabled: bool) -> None:
        self.socket_dir = Path(socket_dir)
        self.allowlist = allowlist
        self.enabled = enabled

    async def execute(
        self,
        *,
        domain_ref: str,
        command: str,
        arguments: dict[str, Any] | None = None,
        socket_path: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise MCPError(code="QMP_DISABLED", message="QMP is disabled by policy")

        if not self._is_allowed(command):
            raise MCPError(
                code="QMP_COMMAND_DENIED",
                message=f"QMP command '{command}' is not allowed",
                details={"command": command, "source": "qmp"},
            )

        response = await self._run_qmp_command(
            command=command,
            arguments=arguments or {},
            socket_path=socket_path or self._default_socket(domain_ref),
        )
        return {
            "source": "qmp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "command": command,
            "response": response,
        }

    async def capabilities(self, *, domain_ref: str, socket_path: str | None = None) -> dict[str, Any]:
        return await self.execute(
            domain_ref=domain_ref,
            command="query-commands",
            arguments={},
            socket_path=socket_path,
        )

    async def events(
        self,
        *,
        domain_ref: str,
        event_types: list[str] | None = None,
        since: str | None = None,
        socket_path: str | None = None,
    ) -> dict[str, Any]:
        # Minimal event bridge: query-status is used as a safe status heartbeat.
        # Full event streaming can be added with a persistent subscription mode.
        status = await self.execute(
            domain_ref=domain_ref,
            command="query-status",
            arguments={},
            socket_path=socket_path,
        )
        return {
            "source": "qmp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "domain_ref": domain_ref,
            "event_types": event_types or [],
            "since": since,
            "events": [],
            "status_snapshot": status["response"],
        }

    async def collect_events(
        self,
        *,
        domain_ref: str,
        timeout_seconds: float = 2.0,
        event_types: list[str] | None = None,
        socket_path: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise MCPError(code="QMP_DISABLED", message="QMP is disabled by policy")

        resolved_path = socket_path or self._default_socket(domain_ref)
        if not Path(resolved_path).exists():
            raise MCPError(
                code="QMP_TRANSPORT_ERROR",
                message=f"QMP socket not found at '{resolved_path}'",
                retryable=True,
                details={"socket_path": resolved_path, "source": "qmp"},
            )

        try:
            reader, writer = await asyncio.open_unix_connection(path=resolved_path)
        except Exception as exc:
            raise MCPError(
                code="QMP_TRANSPORT_ERROR",
                message="Failed to open QMP socket",
                retryable=True,
                details={"socket_path": resolved_path, "source": "qmp", "cause": str(exc)},
            )

        try:
            # QMP handshake
            greeting_line = await reader.readline()
            if not greeting_line:
                raise MCPError(code="QMP_TRANSPORT_ERROR", message="Connection closed during greeting")
            try:
                greeting = json.loads(greeting_line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="Failed to parse QMP greeting",
                    details={"source": "qmp", "cause": str(exc)},
                )
            if "QMP" not in greeting:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="Invalid QMP greeting",
                    details={"source": "qmp", "greeting": greeting},
                )

            await self._send(writer, {"execute": "qmp_capabilities"})
            ack_line = await reader.readline()
            if not ack_line:
                raise MCPError(code="QMP_TRANSPORT_ERROR", message="Connection closed during capabilities ack")
            try:
                ack = json.loads(ack_line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="Failed to parse capabilities ack",
                    details={"source": "qmp", "cause": str(exc)},
                )
            if "error" in ack:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="qmp_capabilities negotiation failed",
                    details={"source": "qmp", "response": ack},
                )

            # Collect events for timeout_seconds
            events: list[dict[str, Any]] = []
            loop = asyncio.get_event_loop()
            deadline = loop.time() + timeout_seconds
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    line = await asyncio.wait_for(reader.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if not line:
                    break
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise MCPError(
                        code="QMP_PROTOCOL_ERROR",
                        message="Failed to parse QMP message",
                        details={"source": "qmp", "cause": str(exc)},
                    )
                if "event" in msg:
                    if not event_types or msg["event"] in event_types:
                        events.append(msg)

            return {
                "source": "qmp",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "domain_ref": domain_ref,
                "event_types_filter": event_types or [],
                "events": events,
                "total_count": len(events),
            }
        finally:
            writer.close()
            await writer.wait_closed()

    def _is_allowed(self, command: str) -> bool:
        if "*" in self.allowlist:
            return True
        return command in self.allowlist

    def _default_socket(self, domain_ref: str) -> str:
        return str(self.socket_dir / f"{domain_ref}.qmp")

    async def _run_qmp_command(self, *, command: str, arguments: dict[str, Any], socket_path: str) -> dict[str, Any]:
        if not Path(socket_path).exists():
            raise MCPError(
                code="QMP_TRANSPORT_ERROR",
                message=f"QMP socket not found at '{socket_path}'",
                retryable=True,
                details={"socket_path": socket_path, "source": "qmp"},
            )

        try:
            reader, writer = await asyncio.open_unix_connection(path=socket_path)
        except Exception as exc:
            raise MCPError(
                code="QMP_TRANSPORT_ERROR",
                message="Failed to open QMP socket",
                retryable=True,
                details={"socket_path": socket_path, "source": "qmp", "cause": str(exc)},
            )

        try:
            greeting = await self._read_json_message(reader)
            if "QMP" not in greeting:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="Invalid QMP greeting",
                    details={"socket_path": socket_path, "source": "qmp", "greeting": greeting},
                )

            await self._send(writer, {"execute": "qmp_capabilities"})
            capabilities_ack = await self._read_terminal_message(reader)
            if "error" in capabilities_ack:
                raise MCPError(
                    code="QMP_PROTOCOL_ERROR",
                    message="qmp_capabilities negotiation failed",
                    details={"source": "qmp", "response": capabilities_ack},
                )

            await self._send(writer, {"execute": command, "arguments": arguments})
            result = await self._read_terminal_message(reader)
            if "error" in result:
                raise MCPError(
                    code="QMP_COMMAND_FAILED",
                    message=f"QMP command '{command}' failed",
                    details={"source": "qmp", "response": result},
                )
            return result
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        writer.write(line)
        await writer.drain()

    async def _read_json_message(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        line = await reader.readline()
        if not line:
            raise MCPError(code="QMP_TRANSPORT_ERROR", message="Connection closed while reading QMP")
        return json.loads(line.decode("utf-8"))

    async def _read_terminal_message(self, reader: asyncio.StreamReader) -> dict[str, Any]:
        # QMP may emit async events before command returns. Skip those.
        while True:
            msg = await self._read_json_message(reader)
            if "event" in msg:
                continue
            return msg
