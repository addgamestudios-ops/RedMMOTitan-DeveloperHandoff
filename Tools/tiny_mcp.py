#!/usr/bin/env python3
"""Tiny MCP client for Unreal execute_python_code — one short snippet at a time."""
import json
import socket
import sys
import urllib.request
from urllib.parse import urlparse

URL = "http://127.0.0.1:8000/mcp"
SESSION = None


def rpc(method, params=None, timeout=60):
    global SESSION
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if SESSION:
        headers["Mcp-Session-Id"] = SESSION
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            SESSION = sid
        raw = resp.read().decode()
        # SSE or plain JSON
        if raw.startswith("event:") or "data:" in raw:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            raise RuntimeError(f"no data in SSE: {raw[:200]}")
        return json.loads(raw)


def stream_rpc(method, params=None, timeout=60, request_id=2):
    """Read a UE multi-write SSE response through its first data event.

    Epic's UE HTTP server intentionally omits Content-Length and chunked encoding
    for streamed tool results. Keeping the raw socket alive mirrors the behavior
    documented by the engine's ModelContextProtocol tests.
    """
    global SESSION
    if not SESSION:
        raise RuntimeError("initialize the MCP session before calling stream_rpc")

    body = json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
    ).encode()
    parsed = urlparse(URL)
    port = parsed.port or 80
    if parsed.scheme != "http":
        raise RuntimeError("tiny_mcp stream transport supports local HTTP only")

    request = (
        f"POST {parsed.path or '/'} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}:{port}\r\n"
        "Content-Type: application/json\r\n"
        "Accept: application/json, text/event-stream\r\n"
        f"Mcp-Session-Id: {SESSION}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: keep-alive\r\n\r\n"
    ).encode() + body

    sock = socket.create_connection((parsed.hostname, port), timeout=min(timeout, 10))
    sock.settimeout(timeout)
    response = b""
    try:
        sock.sendall(request)
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response += chunk
            payload = response.split(b"\r\n\r\n", 1)[-1]
            if b"data:" in payload and (b"\n\n" in payload or b"\r\n\r\n" in payload):
                break
    finally:
        sock.close()

    header_bytes, _, payload = response.partition(b"\r\n\r\n")
    for line in header_bytes.decode(errors="replace").splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep and key.lower() == "mcp-session-id":
            SESSION = value.strip()

    for line in payload.decode(errors="replace").splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError(f"no SSE data event received: {response[:500]!r}")


def call_tool(name, arguments=None, timeout=90, request_id=2):
    return stream_rpc(
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        timeout=timeout,
        request_id=request_id,
    )


def invoke(toolset_name: str, tool_name: str, arguments=None, timeout=90, request_id=3):
    """Invoke a tool exposed through UE 5.8's official toolset registry."""
    return call_tool(
        "call_tool",
        {
            "toolset_name": toolset_name,
            "tool_name": tool_name,
            "arguments": arguments or {},
        },
        timeout=timeout,
        request_id=request_id,
    )


def print_result(response):
    """Print the text content from an MCP response, falling back to JSON."""
    result = response.get("result", response) if isinstance(response, dict) else response
    content = result.get("content") if isinstance(result, dict) else None
    if content:
        for item in content:
            if item.get("type") == "text":
                print(item.get("text", ""))
        return
    print(json.dumps(response, indent=2)[:20000])


def init():
    return rpc(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "tiny-mcp", "version": "1"},
        },
    )


def notify_initialized():
    body = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if SESSION:
        headers["Mcp-Session-Id"] = SESSION
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def exec_py(code: str, timeout=90):
    res = rpc(
        "tools/call",
        {"name": "execute_python_code", "arguments": {"code": code}},
        timeout=timeout,
    )
    return res


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ping"
    init()
    notify_initialized()
    if cmd == "ping":
        print_result(call_tool("list_toolsets"))
        return
    if cmd == "code":
        code = sys.stdin.read()
        r = exec_py(code)
        # unwrap
        result = r.get("result", r)
        content = result.get("content") if isinstance(result, dict) else None
        if content:
            for c in content:
                if c.get("type") == "text":
                    print(c.get("text", ""))
        else:
            print(json.dumps(r, indent=2)[:4000])
        return
    if cmd == "toolsets":
        print_result(call_tool("list_toolsets"))
        return
    if cmd == "describe" and len(sys.argv) >= 3:
        print_result(call_tool("describe_toolset", {"toolset_name": sys.argv[2]}))
        return
    if cmd == "call" and len(sys.argv) >= 4:
        raw = sys.stdin.read().strip()
        arguments = json.loads(raw) if raw else {}
        print_result(invoke(sys.argv[2], sys.argv[3], arguments))
        return
    print("usage: tiny_mcp.py ping | toolsets | describe <toolset> | call <toolset> <tool> [json stdin] | code <stdin>")


if __name__ == "__main__":
    main()
