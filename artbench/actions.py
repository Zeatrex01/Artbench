"""Mutations on project files that the page may ask for: change a model's state (move it between state folders),
set a note or an engine link, reveal a path, open a file. Nothing is deleted; every change is one history line."""
import os
import shutil
import subprocess

from . import store, sync
from .errors import Conflict


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


def reveal(path):
    path = os.path.normpath(path)
    args = ["explorer", path] if os.path.isdir(path) else ["explorer", "/select,", path]
    subprocess.Popen(args)


def open_file(path):
    os.startfile(os.path.normpath(path))      # Blender for .blend, the default app otherwise


def _item_id(cfg, path):
    return os.path.relpath(path, cfg["art_root"]).replace("\\", "/")


def _carry_notes(cfg, old_id, new_id):
    data = store.notes(cfg)
    if old_id in data["items"]:
        data["items"][new_id] = data["items"].pop(old_id)
        store.save_notes(cfg, data)
