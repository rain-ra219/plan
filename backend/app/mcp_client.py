from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


MCP_PROTOCOL_VERSION = "2025-06-18"


class McpClientError(RuntimeError):
    pass


def discover_tools(endpoint_url: str, timeout: int = 10) -> list[dict[str, Any]]:
    initialize(endpoint_url, timeout=timeout)
    result = call_json_rpc(endpoint_url, "tools/list", {}, timeout=timeout)
    tools = result.get("tools", []) if isinstance(result, dict) else []
    if not isinstance(tools, list):
        raise McpClientError("MCP tools/list 返回格式不正确")
    return [tool for tool in tools if isinstance(tool, dict)]


def call_tool(endpoint_url: str, tool_name: str, arguments: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    initialize(endpoint_url, timeout=timeout)
    result = call_json_rpc(
        endpoint_url,
        "tools/call",
        {"name": tool_name, "arguments": arguments},
        timeout=timeout,
    )
    return result if isinstance(result, dict) else {"result": result}


def initialize(endpoint_url: str, timeout: int = 10) -> dict[str, Any]:
    return call_json_rpc(
        endpoint_url,
        "initialize",
        {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "ai-automation-console-lite", "version": "0.1.0"},
        },
        timeout=timeout,
    )


def call_json_rpc(endpoint_url: str, method: str, params: dict[str, Any], timeout: int = 10) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": f"mcp_{uuid.uuid4().hex[:12]}",
        "method": method,
        "params": params,
    }
    request = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise McpClientError(f"MCP HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise McpClientError(f"MCP 连接失败：{exc.reason}") from exc
    except TimeoutError as exc:
        raise McpClientError("MCP 请求超时") from exc

    if not raw.strip():
        return {}

    data = parse_mcp_response(raw)
    if isinstance(data, list):
        data = data[-1] if data else {}
    if not isinstance(data, dict):
        raise McpClientError("MCP 返回不是 JSON-RPC 对象")
    if data.get("error"):
        message = data["error"].get("message") if isinstance(data["error"], dict) else str(data["error"])
        raise McpClientError(message or "MCP 调用失败")
    _ = started
    return data.get("result", {})


def parse_mcp_response(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("data:"):
        chunks = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                value = line[5:].strip()
                if value and value != "[DONE]":
                    chunks.append(json.loads(value))
        return chunks[-1] if chunks else {}
    return json.loads(text)
