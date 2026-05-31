"""Live MCP client manager (ROADMAP §7.5 / WS-A).

Connects to external MCP servers declared in `mcp_servers.json` and surfaces their
tools through the SAME tool registry agents already use — so an agent calling
`weave_query` (the W&B/Weave MCP) is indistinguishable, to the engine, from calling
`web_search`. Every MCP call flows through `execute_tool` and is Weave-traced.

100% optional and lazy: if `settings.mcp_enabled` is false (no config file) NOTHING
here runs and no MCP tools are registered — the council still works keyless. All
connection failures are logged and swallowed; a broken server never breaks a debate.

Design: connections are PER-CALL, not persistent. A debate runs agents inside
`asyncio.gather`, so a tool call happens in a child task; an MCP session opened in
the parent task and used from a child trips anyio's cancel-scope guard. Opening +
closing a fresh session inside the calling task (with an init timeout) sidesteps that
entirely. The brief extra handshake per call is negligible for a council.

Config shape (mcp_servers.json):
{
  "servers": [
    {
      "name": "wandb",
      "transport": "http",                  # or "stdio"
      "url": "https://mcp.withwandb.com/mcp",
      "headers": {"Authorization": "Bearer ${WANDB_API_KEY}"},
      # stdio: "command": "uvx", "args": [...], "env": {"KEY": "${KEY}"}
      "expose": [
        {"as": "weave_query", "tool": "query_weave_traces_tool",
         "description": "Query real W&B/Weave trace data as evidence.",
         "defaults": {"entity_name": "…", "project_name": "…"}}
      ]
    }
  ]
}
If "expose" is omitted, every tool the server lists is exposed under its own name.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from string import Template
from typing import Optional

from ..config import get_settings

log = logging.getLogger("mcp")
_INIT_TIMEOUT = 15.0


def _expand(value: str) -> str:
    """Expand ${VAR} from the process env, overlaid with the keys we hold in
    settings (loaded from backend/.env, which is NOT exported to os.environ)."""
    s = get_settings()
    mapping = dict(os.environ)
    for k, v in (("WANDB_API_KEY", s.wandb_api_key),
                 ("FIRECRAWL_API_KEY", s.firecrawl_api_key),
                 ("TAVILY_API_KEY", s.tavily_api_key)):
        if v:
            mapping[k] = v
    return Template(value).safe_substitute(mapping)


def _result_to_dict(result) -> dict:
    """Flatten an MCP CallToolResult into a JSON-able dict."""
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    out: dict = {"text": "\n".join(parts)} if parts else {}
    structured = getattr(result, "structuredContent", None)
    if structured:
        out["data"] = structured
    if getattr(result, "isError", False):
        out["error"] = out.get("text") or "mcp tool error"
    return out or {"text": ""}


@asynccontextmanager
async def _open(spec: dict):
    """Open an initialized MCP ClientSession for `spec`, fully within the caller's
    task. Uses NESTED `async with` (not AsyncExitStack) so the transport's internal
    anyio task groups nest/cancel correctly — flattening them trips a TaskGroup error.
    """
    from mcp import ClientSession

    if spec.get("transport", "stdio") == "http":
        from mcp.client.streamable_http import streamablehttp_client
        headers = {k: _expand(v) for k, v in (spec.get("headers") or {}).items()}
        async with streamablehttp_client(spec["url"], headers=headers or None) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=_INIT_TIMEOUT)
                yield session
    else:
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = {k: _expand(v) for k, v in (spec.get("env") or {}).items()}
        if env:
            env.setdefault("PATH", os.environ.get("PATH", ""))
        params = StdioServerParameters(command=spec["command"],
                                       args=spec.get("args", []), env=env or None)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=_INIT_TIMEOUT)
                yield session


class McpManager:
    def __init__(self) -> None:
        self._servers: dict[str, dict] = {}               # server name -> spec
        # exposed tool name -> {server, tool, defaults, description, input_schema}
        self._exposed: dict[str, dict] = {}
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def exposed(self) -> dict[str, dict]:
        return self._exposed

    async def connect_all(self, config_path) -> None:
        if self._connected:
            return
        self._connected = True   # mark first so a broken config never loops on retry
        try:
            cfg = json.loads(open(config_path, encoding="utf-8").read())
        except Exception as e:                            # noqa: BLE001
            log.warning("mcp: cannot read %s: %s", config_path, e)
            return
        for spec in cfg.get("servers", []):
            try:
                await self._discover(spec)
            except BaseException as e:                    # noqa: BLE001 — incl. CancelledError
                log.warning("mcp: server %s discovery failed: %s", spec.get("name"), e)

    async def _discover(self, spec: dict) -> None:
        name = spec["name"]
        async with _open(spec) as session:
            listed = {t.name: t for t in (await session.list_tools()).tools}
        self._servers[name] = spec
        for e in (spec.get("expose") or [{"as": t, "tool": t} for t in listed]):
            tool = listed.get(e["tool"])
            self._exposed[e["as"]] = {
                "server": name, "tool": e["tool"], "defaults": e.get("defaults") or {},
                "description": e.get("description") or (getattr(tool, "description", "") or e["tool"]),
                "input_schema": getattr(tool, "inputSchema", {"type": "object"}),
            }
        log.info("mcp: discovered %s — exposing %s", name, list(self._exposed))

    async def call(self, exposed_name: str, args: dict) -> dict:
        meta = self._exposed.get(exposed_name)
        if not meta:
            return {"error": f"mcp tool '{exposed_name}' not connected"}
        merged = {**meta["defaults"], **(args or {})}
        try:
            async with _open(self._servers[meta["server"]]) as session:
                result = await session.call_tool(meta["tool"], arguments=merged)
                return _result_to_dict(result)
        except BaseException as e:                        # noqa: BLE001
            return {"error": str(e), "tool": exposed_name}

    async def aclose(self) -> None:
        self._servers.clear()
        self._exposed.clear()
        self._connected = False


_manager: Optional[McpManager] = None


def get_mcp_manager() -> McpManager:
    global _manager
    if _manager is None:
        _manager = McpManager()
    return _manager


async def ensure_mcp_registered(registry) -> None:
    """Connect MCP servers (once) and register their tools into `registry`.

    No-op unless settings.mcp_enabled. Idempotent and failure-tolerant.
    """
    s = get_settings()
    if not s.mcp_enabled:
        return
    mgr = get_mcp_manager()
    if mgr.connected:
        return
    from .tool_registry import ToolSpec

    await mgr.connect_all(str(s.mcp_config_file))

    def _make_handler(exposed_name: str):
        async def _handler(args: dict, ctx) -> dict:
            return await get_mcp_manager().call(exposed_name, args)
        return _handler

    for name, meta in mgr.exposed().items():
        registry.register(ToolSpec(
            name=name, description=meta["description"],
            input_schema=meta.get("input_schema") or {"type": "object"},
            kind="mcp", handler=_make_handler(name)))
