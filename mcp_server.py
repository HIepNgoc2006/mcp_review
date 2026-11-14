"""Portable stdio MCP adapter for a separately installed local Bridge."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Annotated, Literal

from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

VERSION = "1.0.1"
BRIDGE_URL = "http://127.0.0.1:5050"
REQUEST_TIMEOUT_SECONDS = 5
MAX_REPLY_PREVIEW_CHARS = 2000
logger = logging.getLogger("chatgpt_bridge_mcp")
mcp = MCPServer(
    "chatgpt-bridge",
    version=VERSION,
    instructions=(
        "Manage a separately installed local ChatGPT–Antigravity Bridge. All write actions require explicit IDs. "
        "Never target by title, channel, foreground tab, or first window. Do not repeat an operation ID with different input. "
        "The local Bridge validates user/profile identities; never guess them. Ask the user when a write target is ambiguous."
    ),
)


class BridgeError(Exception):
    """Sanitized, actionable local Bridge error."""


def bridge_request(path: str, payload: dict | None = None, query: dict | None = None, method: str | None = None) -> dict:
    if not path.startswith("/") or ".." in path or "?" in path or "#" in path:
        raise ValueError("Invalid fixed Bridge API path")
    if query and not all(isinstance(key, str) and isinstance(value, str) for key, value in query.items()):
        raise ValueError("Invalid Bridge API query")
    url = f"{BRIDGE_URL}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method=method or ("GET" if payload is None else "POST"),
    )
    try:
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, redirected_request, response, code, message, headers, new_url):
                return None

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirectHandler())
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            details = json.loads(error.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            details = {}
        code = details.get("error", "BRIDGE_REQUEST_FAILED")
        messages = {
            "UNPAIRED_SESSION": "The Anti session has no explicit ChatGPT pairing.",
            "PAIRING_CONFLICT": "A pairing target is already assigned to another ChatGPT conversation.",
            "INVALID_PAIRING": "The pairing values are invalid.",
            "RESPONSE_NOT_CURRENT": "This reply is no longer the current queued response.",
            "RESPONSE_ALREADY_RESERVED": "This reply already has a delivery receipt; it was not sent again.",
            "OPERATION_ID_CONFLICT": "This operation ID has already been used with different arguments.",
            "INVALID_COMPACT_TARGET": "A valid local user and exact conversation ID are required.",
            "COMPACT_TARGET_UNAVAILABLE": "The exact Antigravity conversation is not available for compact.",
        }
        raise BridgeError(f"Bridge {code}: {messages.get(code, 'The Bridge rejected the request.')}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BridgeError("Bridge unavailable at 127.0.0.1:5050; start or restore the single Bridge listener") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BridgeError("Bridge returned an invalid JSON response") from None
    if not isinstance(result, dict):
        raise BridgeError("Bridge returned an invalid response object")
    return result


def _metadata_response(records: object, fields: tuple[str, ...]) -> dict:
    if not isinstance(records, list):
        return {"items": [], "count": 0}
    safe_records = [
        {key: record[key] for key in fields if key in record}
        for record in records if isinstance(record, dict)
    ]
    return {"items": safe_records, "count": len(safe_records)}


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"{name} is required")


def _require_user(user: str) -> None:
    _require_text(user, "user")


def _require_operation(operation_id: str) -> None:
    if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
        raise ToolError("operation_id must contain 1 to 200 characters")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_bridge_status() -> dict:
    """Read local Bridge health, process identity and single-listener status."""
    result = bridge_request("/health")
    return {key: result.get(key) for key in ("status", "bridge", "process_count", "listener_count", "pid")}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_chatgpt_tabs() -> dict:
    """List active ChatGPT tab identity and online metadata without prompt bodies."""
    return _metadata_response(bridge_request("/tabs").get("tabs"), (
        "chat_id", "tab_id", "title", "url", "channel", "online", "agent", "anti_title", "anti_user", "anti_conversation_id",
    ))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_anti_sessions(user: str) -> dict:
    """List one Bridge-configured user's Anti sessions without filesystem paths."""
    _require_user(user)
    result = bridge_request("/sessions", query={"user": user})
    return {
        key: result[key] for key in ("status", "user", "count") if key in result
    } | {
        "sessions": _metadata_response(result.get("sessions"), (
            "user", "conversation_id", "title", "is_active", "is_open", "ambiguous", "size_kb", "steps",
        ))["items"]
    }


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_pairings() -> dict:
    """List explicit ChatGPT-to-Antigravity pairings and online state."""
    return _metadata_response(bridge_request("/pairings").get("pairings"), (
        "chat_id", "chat_url", "chat_title", "user", "conversation_id", "anti_title", "agent", "updated_at", "online",
    ))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def list_queues() -> dict:
    """List queue counts and message/response IDs only; never returns queued bodies."""
    result = bridge_request("/queues")
    safe = {"status": result.get("status", "unknown")}
    for queue_name, id_field in (("outbound", "message_ids"), ("responses", "response_ids")):
        queues = result.get(queue_name)
        if not isinstance(queues, dict):
            safe[queue_name] = {}
            continue
        safe[queue_name] = {
            chat_id: {key: item[key] for key in ("count", id_field) if key in item}
            for chat_id, item in queues.items() if isinstance(chat_id, str) and isinstance(item, dict)
        }
    return safe


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def pull_chatgpt_reply(chat_id: str, preview_chars: Annotated[int, Field(ge=1, le=MAX_REPLY_PREVIEW_CHARS)] = 500) -> dict:
    """Read a bounded preview for an explicit ChatGPT ID and release its claim."""
    _require_text(chat_id, "chat_id")
    response = bridge_request("/response", query={"chat_id": chat_id}).get("data")
    if not isinstance(response, dict) or not response:
        return {"status": "no_pending", "chat_id": chat_id}
    response_id, claim_id = response.get("response_id", ""), response.get("claim_id", "")
    if not response_id or not claim_id:
        raise ToolError("Bridge reply is missing its response/claim ID; no reply was consumed")
    agents = response.get("agents", [])
    if isinstance(agents, list) and agents:
        source = json.dumps([
            {key: item[key] for key in ("index", "title", "prompt") if key in item}
            for item in agents if isinstance(item, dict)
        ], ensure_ascii=False)
    else:
        source = response.get("raw", response.get("text", ""))
    if not isinstance(source, str):
        source = ""
    try:
        bridge_request("/responses/release", {"chat_id": chat_id, "response_id": response_id, "claim_id": claim_id})
    except BridgeError:
        raise ToolError("Reply preview could not safely release its queue claim; check Bridge health") from None
    return {"status": "preview_released", "chat_id": chat_id, "response_id": response_id,
            "preview": source[:preview_chars], "truncated": len(source) > preview_chars}

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_delivery_receipt(chat_id: str, response_id: str) -> dict:
    """Inspect metadata for one exact response delivery receipt without exposing prompt data."""
    _require_text(chat_id, "chat_id")
    _require_text(response_id, "response_id")
    result = bridge_request("/responses/receipts", query={"chat_id": chat_id, "response_id": response_id})
    receipt = result.get("receipt")
    safe = {"status": result.get("status", "unknown")}
    if isinstance(receipt, dict):
        safe["receipt"] = {
            key: receipt[key] for key in ("chat_id", "response_id", "user", "conversation_id", "agent", "state")
            if key in receipt
        }
    return safe


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
def pair_chat(chat_id: str, user: str, conversation_id: str, agent: Literal["agent_1", "agent_2", "agent_3", "agent_4"]) -> dict:
    """Pair exact ChatGPT and Anti IDs; changes routing and rejects conflicts."""
    _require_text(chat_id, "chat_id")
    _require_user(user)
    _require_text(conversation_id, "conversation_id")
    if agent not in ("agent_1", "agent_2", "agent_3", "agent_4"):
        raise ToolError("agent must be agent_1, agent_2, agent_3, or agent_4")
    return bridge_request("/pairings", {"chat_id": chat_id, "user": user, "conversation_id": conversation_id,
                                        "anti_title": conversation_id, "agent": agent})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False))
def unpair_chat(chat_id: str) -> dict:
    """Remove only the exact ChatGPT pairing ID; outbound queue items remain."""
    _require_text(chat_id, "chat_id")
    return bridge_request("/pairings", method="DELETE", query={"chat_id": chat_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def push_to_chatgpt(operation_id: str, user: str, conversation_id: str, text: str) -> dict:
    """Queue text for one exact pairing with durable duplicate protection."""
    _require_operation(operation_id)
    _require_user(user)
    _require_text(conversation_id, "conversation_id")
    _require_text(text, "text")
    return bridge_request("/push", {"operation_id": operation_id, "user": user,
                                     "conversation_id": conversation_id, "text": text})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def inject_chatgpt_reply(operation_id: str, chat_id: str, response_id: str, user: str, conversation_id: str) -> dict:
    """Send one reply to an exact paired Anti session; uncertain outcomes are never retried."""
    _require_operation(operation_id)
    _require_text(chat_id, "chat_id")
    _require_text(response_id, "response_id")
    _require_user(user)
    _require_text(conversation_id, "conversation_id")
    return bridge_request("/responses/inject", {"operation_id": operation_id, "chat_id": chat_id,
        "response_id": response_id, "user": user, "conversation_id": conversation_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def compact_anti_session(user: str, conversation_id: str) -> dict:
    """Request /compact in the exact specified Anti conversation."""
    _require_user(user)
    _require_text(conversation_id, "conversation_id")
    return bridge_request("/compact", {"user": user, "conversation_id": conversation_id})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def get_autopilot_status() -> dict:
    """Read the single Bridge-owned Auto-Pilot worker state."""
    return bridge_request("/autopilot")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def start_autopilot() -> dict:
    """Start the Bridge-owned Auto-Pilot worker; repeated requests are idempotent."""
    return bridge_request("/autopilot/start", {})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
def stop_autopilot() -> dict:
    """Stop the Bridge-owned Auto-Pilot worker and wait for confirmation."""
    return bridge_request("/autopilot/stop", {})


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False))
def restart_bridge() -> dict:
    """Restart Bridge and wait for a different PID plus one healthy listener."""
    before = bridge_request("/health")
    if (before.get("status"), before.get("process_count"), before.get("listener_count")) != ("running", 1, 1):
        raise ToolError("Bridge is not uniquely healthy; refusing to restart an ambiguous listener")
    previous_pid = before.get("pid")
    if not isinstance(previous_pid, int) or previous_pid <= 0:
        raise ToolError("Bridge health does not expose a valid process ID; restart cannot be verified")
    bridge_request("/bridge/restart", {})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        try:
            current = bridge_request("/health")
        except BridgeError:
            continue
        if (current.get("status"), current.get("process_count"), current.get("listener_count")) == ("running", 1, 1) and current.get("pid") != previous_pid:
            return current
    raise ToolError("Bridge restart was requested but a new single healthy process was not confirmed")


async def _smoke_test() -> dict:
    global bridge_request
    live_request = bridge_request

    def fake_bridge_request(path: str, payload: dict | None = None, query: dict | None = None, method: str | None = None) -> dict:
        if path != "/health" or payload is not None or query is not None or method is not None:
            raise BridgeError("Unexpected request during offline smoke test")
        return {"status": "running", "bridge": "test", "process_count": 1, "listener_count": 1, "pid": 1}

    bridge_request = fake_bridge_request
    try:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_bridge_status", {})
            return {"tool_count": len(tools.tools), "tool_names": [tool.name for tool in tools.tools],
                    "health": json.loads(result.content[0].text)}
    finally:
        bridge_request = live_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Local ChatGPT Bridge MCP stdio adapter")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list-tools", action="store_true", help="print tool names and JSON input schemas")
    actions.add_argument("--smoke-test", action="store_true", help="run SDK in-memory tool catalog and safe health call")
    args = parser.parse_args()
    if args.list_tools:
        print(json.dumps([{"name": tool.name, "description": tool.description, "inputSchema": tool.parameters}
                          for tool in mcp._tool_manager.list_tools()], ensure_ascii=False, indent=2))
        return 0
    if args.smoke_test:
        import anyio
        print(json.dumps(anyio.run(_smoke_test), ensure_ascii=False, indent=2))
        return 0
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
