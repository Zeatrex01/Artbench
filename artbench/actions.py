"""Mutations on project files that the page may ask for: change a model's state (move it between state folders),
set a note or an engine link, archive an engine asset nothing uses and restore it, reveal a path, open a file. Nothing
is deleted; every change is one history line."""
import os
import shutil
import subprocess
import sys
import time

from . import config, engines, store, sync
from .errors import Conflict

ARCHIVED_FILE = "archived.json"


def set_state(cfg, item, state):
    """Moves the model and its package (textures and texture sources that belong to it) into the state folder,
    keeping the category sub-folder. A model leaving the Outbox for the game gets its own folder,
    FBX/<Category>/<ModelStem>/. Notes and sync bases follow every moved file. Returns the model's new path."""
    with store.locked(cfg):
        moves = move_plan(cfg, item, state)
        os.makedirs(os.path.dirname(moves[-1][1]), exist_ok=True)
        for old, new in moves:                # each file is logged and carried as soon as it moved
            shutil.move(old, new)
            store.log(cfg, "MOVE", f"{item['state']} -> {state}", old, new)
            _carry_notes(cfg, _item_id(cfg, old), _item_id(cfg, new))
            sync.carry_base(cfg, _item_id(cfg, old), _item_id(cfg, new))
    return moves[-1][1]


def move_plan(cfg, item, state):
    """[(old path, new path)] for a state move: the package members first, the model last. Raises FileExistsError
    when any destination is taken, before anything moves."""
    if state not in cfg["state_dirs"]:
        raise ValueError(f"unknown state {state}")
    dst_dir = os.path.join(cfg["state_dirs"][state], item["category"])
    if item.get("state") == "outbox" and state == "ingame":
        dst_dir = os.path.join(dst_dir, os.path.splitext(item["name"])[0])
    src_dir = os.path.dirname(item["path"])
    shared = next((f for f in (item.get("package") or {}).get("files", [])[1:] if f.get("shared")), None)
    if shared:
        raise Conflict(f"{shared['name']} is also used by {', '.join(shared['shared'])}: moving it would break that "
                       f"model; give each model its own copy, or move them together by hand")
    moves = [(os.path.join(src_dir, n), os.path.join(dst_dir, n)) for n in _members(cfg, item)
             if os.path.exists(os.path.join(src_dir, n))]
    moves.append((item["path"], os.path.join(dst_dir, item["name"])))
    taken = [new for _, new in moves if os.path.exists(new)]
    if taken:
        raise FileExistsError(f"already there: {taken[0]}")
    return moves


def _members(cfg, item):
    """File names (beside the model) that travel with it: package textures and buffers, and texture sources. Items built before
    packages existed fall back to the old rule: every texture when the model is alone in its folder."""
    pkg = item.get("package")
    if pkg:
        return [f["name"] for f in pkg["files"][1:]] + list(pkg.get("sources", []))
    folder = os.path.dirname(item["path"])
    others = [f for f in os.listdir(folder) if f.lower().endswith(tuple(cfg["model_extensions"])) and f != item["name"]]
    return [] if others else list(item.get("textures", []))


META_FIELDS = ("note", "source", "engine_path", "blend")


def set_meta(cfg, item_id, **fields):
    """Sets or clears note / source / engine_path / blend on an item id (desktop item, texture or engine:<path>).
    engine_path may only name a file inside the engine root with the item's own file name (the copy the team moved,
    or one of several same-name candidates): pointing an item at another file would let a send overwrite it."""
    if fields.get("engine_path"):
        fields["engine_path"] = _engine_path_for(cfg, item_id, fields["engine_path"])
    with store.locked(cfg):
        data = store.notes(cfg)
        entry = data["items"].setdefault(item_id, {})
        for key, value in fields.items():
            if value in (None, ""):
                entry.pop(key, None)
            else:
                entry[key] = value
        if not entry:
            data["items"].pop(item_id, None)
        store.save_notes(cfg, data)
        store.log(cfg, "META", item_id, fields)


def _engine_path_for(cfg, item_id, value):
    """An absolute path, or one in the engine's own form ("Assets/..." for Unity) as the asset operation takes it."""
    from . import engines                    # lazy: keeps this module's imports to store and sync
    adapter = engines.of(cfg)
    if os.path.isabs(value):
        path = os.path.normpath(value)
    elif adapter.is_engine_path(value):
        path = adapter.from_engine_path(cfg, value)
    else:
        raise ValueError(f"engine_path {value!r} must be absolute or start with {adapter.prefix}")
    if not sync.engine_note_ok(cfg, os.path.basename(item_id), path):
        raise ValueError(f"engine_path {value!r} must be an existing file inside the engine root named {os.path.basename(item_id)!r}")
    return path


def opener(action, path, platform=None):
    """The command that reveals (`reveal`: the folder, with the file selected where the system can) or opens
    (`open`: with its default app, Blender for a .blend) a path: Explorer on Windows, Finder on a Mac, xdg-open on
    Linux. None for opening on Windows, which goes through os.startfile."""
    platform = sys.platform if platform is None else platform
    folder = os.path.isdir(path)
    if platform == "win32":
        if action == "open":
            return None
        return ["explorer", path] if folder else ["explorer", "/select,", path]
    if platform == "darwin":
        return ["open", path] if action == "open" or folder else ["open", "-R", path]
    return ["xdg-open", path if action == "open" or folder else os.path.dirname(path)]


def reveal(path):
    subprocess.Popen(opener("reveal", os.path.normpath(path)))


def open_file(path):
    path = os.path.normpath(path)
    args = opener("open", path)
    if args is None:
        os.startfile(path)                    # Blender for .blend, the default app otherwise
    else:
        subprocess.Popen(args)


def _item_id(cfg, path):
    return os.path.relpath(path, cfg["art_root"]).replace("\\", "/")


def _carry_notes(cfg, old_id, new_id):
    data = store.notes(cfg)
    if old_id in data["items"]:
        data["items"][new_id] = data["items"].pop(old_id)
        store.save_notes(cfg, data)


# --- archive: engine assets the game no longer needs, out of the game project and back ---------------------------

def _archive_root(cfg):
    """The art folder's archive; a game project on its own archives into its data folder (never into the game)."""
    if config.is_project_mode(cfg):
        return os.path.join(store.data_dir(cfg), "_Archive")
    return cfg["state_dirs"]["archive"]


def _archived_path(cfg):
    return os.path.join(store.data_dir(cfg), ARCHIVED_FILE)


def archived(cfg):
    """[{id, path, time, files: {engine path: archived file}}], the latest first."""
    data = store._read_json(_archived_path(cfg), [])
    return data if isinstance(data, list) else []


def archive_plan(cfg, assets, ids):
    """{dest, archive: [{id, path, files, warn?}], blocked: [{id, reason: used | in_build | unknown, ...}]} for the
    catalog entries `assets`. Only what nothing uses can go; one loaded by name (Resources) goes with a warning."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        raise ValueError("no asset ids given")
    adapter, by_id = engines.of(cfg), {a["id"]: a for a in assets}
    out = {"dest": os.path.join(_archive_root(cfg), time.strftime("%Y-%m-%d")), "archive": [], "blocked": []}
    for asset_id in ids:
        a = by_id.get(asset_id)
        if a is None or not asset_id.startswith("engine:"):
            out["blocked"].append({"id": asset_id, "reason": "unknown"})
            continue
        users = [u["path"] for u in a.get("used_by") or []]
        if users or a.get("used_by_count"):
            out["blocked"].append({"id": asset_id, "path": a["path"], "reason": "used", "used_by": users[:5],
                                   "used_by_count": len(users) or a.get("used_by_count")})
            continue
        if a.get("in_build"):
            out["blocked"].append({"id": asset_id, "path": a["path"], "reason": "in_build"})
            continue
        path = adapter.from_engine_path(cfg, a["path"])
        files = [a["path"]] + [a["path"] + s[len(path):] for s in adapter.sidecars(path) if os.path.exists(s)]
        row = {"id": asset_id, "path": a["path"], "files": files}
        if a.get("usage") == "by_name":
            row["warn"] = "by_name"
        out["archive"].append(row)
    return out


def archive(cfg, assets, ids):
    """Moves every archivable asset with its sidecars (.meta) into the archive, under the same path; a second archive
    on one day gets a time suffix. One ARCHIVE line each. {dest, archived: n, blocked}."""
    plan = archive_plan(cfg, assets, ids)
    adapter, root = engines.of(cfg), engines.content_root(cfg)
    where = {"state_dirs": {"archive": _archive_root(cfg)}}           # sync.archive_path's dated, never-overwriting name
    with store.locked(cfg):
        records = archived(cfg)
        for row in plan["archive"]:
            moved = {}
            for engine_path in row["files"]:
                src = adapter.from_engine_path(cfg, engine_path)
                if not os.path.exists(src):
                    continue
                dest = sync.archive_path(where, "engine", root, src)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(src, dest)
                moved[engine_path] = dest
            if moved:
                records.insert(0, {"id": row["id"], "path": row["path"], "time": time.time(), "files": moved})
                store.log(cfg, "ARCHIVE", row["id"], next(iter(moved.values())))
        store._write_json(_archived_path(cfg), records)
    adapter.mark_dump_stale(cfg, time.time())
    return {"dest": plan["dest"], "archived": len(plan["archive"]), "blocked": plan["blocked"]}


def restore(cfg, ids):
    """Moves archived assets back to where they were, sidecars too (the same GUID, so references return). One whose
    place is taken again stays in the archive. {restored: [ids], skipped: [{id, reason: exists | unknown}]}."""
    adapter, wanted, out = engines.of(cfg), set(ids or []), {"restored": [], "skipped": []}
    with store.locked(cfg):
        records, keep = archived(cfg), []
        for rec in records:
            if rec["id"] not in wanted or rec["id"] in out["restored"]:
                keep.append(rec)
                continue
            targets = {p: adapter.from_engine_path(cfg, p) for p in rec["files"]}
            if any(os.path.exists(t) for t in targets.values()):
                out["skipped"].append({"id": rec["id"], "reason": "exists"})
                keep.append(rec)
                continue
            for engine_path, kept in rec["files"].items():
                os.makedirs(os.path.dirname(targets[engine_path]), exist_ok=True)
                shutil.move(kept, targets[engine_path])
            out["restored"].append(rec["id"])
            store.log(cfg, "RESTORE", rec["id"], rec["path"])
        store._write_json(_archived_path(cfg), keep)
    found = {r["id"] for r in records}
    out["skipped"] += [{"id": i, "reason": "unknown"} for i in sorted(wanted - found)]
    if out["restored"]:
        adapter.mark_dump_stale(cfg, time.time())
    return out
