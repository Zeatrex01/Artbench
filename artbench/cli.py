"""Command line over the operations layer, for scripts and AI tools that cannot speak MCP, and the one-step setup of
a game project in project mode:

    python -m artbench setup <folder inside the Unity project> [--name NAME] [--github ACCOUNT] [--mcp claude]
    python -m artbench ops
    python -m artbench call asset --project demo --arg id=FBX/Props/Crate/Crate.fbx
    python -m artbench call send --project demo --arg id=... --arg force=true --json-args '{"files": ["..."]}'

The result is printed as JSON. Exit codes: 0 success, 1 the operation failed (the error is printed as JSON),
2 usage error (unknown operation, bad flags)."""
import argparse
import json
import os
import sys
import zipfile

from . import app_window, config, github_link, mcp_link, ops, workspace


def _parser():
    p = argparse.ArgumentParser(prog="python -m artbench")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("ops", help="list the operations and their arguments")
    s = sub.add_parser("setup", help="connect a game project on its own (project mode) and print the MCP lines")
    s.add_argument("path")
    s.add_argument("--name", default=None)
    s.add_argument("--github", default=None, help="the GitHub account this project pushes as (shown when gh is set to another)")
    s.add_argument("--mcp", choices=["claude"], default=None, help="also register the MCP server with Claude Code")
    z = sub.add_parser("addon", help="write the Blender add-on as a zip to install in Blender (Get Extensions > Install from Disk)")
    z.add_argument("out", nargs="?", default="artbench_bridge.zip")
    sub.add_parser("shortcut", help="put an Artbench shortcut on the desktop that opens the app window (Windows)")
    c = sub.add_parser("call", help="run one operation")
    c.add_argument("operation")
    c.add_argument("--project")
    c.add_argument("--arg", action="append", default=[], metavar="KEY=VALUE")
    c.add_argument("--json-args", default=None, metavar="JSON")
    c.add_argument("--compact", action="store_true", help="print the result on one line")
    return p


def main(argv, out=None):
    if out is None:                          # a pipe on Windows defaults to the ANSI code page: JSON goes out as UTF-8
        out = sys.stdout
        if hasattr(out, "reconfigure"):
            out.reconfigure(encoding="utf-8")
    try:
        a = _parser().parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.command == "setup":
        return _setup(a, out)
    if a.command == "addon":
        return _addon(a, out)
    if a.command == "shortcut":
        return _shortcut(out)
    if a.command == "ops":
        for o in (d for d in ops.describe() if ops.OPS[d["name"]].agents):
            props = o["params"].get("properties", {})
            required = set(o["params"].get("required", []))
            names = " ".join(k if k in required else f"[{k}]" for k in props)
            out.write(f"{o['name']}{' (writes)' if o['write'] else ''}: {names}\n")
        return 0
    op = ops.OPS.get(a.operation)
    if op is None or not op.agents:
        sys.stderr.write(f"unknown operation {a.operation!r}; see: python -m artbench ops\n")
        return 2
    args = {}
    for pair in a.arg:
        if "=" not in pair:
            sys.stderr.write(f"--arg needs KEY=VALUE, got {pair!r}\n")
            return 2
        key, value = pair.split("=", 1)
        args[key] = value
    args = ops.coerce(op, args)
    if a.json_args:
        try:
            extra = json.loads(a.json_args)
        except ValueError:
            sys.stderr.write("--json-args is not valid JSON\n")
            return 2
        if not isinstance(extra, dict):
            sys.stderr.write("--json-args must be a JSON object\n")
            return 2
        args.update(extra)
    if a.project:
        args["project"] = a.project
    indent = None if a.compact else 1
    try:
        result = ops.call(a.operation, args)
    except ops.OpError as e:
        out.write(json.dumps({"ok": False, "error": {"code": e.code, "message": e.message, "detail": e.detail}},
                             ensure_ascii=False, indent=indent) + "\n")
        return 1
    try:
        text = json.dumps(result, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError) as e:
        out.write(json.dumps({"ok": False, "error": {"code": "internal", "message": f"the result could not be encoded as JSON: {e}",
                                                     "detail": None}}, indent=indent) + "\n")
        return 1
    out.write(text + "\n")
    return 0


ADDON_DIR = os.path.join(config.TOOL_ROOT, "blender_addon", "artbench_bridge")


def _addon(a, out):
    """Zips blender_addon/artbench_bridge with its files at the zip's root, the layout Blender extensions install from."""
    path = os.path.abspath(a.out)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(ADDON_DIR)):
            full = os.path.join(ADDON_DIR, name)
            if os.path.isfile(full) and not name.endswith(".pyc"):
                z.write(full, name)
    out.write(f"Wrote {path}\nIn Blender: Edit > Preferences > Get Extensions > Install from Disk, pick this zip.\n"
              "The Artbench tab in the 3D view's sidebar holds the file's notes; with Artbench running (python -m artbench) it also shows the link and Send to Artbench.\n")
    return 0


def _setup(a, out):
    try:
        cfg = workspace.connect_project(a.path, a.name)
    except ValueError as e:
        out.write(f"Not connected: {e}\n")
        return 1
    github = None
    if a.github:
        try:
            github = github_link.set_github_account(cfg["id"], a.github)
        except ValueError as e:
            out.write(f"GitHub account not saved: {e}\n")
    counts = ops.catalog_counts(cfg)
    listed = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in sorted(counts["kinds"].items()))
    lines = mcp_link.mcp_lines()
    out.write(f"Connected {cfg['name']} (id {cfg['id']}, project mode)\n  {cfg['engine_root']}\n"
              f"  {sum(counts['kinds'].values())} assets: {listed or 'none'}\n"
              + (f"  GitHub account: {github['account']}" + (f" (gh is set to {github['active'] or 'nothing'}: {github['switch']})" if github["switch"] else "") + "\n" if github else "")
              + "\n"
              "Register Artbench with your AI tool (once per machine):\n"
              f"  Claude Code:\n    {lines['claude']}\n"
              f"  Gemini CLI (~/.gemini/settings.json):\n    {lines['gemini']}\n"
              "  Codex (~/.codex/config.toml):\n    " + lines["codex"].replace("\n", "\n    ") + "\n\n"
              "Open the page: python -m artbench (or Artbench.bat)\n")
    if a.mcp == "claude":
        out.write(mcp_link.register_claude()["message"] + "\n")
    return 0


def _shortcut(out, windows=None, run=None):
    try:
        path = app_window.create_shortcut(config.TOOL_ROOT, sys.executable, windows=windows,
                                          **({"run": run} if run else {}))
    except Exception as e:                 # Unavailable, or PowerShell missing or slow
        out.write(f"No shortcut: {e}\n")
        return 1
    out.write(f"Shortcut written: {path}\nDouble-click it to open Artbench in its own window.\n")
    return 0
