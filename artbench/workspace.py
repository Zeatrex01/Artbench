"""Connecting projects, GitHub style: first the game (engine) project, then the art folder for it, which is either
linked (it already exists) or created from the folder template below. The art folder carries its own
art_inventory.json and tracking files, so it can be moved or shared as a whole. Nothing here deletes files;
detaching a project only removes it from the registry. A connect keeps a progress record the page reads while it
waits (connect_progress): checking the folder, then the engine's own stages of reading the project."""
import copy
import functools
import json
import os
import re
import threading
import time

from . import config, engines, store
from .errors import NotFound

# Folder template of a new art folder (relative to the art folder). States, blend and texture roots match
# config.DEFAULTS; the archive sits inside so the folder stays self-contained.
TEMPLATE_STATES = {"ingame": "FBX", "outbox": "Outbox", "stock": "Stock", "archive": "_Archive"}
TEMPLATE_DIRS = ("FBX", "Outbox", "Stock", "_Archive", "Blend", "Textures")
DEFAULT_CATEGORIES = ["Characters", "Props", "Environment", "Weapons", "Blocks"]
README_NAME = "README.md"


# --- the progress of the connect that runs now (or ran last): one at a time, the server holds its lock meanwhile ------
_progress = {"state": "idle"}
_progress_lock = threading.Lock()


def connect_progress():
    """{state: idle | running | done | error, stage, stages: [{id, done, total}], current, name, project, message,
    started, elapsed}. Stages: "check" (the folder), then the engine's: "files", "meta", "refs", "settings"."""
    with _progress_lock:
        p = copy.deepcopy(_progress)
    if "started" in p:
        p["elapsed"] = round((p.get("ended") or time.time()) - p["started"], 2)
    return p


def _report(stage, done, total, current=""):
    with _progress_lock:
        stages = _progress.setdefault("stages", [])
        if not stages or stages[-1]["id"] != stage:
            stages.append({"id": stage, "done": 0, "total": 0})
        stages[-1].update(done=done, total=total)
        _progress.update(stage=stage, current=current)


def _tracked(fn):
    """Runs a connect with its progress record: running from the start, done with the project's id, or error with the
    reason (the exception still reaches the caller)."""
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with _progress_lock:
            _progress.clear()
            _progress.update(state="running", stage="check", stages=[{"id": "check", "done": 0, "total": 1}],
                             current="", name="", project=None, message="", started=time.time())
        try:
            cfg = fn(*args, **kwargs)
        except Exception as e:
            with _progress_lock:
                _progress.update(state="error", message=str(e), ended=time.time())
            raise
        with _progress_lock:
            _progress.update(state="done", project=cfg.get("id"), name=cfg.get("name") or cfg.get("id"), ended=time.time())
        return cfg
    return run


def check_engine(path):
    """What kind of engine project a path belongs to. {engine, project_root, assets_root, ok, message}."""
    if not (path or "").strip():
        return {"ok": False, "engine": None, "message": "no folder given"}
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return {"ok": False, "engine": None, "message": "folder does not exist"}
    for name, adapter in engines.ADAPTERS.items():
        found = adapter.detect(path)
        if found:
            content = found["content_root"]
            inside = path.lower().startswith(content.lower())
            return {"ok": True, "engine": name, "project_root": found["project_root"], "assets_root": content,
                    "engine_root": path if inside else content,
                    "message": f"{name.capitalize()} project" + ("" if inside else f"; art root set to {os.path.basename(content)}, narrow it if you want")}
    return {"ok": False, "engine": None, "message": "no engine project found above this folder (Unity: Assets + ProjectSettings; Godot: project.godot)"}


@_tracked
def connect(name, engine_root, art_parent, art_name=None, categories=None, create=True):
    """Registers a project: validates the engine folder, links or creates the art folder, writes its config, and
    reads the engine project once (so the first open is quick). Returns the loaded config. Raises ValueError with a
    readable message on bad input."""
    name = (name or "").strip()
    if not name:
        raise ValueError("project name is empty")
    engine = check_engine(engine_root)
    if not engine["ok"]:
        raise ValueError(engine["message"])
    _report("check", 1, 1, engine["project_root"])
    art_name = (art_name or "").strip() or _safe_name(name)
    if not os.path.isdir(art_parent or ""):
        raise ValueError("parent folder for the art folder does not exist")
    art_dir = os.path.normpath(os.path.join(art_parent, art_name))
    cfg_path = os.path.join(art_dir, config.CONFIG_NAME)
    if os.path.exists(cfg_path):
        raise ValueError(f"{art_dir} already has an {config.CONFIG_NAME}; link it from the registry instead")
    if not os.path.isdir(art_dir):
        if not create:
            raise ValueError(f"art folder does not exist: {art_dir}")
        os.makedirs(art_dir)
    for d in TEMPLATE_DIRS:
        os.makedirs(os.path.join(art_dir, d), exist_ok=True)
    for cat in categories or DEFAULT_CATEGORIES:
        os.makedirs(os.path.join(art_dir, "FBX", cat), exist_ok=True)
        os.makedirs(os.path.join(art_dir, "Blend", cat), exist_ok=True)
    cfg = {
        "id": _free_id(_safe_name(name).lower(), suffix="-art", mode="art"), "name": name, "engine": engine["engine"],
        "engine_root": engine["engine_root"].replace("\\", "/"),
        "engine_assets_root": engine["assets_root"].replace("\\", "/"),
        "art_root": ".", "states": dict(TEMPLATE_STATES), "blend_root": "Blend", "textures_root": "Textures",
        "categories": list(categories or DEFAULT_CATEGORIES),
        "engine_layout": "per_model",            # a project set up here: one engine folder per model, textures beside it
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    readme = os.path.join(art_dir, README_NAME)
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(_readme(name, cfg))
    register(cfg_path)
    loaded = config.load(cfg_path)
    store.log(loaded, "CONNECT", engine["engine_root"], art_dir)
    engines.of(loaded).build_dump(loaded, force=True, progress=_report)
    return loaded


@_tracked
def connect_project(engine_path, name=None):
    """Project mode: registers a game project on its own (no art folder). `engine_path` is any folder inside the
    engine project; the whole content root (Unity: Assets/) is inventoried. The config and every file Artbench keeps
    for the project live in config.DATA_ROOT/<id>/, never inside the engine project. Connecting the same project
    again (same root, project mode) updates its config. Returns the loaded config; ValueError on bad input."""
    engine = check_engine(engine_path)
    if not engine["ok"]:
        raise ValueError(engine["message"])
    _report("check", 1, 1, engine["project_root"])
    content = os.path.normpath(engine["assets_root"])
    project_root = os.path.normpath(engine["project_root"])
    known = [c for c in config.projects() if "error" not in c]
    same = next((c for c in known if config.is_project_mode(c) and c.get("engine_root")
                 and os.path.normcase(os.path.normpath(c["engine_root"])) == os.path.normcase(content)), None)
    if same:
        project_id, folder = same["id"], os.path.dirname(same["config_path"])
    else:
        project_id = _free_id(_safe_name(os.path.basename(project_root)).lower(), suffix="-project", mode="project")
        folder = os.path.join(config.DATA_ROOT, project_id)
    os.makedirs(folder, exist_ok=True)
    cfg_path = os.path.join(folder, config.CONFIG_NAME)
    cfg = store._read_json(cfg_path, {}) if same else {}     # connecting again keeps the user's own edits
    cfg = cfg if isinstance(cfg, dict) else {}
    cfg.update({
        "id": project_id, "name": (name or "").strip() or cfg.get("name") or os.path.basename(project_root),
        "mode": "project", "engine": engine["engine"],
        "engine_root": content.replace("\\", "/"), "engine_assets_root": content.replace("\\", "/"),
    })
    # StreamingAssets is listed (its files are loaded by name); third-party packs are read for references only.
    cfg.setdefault("engine_ignore_dump", engines.of(cfg).dump_ignore(project_mode=True))
    store._write_json(cfg_path, cfg)
    register(cfg_path)
    loaded = config.load(cfg_path)
    store.log(loaded, "CONNECT", project_root, "project mode")
    engines.of(loaded).build_dump(loaded, force=True, progress=_report)
    return loaded


def taken_ids():
    """{id: mode or None} of every registered project, the unreadable ones too: a config on an unplugged drive or an
    offline OneDrive folder keeps its id (taken from its folder's name, as connect names it), so no new project takes
    it and two entries never share an id when the drive is back."""
    out = {}
    for path in config.registry():
        cfg = config.load_quiet(path)
        if "error" in cfg:
            folder = os.path.basename(os.path.dirname(os.path.normpath(path)))
            out.setdefault(_safe_name(folder).lower(), None)
        else:
            out[cfg.get("id")] = cfg.get("mode")
    return out


def _free_id(base, suffix, mode):
    """`base`, or `<base><suffix>` when a project of the other mode (or an unreadable one) already has that id, then
    -2, -3, ... until free (a second clone of the same mode is `<base>-2`)."""
    taken = taken_ids()
    candidate = base
    if candidate in taken and taken[candidate] != mode:
        candidate = base + suffix
    out, n = candidate, 1
    while out in taken:
        n += 1
        out = f"{candidate}-{n}"
    return out


@_tracked
def link(cfg_path):
    """Adds an existing art folder (one that already has an art_inventory.json) to the registry and reads its engine
    project once, when that is reachable."""
    cfg_path = os.path.normpath(cfg_path)
    if os.path.isdir(cfg_path):
        cfg_path = os.path.join(cfg_path, config.CONFIG_NAME)
    if not os.path.isfile(cfg_path):
        raise ValueError(f"no {config.CONFIG_NAME} at {cfg_path}")
    loaded = config.load(cfg_path)         # raises on a broken file
    _report("check", 1, 1, os.path.dirname(cfg_path))
    register(cfg_path)
    engines.of(loaded).build_dump(loaded, force=True, progress=_report)
    return loaded


def detach(project_id):
    """Removes a project from the registry. Its folders and files stay where they are."""
    entries = config.registry()
    keep = [p for p in entries if config.load_quiet(p).get("id") != project_id]
    if len(keep) == len(entries):
        raise KeyError(f"project {project_id}")
    _save_registry(keep)
    return True


def register(cfg_path):
    entries = config.registry()
    norm = os.path.normpath(cfg_path).replace("\\", "/")
    if norm not in [os.path.normpath(p).replace("\\", "/") for p in entries]:
        entries.append(norm)
        _save_registry(entries)


def _safe_name(name):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "Project"


def _save_registry(entries):
    with open(config.REGISTRY, "w", encoding="utf-8") as f:
        json.dump({"projects": entries}, f, indent=2)


def _readme(name, cfg):
    states = cfg["states"]
    return (
        f"# {name} art folder\n\n"
        "Managed by Artbench. Layout:\n\n"
        f"- `{states['ingame']}/<Category>/<Set>/` models that are in the game, textures beside them\n"
        f"- `{states['outbox']}/<Category>/` finished, waiting to be sent to the engine\n"
        f"- `{states['stock']}/<Category>/` ready models that are not in the game\n"
        f"- `{states['archive']}/<date>/` replaced files (nothing is deleted)\n"
        f"- `{cfg['blend_root']}/<Category>/` Blender sources\n"
        f"- `{cfg['textures_root']}/<Set>/` shared texture sets\n\n"
        "Tracking files written by the tool: `art_inventory.json` (config), `inventory.json` (notes), "
        "`tasks.json`, `inventory_history.log`, `engine_index.json` (engine dump).\n"
    )


def hide_folder(project_id, folder, hidden=True):
    """Hides a folder of the engine project from the catalog (hidden=False shows it again): an engine_ignore_dump
    entry "Assets/<path>", so its assets leave the catalog while what they reference still counts. Rebuilds the dump
    and writes a HIDE or SHOW history line. Returns the project's ignore list. ValueError for a path that is not a
    folder under the content root (Unity: Assets/, Godot: res://), NotFound for an unknown project."""
    cfg = next((c for c in config.projects() if c.get("id") == project_id and "error" not in c), None)
    if cfg is None:
        raise NotFound(f"project {project_id}")
    prefix = engines.of(cfg).prefix                        # "Assets/" or "res://"
    path = (folder or "").replace("\\", "/")
    if path.startswith(prefix):
        path = path[len(prefix):]
    elif prefix == "Assets/" and path.strip("/") == "Assets":
        path = ""
    parts = [p for p in path.strip("/").split("/") if p]
    if path.startswith("/") or ":" in path or ".." in parts:
        raise ValueError(f"not a folder under {prefix}: {folder!r}")
    if not parts:
        raise ValueError(f"the {prefix.rstrip('/:')} folder itself cannot be hidden" if prefix == "Assets/"
                         else "the project folder itself cannot be hidden")
    entry = prefix + "/".join(parts)
    raw = store._read_json(cfg["config_path"], {})
    raw = raw if isinstance(raw, dict) else {}
    adapter = engines.of(cfg)
    current = list(raw.get("engine_ignore_dump", adapter.dump_ignore(project_mode=config.is_project_mode(cfg))))
    if hidden and entry not in current:
        current.append(entry)
    elif not hidden:
        current = [e for e in current if e != entry]
    raw["engine_ignore_dump"] = current
    store._write_json(cfg["config_path"], raw)
    store.log(cfg, "HIDE" if hidden else "SHOW", entry, "folder in the catalog")
    loaded = config.load(cfg["config_path"])
    adapter.build_dump(loaded, force=True)
    return current
