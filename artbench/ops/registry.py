"""The registry and the calls: the operations' definitions in contract order, argument coercion and checks, and
the mapping of every failure to an OpError."""
from .. import config
from . import assets, machine, transfer, work
from ..errors import Conflict, NeedsForce, NotFound, OutsideRoot, Unavailable, WarningsNotAccepted, WrongMode
from .common import ART_ONLY, BRIDGE_ONLY, Op, OpError, WRITE_OPS, _P, _PAGE, _schema


_DEFS = [
    {"name": "projects", "description": "Registered projects: id, name, mode ('project': a Unity project alone; 'art': with an art folder).",
     "params": _schema({})},
    {"name": "overview",
     "description": "Start here: the project's map. Counts per kind and usage, assets per folder, tasks (todo, doing, done, high_open), changes since the last look. Art mode: models per state.",
     "params": _schema(_P, ["project"])},
    {"name": "search",
     "description": "Find assets by name or path. Brief rows {id, kind, usage, used_by_count}; an id is engine:<path under Assets/>.",
     "params": _schema({**_P, "query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, ["project", "query"])},
    {"name": "asset",
     "description": "One asset in full by id: path, size, usage, used_by and uses (50 rows each, with counts), its tasks.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "unused",
     "description": "Unreferenced assets (likely unused: check before deleting) and by_name ones (Resources, StreamingAssets: loaded from code), as brief rows, paged (offset, limit 25).",
     "params": _schema({**_P, **_PAGE}, ["project"])},
    {"name": "placeholders",
     "description": "Code-made mesh .asset files still waiting for a real model, with usage.",
     "params": _schema(_P, ["project"])},
    {"name": "layout_issues",
     "description": "Assets outside the folder their layout rule expects (advisory; none while Layout is off). Paged.",
     "params": _schema({**_P, **_PAGE}, ["project"])},
    {"name": "graph_neighbors",
     "description": "What an asset references and what references it, up to hops. path: an Assets/ path, an engine: id or a unique file name. At most 200 edges.",
     "params": _schema({**_P, "path": {"type": "string"},
                             "hops": {"type": "integer", "default": 1}}, ["project", "path"])},
    {"name": "tasks", "description": "The task board, high priority first. status: todo, doing, done or open (todo and doing); assets: only tasks tied to these ids; limit (50).",
     "params": _schema({**_P, "status": {"type": "string"}, "assets": {"type": "array", "items": {"type": "string"}},
                        "limit": {"type": "integer", "default": 50}}, ["project"])},
    {"name": "task_add", "description": "Add a task; asset ties it to an asset id. priority: high, normal (default), low.",
     "params": _schema({**_P, "title": {"type": "string"}, "asset": {"type": "string"}, "note": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "normal", "low"]}}, ["project", "title"])},
    {"name": "task_update", "description": "Change a task's status, priority, title, note or asset.",
     "params": _schema({**_P, "id": {"type": "string"}, "status": {"type": "string"}, "title": {"type": "string"},
                             "note": {"type": "string"}, "asset": {"type": "string"},
                             "priority": {"type": "string", "enum": ["high", "normal", "low"]}}, ["project", "id"])},
    {"name": "note", "description": "Set or clear the note on an asset id.",
     "params": _schema({**_P, "id": {"type": "string"}, "note": {"type": "string"}}, ["project", "id", "note"])},
    {"name": "move",
     "description": "Move a desktop model to another state (ingame, outbox, stock, archive). Never deletes.",
     "params": _schema({**_P, "id": {"type": "string"}, "state": {"type": "string"}}, ["project", "id", "state"])},
    {"name": "history", "description": "Recent history lines, newest first.",
     "params": _schema({**_P, "limit": {"type": "integer", "default": 50}}, ["project"])},
    {"name": "refresh", "description": "Re-read the engine project now; returns the overview.",
     "params": _schema(_P, ["project"])},
    {"name": "changes",
     "description": "What changed on disk, newest first (added, removed, changed, moved). since_seen: only after the last Mark as seen; mark_seen: mark everything seen.",
     "params": _schema({**_P, "limit": {"type": "integer", "default": 100}, "since_seen": {"type": "boolean", "default": False},
                        "mark_seen": {"type": "boolean", "default": False}}, ["project"])},
    {"name": "send_plan",
     "description": "What sending a desktop model to the engine would do: target, overwrite, backup, warnings.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "send",
     "description": "Send a desktop model and its package (textures; a .gltf's buffers and images) to the engine (old copies archived, .meta kept). files: ids from send_plan; force for files the team changed; accept_warnings for fingerprint warnings.",
     "params": _schema({**_P, "id": {"type": "string"}, "accept_warnings": {"type": "boolean", "default": False},
                             "force": {"type": "boolean", "default": False},
                             "files": {"type": "array", "items": {"type": "string"}},
                             "expect": {"type": "object", "description": "From the confirmed plan: {file id: target_sha}; conflict when a file changed since"}}, ["project", "id"])},
    {"name": "pull_plan",
     "description": "What pulling the engine copy of a model over the desktop copy would do.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "pull",
     "description": "Pull the engine copies of a model's package (textures, .gltf buffers and images) over the desktop (old copies archived). files: ids from pull_plan; force for files changed on both sides.",
     "params": _schema({**_P, "id": {"type": "string"}, "force": {"type": "boolean", "default": False},
                             "files": {"type": "array", "items": {"type": "string"}},
                             "expect": {"type": "object", "description": "From the confirmed plan: {file id: target_sha}; conflict when a file changed since"}}, ["project", "id"])},
    {"name": "bring_in_plan",
     "description": "Where bringing an engine-only model (engine:<path>) into the art folder would put it; category null means one must be given.",
     "params": _schema({**_P, "id": {"type": "string"}, "category": {"type": "string"}}, ["project", "id"])},
    {"name": "bring_in",
     "description": "Copy an engine-only model into the art folder as FBX/<category>/<model>/ (textures stay in the engine). Refused when the target exists.",
     "params": _schema({**_P, "id": {"type": "string"}, "category": {"type": "string"}}, ["project", "id", "category"])},
    {"name": "metadata_snapshot",
     "description": "A desktop model's structure from Blender (objects, vertices, materials, bones, animations). state pending: call again.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "metadata_diff",
     "description": "What sending a model would change in the engine, with warnings and the prefabs and scenes it reaches. state pending: call again.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
]


_DEFS += [
    {"name": "catalog",
     "description": "The asset catalog, filtered (kind, usage, folder: an Assets/ prefix, search) and paged (offset, limit 25, at most 500; total). Brief rows {id, kind, usage, used_by_count}; detail=full adds path, size, used_by, uses. usage: used, unreferenced, by_name (loaded from code), unknown (not Force Text).",
     "params": _schema({**_P, "kind": {"type": "string"}, "usage": {"type": "string"}, "folder": {"type": "string"},
                        "search": {"type": "string"}, "detail": {"type": "string", "enum": ["brief", "full"]},
                        "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 25}}, ["project"])},
]


_DEFS += [
    {"name": "meta", "description": "Set or clear fields on an asset id: note, source, engine_path, blend.",
     "params": _schema({**_P, "id": {"type": "string"}, "note": {"type": "string"}, "source": {"type": "string"},
                        "engine_path": {"type": "string"}, "blend": {"type": "string"}}, ["project", "id"])},
    {"name": "preview", "description": "A desktop model's preview PNG: state ready, pending (call again), failed or none.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
]


_DEFS += [
    {"name": "engine_report", "description": "For engine bridges: a live report of scene contents and asset events (schema 1, see ARCHITECTURE.md). Stored in the tool cache; never written into the engine project.",
     "params": _schema({**_P, "report": {"type": "object"}}, ["project", "report"])},
    {"name": "scene_inventory", "description": "What each scene uses, followed through prefabs and materials to the art files. scene: one Assets/ .unity path. source live: a fresh bridge report.",
     "params": _schema({**_P, "scene": {"type": "string"}}, ["project"])},
    {"name": "doctor", "description": "Machine checks for this project (folders, dump, lock, long paths, OneDrive, Blender, server), each ok, warn, fail or skip.",
     "params": _schema(_P, ["project"])},
    {"name": "engine_status", "description": "Whether an engine bridge has reported: bridge, last report, scenes, recent events.",
     "params": _schema(_P, ["project"])},
    {"name": "blender_status", "description": "Whether Blender is open with the add-on, its .blend and the project that file belongs to.",
     "params": _schema({})},
    {"name": "layout_settings", "description": "Layout rules. No arguments: report. enabled=true turns them on (learned from the project), false off; allow_kind with allow_folder accepts a folder.",
     "params": _schema({**_P, "enabled": {"type": "boolean"}, "allow_kind": {"type": "string"}, "allow_folder": {"type": "string"}}, ["project"])},
    {"name": "open_in_blender", "description": "Open a model in Blender on this machine (a .blend as it is; FBX, OBJ, glTF imported).",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "blender_report", "description": "For the Blender add-on: Blender is open with this file (sent every few seconds); closing=true when it quits.",
     "params": _schema({"file": {"type": "string"}, "blender": {"type": "string"}, "pid": {"type": "integer"},
                        "closing": {"type": "boolean", "default": False}}, ["file", "blender", "pid"])},
    {"name": "blender_notes_send", "description": "For the Blender add-on: the notes of this .blend (its last send replaces the one before; an empty list removes them). Each note: text, kind (todo or note), done, priority (high, normal, low), object (a name or null).",
     "params": _schema({"file": {"type": "string"}, "notes": {"type": "array", "items": {"type": "object"}}}, ["file", "notes"])},
    {"name": "blender_notes", "description": "Notes artists sent from Blender for this project's .blend files, newest first.",
     "params": _schema({**_P}, ["project"])},
]


for _d in _DEFS:
    if _d["name"] == "asset":
        _d["description"] += " Instead of id: engine_path (under Assets/) or guid."
        _d["params"]["properties"].update({"engine_path": {"type": "string"}, "guid": {"type": "string"}})
        _d["params"]["required"] = ["project"]


for _d in _DEFS:
    if _d["name"] in ART_ONLY:
        _d["description"] += " Art mode only."


_IMPL = {name: fn for mod in (assets, work, transfer, machine) for name, fn in vars(mod).items() if name.startswith("op_")}

OPS = {d["name"]: Op(d["name"], d["description"], d["params"], _IMPL["op_" + d["name"]], write=d["name"] in WRITE_OPS,
          agents=d["name"] not in BRIDGE_ONLY, modes=("art",) if d["name"] in ART_ONLY else ("art", "project"))
       for d in _DEFS}


_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}


def describe():
    """[{name, description, params, write}] for every operation (the /api/v1 self-description)."""
    return [{"name": o.name, "description": o.description, "params": o.params, "write": o.write} for o in OPS.values()]


def coerce(op, args):
    """Arguments from a query string or command line arrive as strings: convert them by the operation's schema."""
    out = dict(args)
    for key, spec in op.params.get("properties", {}).items():
        value = out.get(key)
        if not isinstance(value, str):
            continue
        kind = spec.get("type")
        if kind == "integer" and value.lstrip("-").isdigit():
            out[key] = int(value)
        elif kind == "boolean" and value.lower() in ("true", "false", "1", "0", "yes", "no"):
            out[key] = value.lower() in ("true", "1", "yes")
        elif kind == "array":
            out[key] = [v for v in value.split(",") if v]
    return out


def call(name, args):
    """Runs one operation; every failure comes out as OpError."""
    op = OPS.get(name)
    if op is None:
        raise OpError("not_found", f"unknown operation {name!r}")
    if not isinstance(args, dict):
        raise OpError("bad_request", "arguments must be a JSON object")
    args = coerce(op, args)                  # the same leniency whichever transport the arguments came through
    props = op.params.get("properties", {})
    for key in op.params.get("required", []):
        if args.get(key) is None:
            raise OpError("bad_request", f"missing argument {key!r}")
    for key, value in args.items():
        kind = props.get(key, {}).get("type")
        want = _TYPES.get(kind)
        if want and value is not None and (not isinstance(value, want) or (kind == "integer" and isinstance(value, bool))):
            raise OpError("bad_request", f"argument {key!r} must be {kind}")
    try:
        _check_mode(op, args)
        return op.fn(args)
    except Exception as e:  # noqa: BLE001  (every failure is reported with a code)
        raise to_error(e) from e


def _check_mode(op, args):
    """WrongMode when the named project's mode is one the operation does not serve (an unknown project is left to
    the operation, which reports not_found)."""
    project = args.get("project")
    if project is None:
        return
    for cfg in config.projects():
        if cfg.get("id") == project and "error" not in cfg:
            if cfg.get("mode", "art") not in op.modes:
                raise WrongMode(f"{op.name} is not available for {project!r}: it is a {cfg.get('mode')}-mode project "
                                f"(the game project on its own, no art folder)")
            return


def to_error(exc):
    """Maps a module exception to an OpError by its type (errors.py); messages are never parsed for the code."""
    if isinstance(exc, OpError):
        return exc
    msg = str(exc)
    for kind, code in ((NotFound, "not_found"), (NeedsForce, "needs_force"), (WarningsNotAccepted, "warnings"),
                       (OutsideRoot, "outside_root"), (Unavailable, "unavailable"), (Conflict, "conflict"),
                       (FileExistsError, "conflict"), (TimeoutError, "busy"), (WrongMode, "wrong_mode")):
        if isinstance(exc, kind):
            return OpError(code, msg)
    if type(exc) is ValueError:              # the modules' own validation messages
        return OpError("bad_request", msg)
    return OpError("internal", f"{type(exc).__name__}: {msg}")
