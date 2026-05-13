"""CLI entrypoint: `serve` runs the MCP stdio server; `tool` invokes a tool locally."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from libvirt_mcp_server.server import LibvirtMCPServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nested-mcp-server",
        description="nested MCP server",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # serve – start the MCP stdio transport (used by MCP clients)
    serve_p = sub.add_parser("serve", help="Start the MCP server (stdio transport)")
    serve_p.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="Transport to use (currently only stdio is supported)",
    )

    # tool – invoke a single tool locally and print JSON output
    tool_p = sub.add_parser("tool", help="Invoke a tool locally and print the result as JSON")
    tool_p.add_argument("tool_name", help="Tool name to invoke")
    tool_p.add_argument("--args", default="{}", help="JSON object of tool arguments")
    tool_p.add_argument("--actor", default="cli", help="Actor identity for audit records")

    return parser


async def _serve() -> None:
    from libvirt_mcp_server.app import app  # import here to keep startup lazy
    await app.run_stdio_async()


async def _run_tool(tool_name: str, arguments: dict, actor: str) -> int:
    server = LibvirtMCPServer()
    result = await server.call_tool(tool_name, arguments, actor=actor)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if "error" not in result else 1


def main() -> int:
    parser = build_parser()
    ns = parser.parse_args()

    if ns.command == "serve":
        asyncio.run(_serve())
        return 0

    if ns.command == "tool":
        try:
            arguments = json.loads(ns.args)
            if not isinstance(arguments, dict):
                raise ValueError("--args must be a JSON object")
        except Exception as exc:
            print(json.dumps({"error": f"Invalid --args JSON: {exc}"}), file=sys.stderr)
            return 2
        return asyncio.run(_run_tool(ns.tool_name, arguments, ns.actor))

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
