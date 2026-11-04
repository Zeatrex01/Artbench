"""MCP server (stdio, newline-delimited JSON-RPC) so local AI agents such as Claude Code can read and update the
inventory: projects, assets, usage, unused, placeholders, layout issues, graph neighbours, tasks, notes, history.
Tools are the operations of `ops.py`, the layer the HTTP API and the command line also call, so every caller sees
one state under one set of rules.

    python -m artbench.mcp_server
    claude mcp add --scope user artbench -e PYTHONPATH=<Artbench folder> -- python -m artbench.mcp_server
"""
import json
import sys

from . import config, ops

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "artbench", "version": config.VERSION}

# --- tools: generated from the operations layer ------------------------------------------------------------------

TOOLS = [{"name": "artbench_" + o.name, "description": o.description, "inputSchema": o.params} for o in ops.OPS.values() if o.agents]
HANDLERS = {"artbench_" + o.name: o.name for o in ops.OPS.values() if o.agents}


def tools():
    """The tools for the registered projects' modes, read at every tools/list (a project added later shows up):
    with only project-mode projects, the art-folder tools are left out. With nothing registered, every tool."""
    modes = {c.get("mode", "art") for c in config.projects() if "error" not in c}
    if not modes:
        return TOOLS
    return [t for t in TOOLS if modes & set(ops.OPS[HANDLERS[t["name"]]].modes)]


# --- JSON-RPC ---------------------------------------------------------------------------------------------------

def handle(request):
    """One JSON-RPC request -> response dict (None for notifications)."""
    method, params, rid = request.get("method"), request.get("params") or {}, request.get("id")
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                  "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO}
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return None
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tools()}
    elif method == "tools/call":
        name = params.get("name")
        if name not in HANDLERS:
            return _error(rid, -32602, f"unknown tool {name}")
        try:
            value = ops.call(HANDLERS[name], params.get("arguments") or {})
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))    # compact: an AI pays per character
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        except ops.OpError as e:  # the agent gets the code and the message
            result = {"content": [{"type": "text", "text": f"{e.code}: {e.message}"}], "isError": True}
        except (TypeError, ValueError) as e:  # a result JSON cannot carry: the server keeps answering
            result = {"content": [{"type": "text", "text": f"internal: the result could not be encoded as JSON: {e}"}], "isError": True}
    else:
        if rid is None:
            return None
        return _error(rid, -32601, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def main():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            request = json.loads(raw)
        except ValueError:
            stdout.write((json.dumps(_error(None, -32700, "parse error")) + "\n").encode("utf-8"))
            stdout.flush()
            continue
        response = handle(request)
        if response is not None:
            stdout.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()


if __name__ == "__main__":
    main()
