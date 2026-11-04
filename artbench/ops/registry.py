"""The registry and the calls: the operations' definitions in contract order, argument coercion and checks, and
the mapping of every failure to an OpError."""
from .. import config
from . import assets, machine, transfer, work
from ..errors import Conflict, NeedsForce, NotFound, OutsideRoot, Unavailable, WarningsNotAccepted, WrongMode
from .common import ART_ONLY, BRIDGE_ONLY, Op, OpError, WRITE_OPS, _P, _PAGE, _schema


_DEFS = [
    {"name": "projects", "description": "List the registered projects (id, name, mode, art folder, engine root). Mode 'project' is a game project on its own (its art inventory, no art folder); mode 'art' also has an art folder bridged to the engine.",
     "params": _schema({})},
    {"name": "overview",
     "description": "Counts for a project. Project mode: assets per kind, per usage (used, unreferenced, by_name, unknown), hidden kinds, placeholders, layout issues, whether the project is Force Text, changes since the last Mark as seen. Art mode: models per state, used/unused, engine-only, placeholders, layout issues, open tasks. Call it first to get the shape of a project.",
     "params": _schema(_P, ["project"])},
    {"name": "search",
     "description": "Find assets by name or path, case-insensitive. Project mode: every catalog asset (model, texture, material, prefab, scene, ...). Art mode: desktop models, engine-only models, placeholders. Returns ids to use with artbench_asset.",
     "params": _schema({**_P, "query": {"type": "string"}, "limit": {"type": "integer", "default": 30}}, ["project", "query"])},
    {"name": "asset",
     "description": "Full detail of one asset by id. Project mode: kind, path, size, usage, what uses it (used_by) and what it uses (uses), each capped at 50 rows with the full counts, tasks tied to it. Art mode: state, paths, sync with the engine, where it is used, textures, note, tasks.",
     "params": _schema({**_P, "id": {"type": "string", "description": "Item id (path under the art root) or engine:<path>"}}, ["project", "id"])},
    {"name": "unused",
     "description": "What nothing seems to use. Project mode: 'unreferenced' (no file in the project references it: likely unused, but check before deleting), 'by_name' (in Resources or StreamingAssets: loaded by name from code, so references cannot show use) and the count of 'unknown' (the project is not Force Text); each list is paged (offset, limit up to 500) with unreferenced_total / by_name_total. Art mode: models the engine does not reference.",
     "params": _schema({**_P, **_PAGE}, ["project"])},
    {"name": "placeholders",
     "description": "Code-made mesh .asset files under the engine art root, with usage: the places still waiting for a real model.",
     "params": _schema(_P, ["project"])},
    {"name": "layout_issues",
     "description": "Engine assets sitting outside the folder a layout rule expects (advisory). Project mode: only the project's own layout_rules are applied (none configured: no issues) and the answer is paged {total, offset, issues}.",
     "params": _schema({**_P, **_PAGE}, ["project"])},
    {"name": "graph_neighbors",
     "description": "Reference graph around one engine asset: what it references and what references it, up to N hops. path takes an Assets/... path, an engine:... id, a path relative to Assets, or a file name when only one asset has it. At most 200 edges; edges_total and truncated say when there are more.",
     "params": _schema({**_P, "path": {"type": "string", "description": "Assets/... path, engine:... id, path relative to Assets, or a unique file name"},
                             "hops": {"type": "integer", "default": 1}}, ["project", "path"])},
    {"name": "tasks", "description": "The person's task board: tasks in board order (to do, doing, done; high priority first), optionally only one status (todo, doing, done), optionally only the tasks tied to the given asset ids (assets).",
     "params": _schema({**_P, "status": {"type": "string"}, "assets": {"type": "array", "items": {"type": "string"}}}, ["project"])},
    {"name": "task_add", "description": "Add a task to the person's board (their priorities), optionally tied to an asset id (from artbench_search or artbench_catalog) so it also shows on that asset. priority: high, normal (default) or low.",
     "params": _schema({**_P, "title": {"type": "string"}, "asset": {"type": "string"}, "note": {"type": "string"},
                        "priority": {"type": "string", "enum": ["high", "normal", "low"]}}, ["project", "title"])},
    {"name": "task_update", "description": "Change a task's status (todo, doing, done), priority (high, normal, low), title, note or asset.",
     "params": _schema({**_P, "id": {"type": "string"}, "status": {"type": "string"}, "title": {"type": "string"},
                             "note": {"type": "string"}, "asset": {"type": "string"},
                             "priority": {"type": "string", "enum": ["high", "normal", "low"]}}, ["project", "id"])},
    {"name": "note", "description": "Set (or clear with an empty string) the note on an asset id.",
     "params": _schema({**_P, "id": {"type": "string"}, "note": {"type": "string"}}, ["project", "id", "note"])},
    {"name": "move",
     "description": "Move a desktop model to another state folder (ingame, outbox, stock, archive). Files are moved, never deleted; the move is logged.",
     "params": _schema({**_P, "id": {"type": "string"}, "state": {"type": "string"}}, ["project", "id", "state"])},
    {"name": "history", "description": "Recent history lines (moves, notes, tasks), newest first.",
     "params": _schema({**_P, "limit": {"type": "integer", "default": 50}}, ["project"])},
    {"name": "refresh", "description": "Rebuild the engine dump now and return the overview.",
     "params": _schema(_P, ["project"])},
    {"name": "changes",
     "description": "What changed on disk since earlier looks, newest first, whoever changed it (a branch switch or pull shows up here). Project mode: assets ADDED, REMOVED, CHANGED or MOVED (with `from`). Art mode: files of the art folder and the engine root. since_seen: only what came after the person's last Mark as seen; mark_seen: mark everything as seen now (returns the mark).",
     "params": _schema({**_P, "limit": {"type": "integer", "default": 100}, "since_seen": {"type": "boolean", "default": False},
                        "mark_seen": {"type": "boolean", "default": False}}, ["project"])},
    {"name": "send_plan",
     "description": "What sending a desktop model to the engine would do: target path, overwrite or new, backup path, FBX fingerprint warnings.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "send",
     "description": "Send a desktop model and its package files (textures; for a .gltf also the buffers and images it names) to the engine (each overwritten file archived, .meta untouched). Without `files` the default selection is sent: files the team changed in the engine since the last sync are left out unless force is true. `files` names the file ids to send (see artbench_send_plan). Refused when fingerprint warnings exist unless accept_warnings is true.",
     "params": _schema({**_P, "id": {"type": "string"}, "accept_warnings": {"type": "boolean", "default": False},
                             "force": {"type": "boolean", "default": False},
                             "files": {"type": "array", "items": {"type": "string"}},
                             "expect": {"type": "object", "description": "From the plan you confirmed: {file id: target_sha} or {file id: {target, source}}; refused (conflict) when a file changed since"}}, ["project", "id"])},
    {"name": "pull_plan",
     "description": "What pulling the engine copy of a desktop model over the desktop copy would do: source, target, backup path, sync state, requires_force.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "pull",
     "description": "Pull the engine copies of a model's package (textures, .gltf buffers and images) over the desktop copies (old desktop copies archived). Without `files` every file the engine changed is pulled; files also changed on the desktop since the last sync need force. `files` names the file ids (see artbench_pull_plan).",
     "params": _schema({**_P, "id": {"type": "string"}, "force": {"type": "boolean", "default": False},
                             "files": {"type": "array", "items": {"type": "string"}},
                             "expect": {"type": "object", "description": "From the plan you confirmed: {file id: target_sha} or {file id: {target, source}}; refused (conflict) when a file changed since"}}, ["project", "id"])},
    {"name": "bring_in_plan",
     "description": "Where bringing an engine-only model (id engine:<path>) into the art folder would put it: FBX/<category>/<model>/<file>. Without category the guess from its engine path is used; category null means none was found and one must be given. Only the model is copied; its textures stay in the engine.",
     "params": _schema({**_P, "id": {"type": "string"}, "category": {"type": "string"}}, ["project", "id"])},
    {"name": "bring_in",
     "description": "Bring an engine-only model (id engine:<path>) into the art folder as FBX/<category>/<model>/<file>: only the model is copied (textures stay in the engine), both sides recorded as the same, the new desktop model marked imported {from, time}, one BRING IN history line. Refused when the target exists.",
     "params": _schema({**_P, "id": {"type": "string"}, "category": {"type": "string"}}, ["project", "id", "category"])},
    {"name": "metadata_snapshot",
     "description": "Metadata snapshot of a desktop model (objects with vertex counts, materials, textures, bones, animations, bounding box), from background Blender. state may be 'pending' while Blender works: call again.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "metadata_diff",
     "description": "What sending a desktop model would change in the engine: structural diff, summary lines, Unity-compatibility warnings, affected prefabs/scenes; in a conflict also what each side changed since the last sync. state may be 'pending' while Blender works: call again.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
]


_DEFS += [
    {"name": "catalog",
     "description": "The project's art catalog, filtered and paged: every asset of the listed kinds with kind, path, size and usage. usage is one of used (something references it), unreferenced (nothing in the project's files references it), by_name (loaded by name from code: Resources, StreamingAssets), unknown (the project is not Force Text, so references cannot be read). Filters: kind, usage, folder (an Assets/ path prefix), search; offset and limit (max 500) page the answer, total says how many match.",
     "params": _schema({**_P, "kind": {"type": "string"}, "usage": {"type": "string"}, "folder": {"type": "string"},
                        "search": {"type": "string"}, "offset": {"type": "integer", "default": 0},
                        "limit": {"type": "integer", "default": 100}}, ["project"])},
]


_DEFS += [
    {"name": "meta", "description": "Set or clear (empty string) fields on an asset id: note, source, engine_path, blend (a .blend id under the art root).",
     "params": _schema({**_P, "id": {"type": "string"}, "note": {"type": "string"}, "source": {"type": "string"},
                        "engine_path": {"type": "string"}, "blend": {"type": "string"}}, ["project", "id"])},
    {"name": "preview", "description": "Preview image of a desktop model: state (ready, pending, failed, none) and the PNG path when ready. Call again while pending.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
]


_DEFS += [
    {"name": "engine_report", "description": "For engine bridges: a live report of scene contents and asset events (schema 1, see ARCHITECTURE.md). Stored in the tool cache; never written into the engine project.",
     "params": _schema({**_P, "report": {"type": "object"}}, ["project", "report"])},
    {"name": "scene_inventory", "description": "What each scene uses (read-only): prefabs, models, meshes, materials, textures, followed to the art files, each matched to its art item with sync state. source is 'live' when a fresh engine-bridge report covers the scene, else 'files'. Optional scene: a path such as Assets/Scenes/Main.unity.",
     "params": _schema({**_P, "scene": {"type": "string"}}, ["project"])},
    {"name": "doctor", "description": "Machine checks for this project: engine folder, dump, art folder writable, the project lock across processes, hashing, long paths, OneDrive, Blender, the page server. Each check says ok, warn, fail or skip with a detail. Writes nothing into the engine project.",
     "params": _schema(_P, ["project"])},
    {"name": "engine_status", "description": "Whether an engine bridge has reported: bridge name, last report time, scenes with freshness, recent asset events.",
     "params": _schema(_P, ["project"])},
    {"name": "blender_status", "description": "Whether Blender is open on this machine with the Artbench add-on, which .blend it has open (empty while unsaved), the Blender version, and which registered project that file belongs to. open is false when the add-on has not reported for 15 seconds.",
     "params": _schema({})},
    {"name": "layout_settings", "description": "Layout rules (where each kind of asset should live). Off until turned on. enabled=true turns it on, learning the rules from where the project's assets are now when it has none of its own; enabled=false turns it off and keeps the rules; allow_kind with allow_folder ('' for the root) accepts a folder for that kind. With no arguments it only reports. Returns {enabled, rules, proposed}.",
     "params": _schema({**_P, "enabled": {"type": "boolean"}, "allow_kind": {"type": "string"}, "allow_folder": {"type": "string"}}, ["project"])},
    {"name": "open_in_blender", "description": "Open a model in Blender's window on this machine: a .blend as it is; FBX, OBJ or glTF imported into an empty scene. An art-folder model with a .blend source opens that .blend. id is a catalog id (engine:...) in project mode or an item id in art mode.",
     "params": _schema({**_P, "id": {"type": "string"}}, ["project", "id"])},
    {"name": "blender_report", "description": "For the Blender add-on: Blender is open with this file (sent every few seconds); closing=true when it quits.",
     "params": _schema({"file": {"type": "string"}, "blender": {"type": "string"}, "pid": {"type": "integer"},
                        "closing": {"type": "boolean", "default": False}}, ["file", "blender", "pid"])},
    {"name": "blender_notes_send", "description": "For the Blender add-on: the notes of this .blend (its last send replaces the one before; an empty list removes them). Each note: text, kind (todo or note), done, priority (high, normal, low), object (a name or null).",
     "params": _schema({"file": {"type": "string"}, "notes": {"type": "array", "items": {"type": "object"}}}, ["file", "notes"])},
    {"name": "blender_notes", "description": "The notes artists sent from Blender for this project's .blend files: [{asset, name, file, sent, notes}], newest send first. Read only: the notes live in the .blend.",
     "params": _schema({**_P}, ["project"])},
]


for _d in _DEFS:
    if _d["name"] == "asset":
        _d["description"] += " Instead of id, engine_path (a path under Assets/) or guid finds the asset the engine knows."
        _d["params"]["properties"].update({"engine_path": {"type": "string"}, "guid": {"type": "string"}})
        _d["params"]["required"] = ["project"]


for _d in _DEFS:
    if _d["name"] in ART_ONLY:
        _d["description"] += " Art mode only (projects with an art folder)."


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
