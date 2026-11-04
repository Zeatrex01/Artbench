"""The AI connection (MCP): which AI tools (Claude Code, Gemini CLI, Codex) start Artbench's MCP server, and adding
it to Claude Code. Reads the tools' own config files and never writes them; adding runs Claude Code's own `claude
mcp` commands."""
import json
import os
import shutil
import subprocess
import sys

from . import config

MCP_NAME = "artbench"
MCP_MODULE = "artbench.mcp_server"
CLAUDE_TIMEOUT = 60      # seconds for each `claude mcp` call (a first run can stop at a login prompt)
_MCP_TOOLS = [("claude", "Claude Code"), ("gemini", "Gemini CLI"), ("codex", "Codex")]


def mcp_entry():
    """What an AI tool starts: this Python, the MCP module, this Artbench folder on PYTHONPATH."""
    return {"command": sys.executable, "args": ["-m", MCP_MODULE], "env": {"PYTHONPATH": config.TOOL_ROOT}}


def _q(s):
    return f'"{s}"' if " " in s else s


def mcp_lines():
    """The line or snippet that registers Artbench, per tool."""
    e = mcp_entry()
    root, py = e["env"]["PYTHONPATH"], e["command"]
    return {
        "claude": f"claude mcp add --scope user {MCP_NAME} -e PYTHONPATH={_q(root)} -- {_q(py)} -m {MCP_MODULE}",
        "gemini": json.dumps({"mcpServers": {MCP_NAME: e}}),
        "codex": (f"[mcp_servers.{MCP_NAME}]\ncommand = {json.dumps(py)}\nargs = [\"-m\", \"{MCP_MODULE}\"]\n"
                  f"env = {{ PYTHONPATH = {json.dumps(root)} }}"),
    }


def _mcp_configs(env, home):
    claude_dir = env.get("CLAUDE_CONFIG_DIR") or home
    codex_dir = env.get("CODEX_HOME") or os.path.join(home, ".codex")
    return {"claude": os.path.join(claude_dir, ".claude.json"),
            "gemini": os.path.join(home, ".gemini", "settings.json"),
            "codex": os.path.join(codex_dir, "config.toml")}


def _read_entry(tool, path):
    """Artbench's entry in one tool's config: a dict, None when absent; ValueError when the file cannot be read."""
    if not os.path.isfile(path):
        return None
    try:
        if tool == "codex":
            import tomllib
            with open(path, "rb") as f:
                servers = tomllib.load(f).get("mcp_servers") or {}
        else:
            with open(path, encoding="utf-8") as f:
                servers = json.load(f).get("mcpServers") or {}
    except Exception as e:  # noqa: BLE001  (a broken or foreign file: unknown, never an error for the page)
        raise ValueError(str(e))
    entry = servers.get(MCP_NAME)
    return entry if isinstance(entry, dict) else None


def _same_path(a, b):
    return bool(a) and bool(b) and os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _entry_state(entry):
    """"here" when the entry starts this Artbench folder, "elsewhere" when it starts another one, "missing"."""
    if entry is None:
        return "missing"
    root = config.TOOL_ROOT
    pythonpath = (entry.get("env") or {}).get("PYTHONPATH")
    command = entry.get("command") or ""
    inside = _same_path(os.path.dirname(os.path.dirname(command)), root) or _same_path(os.path.dirname(command), root)
    return "here" if _same_path(pythonpath, root) or inside else "elsewhere"


def mcp_status(env=None, home=None, which=None):
    """{tools: [{tool, name, installed, state: here | elsewhere | missing | unknown, config}], lines: mcp_lines()}."""
    env = os.environ if env is None else env
    home = home or os.path.expanduser("~")
    which = which or shutil.which
    paths = _mcp_configs(env, home)
    tools = []
    for tool, name in _MCP_TOOLS:
        try:
            state = _entry_state(_read_entry(tool, paths[tool]))
        except ValueError:
            state = "unknown"
        tools.append({"tool": tool, "name": name, "installed": bool(which(tool)), "state": state, "config": paths[tool]})
    return {"tools": tools, "lines": mcp_lines()}


def register_claude(env=None, home=None, which=None, run=None):
    """Adds Artbench to Claude Code at user scope (every folder); an entry that starts another Artbench folder is replaced.
    {result: registered | updated | already | no_claude | timeout | failed, message}."""
    which, run = which or shutil.which, run or subprocess.run
    line = mcp_lines()["claude"]
    claude = which("claude")
    if not claude:
        return {"result": "no_claude", "message": f"claude was not found on PATH: run this line yourself: {line}"}
    try:
        state = _entry_state(_read_entry("claude", _mcp_configs(os.environ if env is None else env,
                                                                home or os.path.expanduser("~"))["claude"]))
    except ValueError:
        state = "unknown"
    if state == "here":
        return {"result": "already", "message": "Claude Code already starts this Artbench; nothing changed."}
    e = mcp_entry()
    try:
        if state in ("elsewhere", "unknown"):
            run([claude, "mcp", "remove", "--scope", "user", MCP_NAME], capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
        done = run([claude, "mcp", "add", "--scope", "user", MCP_NAME, "-e", f"PYTHONPATH={e['env']['PYTHONPATH']}", "--",
                    e["command"], *e["args"]], capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"result": "timeout", "message": f"claude did not answer in {CLAUDE_TIMEOUT} s: run this line yourself: {line}"}
    except OSError as err:
        return {"result": "failed", "message": f"claude could not be started ({err}): run this line yourself: {line}"}
    if done.returncode != 0:
        return {"result": "failed", "message": f"claude mcp add failed: {(done.stderr or done.stdout or '').strip()}"}
    if state == "elsewhere":
        return {"result": "updated", "message": "Claude Code now starts this Artbench (it pointed at another folder)."}
    return {"result": "registered", "message": "Added to Claude Code."}
