"""The Blender bridge, first step: the add-on (blender_addon/artbench_bridge) reports every few seconds that Blender is
open and which .blend it has; agents ask whether Blender is open, which file, and which project that file belongs to.
The last report is kept in one machine-wide file beside the project-mode data (it is about this machine's Blender,
not about a project), so the page server and a separate MCP process read the same answer."""
import os
import subprocess
import sys
import time

from . import blender_jobs, config, scan, store
from .errors import Unavailable

FRESH_SECONDS = 15                   # a report older than this means Blender is closed (or hung); the add-on sends every 5
INFO_SECONDS = 20                    # how long the file's place in its project is reused (a report comes every 5 s)
_info_cache = {}                     # path -> (monotonic time, {"project", "asset", "models"})


def _path():
    return os.path.join(config.DATA_ROOT, "blender_session.json")


def report(file, blender, pid, closing=False):
    """Keeps the add-on's report. file is the open .blend ("" while unsaved); closing marks Blender closed at once."""
    if not isinstance(file, str) or not isinstance(blender, str) or not isinstance(pid, int) or isinstance(pid, bool):
        raise ValueError("a report needs file (text, empty while unsaved), blender (version text) and pid (a number)")
    os.makedirs(config.DATA_ROOT, exist_ok=True)
    store._write_json(_path(), {"file": file, "blender": blender, "pid": pid, "seen": time.time(), "closed": bool(closing)})
    return status()


def _inside(path, root):
    target, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return target == base or target.startswith(base.rstrip(os.sep) + os.sep)


def _project_of(path):
    """The id of the registered project whose art folder or engine project holds path, or None."""
    cfg = _project_cfg(path)
    return cfg.get("id") if cfg else None


def _project_cfg(path):
    if not path:
        return None
    for cfg in config.projects():
        if "error" not in cfg and any(root and _inside(path, root) for root in (cfg.get("art_root"), cfg.get("engine_root"))):
            return cfg
    return None


def file_info(path):
    """{project, asset, models}: the project holding the file, the file's id there (its path under the art folder, or
    engine:<path> inside the game project), and the models made from it (desktop models bound to this .blend, by name
    or by an explicit binding). Reused for INFO_SECONDS, since the add-on asks every few seconds."""
    now = time.monotonic()
    hit = _info_cache.get(path)
    if hit and now - hit[0] < INFO_SECONDS:
        return hit[1]
    cfg = _project_cfg(path)
    info = {"project": None, "asset": None, "models": []}
    if cfg:
        info["project"] = cfg.get("id")
        if cfg.get("art_root") and _inside(path, cfg["art_root"]):
            info["asset"] = os.path.relpath(path, cfg["art_root"]).replace("\\", "/")
            target = os.path.normcase(os.path.abspath(path))
            info["models"] = sorted(i["id"] for i in scan.scan(cfg)["items"]
                                    if i.get("blend") and os.path.normcase(os.path.abspath(i["blend"]["path"])) == target)
        elif cfg.get("engine_root") and _inside(path, cfg["engine_root"]):
            info["asset"] = "engine:" + os.path.relpath(path, cfg["engine_root"]).replace("\\", "/")
    _info_cache[path] = (now, info)
    return info


NOTES_FILE = "blender_notes.json"
NOTE_KINDS, NOTE_PRIORITIES = ("todo", "note"), ("high", "normal", "low")
MAX_NOTES, MAX_NOTE_TEXT = 500, 4000


def _clean_notes(notes):
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise ValueError(f"notes must be a list of at most {MAX_NOTES} notes")
    out = []
    for n in notes:
        if not isinstance(n, dict) or not isinstance(n.get("text"), str) or not n["text"].strip():
            raise ValueError("each note needs its text")
        kind, priority = n.get("kind", "note"), n.get("priority", "normal")
        if kind not in NOTE_KINDS or priority not in NOTE_PRIORITIES:
            raise ValueError(f"a note's kind is one of {NOTE_KINDS}, its priority one of {NOTE_PRIORITIES}")
        obj = n.get("object")
        out.append({"text": n["text"][:MAX_NOTE_TEXT], "kind": kind, "done": bool(n.get("done")), "priority": priority,
                    "object": obj if isinstance(obj, str) and obj else None})
    return out


def send_notes(file, notes):
    """Keeps the notes the add-on sent for one .blend (its last send replaces the one before; none left removes the
    file). The file must be inside a registered project. {project, asset, count}."""
    clean = _clean_notes(notes)
    info = file_info(file) if isinstance(file, str) and file else {"project": None}
    cfg = _project_cfg(file) if info["project"] else None
    if not cfg or not info.get("asset"):
        raise ValueError("this file is in no Artbench project: save it inside a project's art folder or game project")
    path = os.path.join(store.data_dir(cfg), NOTES_FILE)
    with store.locked(cfg):
        data = store._read_json(path, {})
        data = data if isinstance(data, dict) else {}
        if clean:
            data[info["asset"]] = {"asset": info["asset"], "name": os.path.basename(file), "file": file,
                                   "sent": time.time(), "notes": clean}
        else:
            data.pop(info["asset"], None)
        store._write_json(path, data)
    return {"project": cfg.get("id"), "asset": info["asset"], "count": len(clean)}


def notes(cfg):
    """[{asset, name, file, sent, notes}] the add-on sent for this project's files, the newest send first."""
    data = store._read_json(os.path.join(store.data_dir(cfg), NOTES_FILE), {})
    entries = [e for e in (data.values() if isinstance(data, dict) else []) if isinstance(e, dict) and isinstance(e.get("notes"), list)]
    return sorted(entries, key=lambda e: e.get("sent") or 0, reverse=True)


def status():
    """{open, file, blender, pid, seconds_since_report, project, asset, models}: open when the last report is fresh and
    not a close; asset and models as file_info()."""
    last = store._read_json(_path(), None)
    if not isinstance(last, dict) or not isinstance(last.get("seen"), (int, float)):
        return {"open": False, "file": None, "blender": None, "pid": None, "seconds_since_report": None, "project": None,
                "asset": None, "models": []}
    age = max(0.0, time.time() - last["seen"])
    info = file_info(last.get("file")) if last.get("file") else {"project": None, "asset": None, "models": []}
    return {"open": not last.get("closed") and age <= FRESH_SECONDS, "file": last.get("file"), "blender": last.get("blender"),
            "pid": last.get("pid"), "seconds_since_report": round(age, 1), **info}


# Run by Blender before its window opens: an empty scene (preferences and add-ons as they are), then the model.
IMPORT_EXPR = (
    "import bpy, sys\n"
    "p = sys.argv[sys.argv.index('--') + 1]\n"
    "bpy.ops.wm.read_homefile(use_empty=True)\n"
    "low = p.lower()\n"
    "if low.endswith('.fbx'): bpy.ops.import_scene.fbx(filepath=p)\n"
    "elif low.endswith('.obj'): bpy.ops.wm.obj_import(filepath=p)\n"
    "else: bpy.ops.import_scene.gltf(filepath=p)\n")


def open_file(cfg, path):
    """Opens path in Blender's window, detached from Artbench: a .blend as it is, FBX/OBJ/glTF imported into an empty
    scene. Unavailable when no Blender is found."""
    exe = blender_jobs.blender(cfg)
    if not exe:
        raise Unavailable("Blender was not found: set \"blender\" in the project config to Blender's program (blender.exe; on a Mac Blender.app/Contents/MacOS/Blender), or put Blender on PATH")
    cmd = [exe, path] if path.lower().endswith(".blend") else [exe, "--python-expr", IMPORT_EXPR, "--", path]
    flags = {"creationflags": 0x00000008 | 0x00000200} if sys.platform == "win32" else {"start_new_session": True}
    subprocess.Popen(cmd, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)
    return {"opened": path, "blender": exe}
