"""Asset package transfers: a model travels with its engine-ready textures. One plan lists every file of the package
with its own sync state, target and action; send and pull move only the files that need it, each under the bridge
rule (archive first, temp file + rename, one history line, one sync base). Files the team changed in the engine are
never overwritten by default: they are left out of the default selection and need an explicit force. Where a new
file goes in the engine follows the project's `engine_layout`: "per_model" (model and textures in one folder) or
"follow" (wherever this model's textures already are; Artbench never invents a folder)."""
import collections
import os
import re
import shutil
import time

from . import actions, asset_meta, catalog, engines, files, store, sync
from .errors import Conflict, OutsideRoot, Unavailable, WarningsNotAccepted  # noqa: F401

TEAM_CHANGED = ("engine_newer", "conflict")
ART_CHANGED = ("desktop_newer", "conflict")


# --- targets ------------------------------------------------------------------------------------------------------

def fingerprint(cfg, path):
    """Metadata snapshot of a model as background Blender sees it (cached by content), or None when Blender is
    unavailable or the file fails to import. A name of its own so tests can stub it."""
    return asset_meta.snapshot_sync(cfg, path)


def model_target(cfg, item):
    """Where the model's engine copy lives or should go; None when nothing decides it."""
    if item.get("engine_path"):
        return item["engine_path"]
    folder = (cfg.get("engine_targets") or {}).get(item["category"])
    if not folder or not cfg.get("engine_root"):
        return None
    if cfg.get("engine_layout") == "per_model":
        return os.path.normpath(os.path.join(cfg["engine_root"], folder, os.path.splitext(item["name"])[0], item["name"]))
    return os.path.normpath(os.path.join(cfg["engine_root"], folder, item["name"]))


def texture_target(cfg, item, name, model_engine_target):
    """Engine path for a texture that has no engine copy yet, or None when no rule decides it."""
    if cfg.get("engine_layout") == "per_model":
        return os.path.join(os.path.dirname(model_engine_target), name) if model_engine_target else None
    folders = collections.Counter(os.path.dirname(f["engine_path"]) for f in item.get("package", {}).get("files", [])
                                  if f["role"] == "texture" and f.get("engine_path"))
    if folders:
        best = max(folders.values())
        return os.path.join(sorted(d for d, n in folders.items() if n == best)[0], name)
    folder = (cfg.get("engine_texture_targets") or {}).get(item["category"])
    if folder and cfg.get("engine_root"):
        return os.path.normpath(os.path.join(cfg["engine_root"], folder, name))
    return None


# --- send ---------------------------------------------------------------------------------------------------------

def plan_send(cfg, item):
    """The package send plan. Top-level fields describe the model (as deploy.plan always did); `files` lists every
    package file, model first."""
    _engine_reachable(cfg)
    target = model_target(cfg, item)
    if not target:
        raise Unavailable(f"no engine target for {item['id']}: set engine_path on the item or engine_targets[{item['category']!r}] in the config")
    if not sync.inside(item["path"], cfg["art_root"]):
        raise OutsideRoot("source outside art root")
    if not cfg.get("engine_root") or not sync.inside(target, cfg["engine_root"]):
        raise OutsideRoot("target outside engine root")
    base = store.sync_base(cfg)
    model = _file_plan(cfg, item["id"], "model", item["path"], target, base, direction="send")
    warnings = asset_meta.warnings(fingerprint(cfg, target), fingerprint(cfg, item["path"])) if model["overwrites"] else []
    warnings += [f"{item['name']} names {uri}, which is not a file beside it: it will not reach the engine"
                 for uri in item.get("package", {}).get("unresolved", [])]
    plan_files = [model]
    for tex in item.get("package", {}).get("files", [])[1:]:
        if tex.get("beside"):                        # what a .gltf names is looked up beside it
            tex_target = os.path.join(os.path.dirname(target), tex["name"])
        else:
            tex_target = tex.get("engine_path") or texture_target(cfg, item, tex["name"], target)
        if tex_target and not sync.inside(tex_target, cfg["engine_root"]):
            tex_target = None
        plan_files.append(_file_plan(cfg, tex["id"], tex["role"], tex["path"], tex_target, base, direction="send",
                                     ambiguous=bool(tex.get("ambiguous"))))
    if item["state"] == "outbox":
        try:
            actions.move_plan(cfg, item, "ingame")       # refuse a blocked Outbox move before anything is written
        except FileExistsError as e:
            raise Conflict(str(e)) from None
    return {"source": item["path"], "target": target, "overwrites": model["overwrites"], "backup": model["backup"],
            "warnings": warnings, "sync": model["sync"], "basis": model["basis"],
            "requires_force": _requires_force(plan_files), "force_reason": model["force_reason"], "files": plan_files}


def send(cfg, item, files=None, accept_warnings=False, force=False, expect=None):
    """Sends the selected package files (default selection when `files` is None). Textures first, model last; stops
    at the first failure. Returns per-file outcomes; the Outbox move runs only when every selected file was sent.
    `expect` ({file id: target_sha} from the plan the caller confirmed) refuses the call when a target changed since
    the caller looked, so a force given for one state never applies to a newer one."""
    _check_selection(files)
    p = plan_send(cfg, item)
    selected = _select(p["files"], files, force)
    model = p["files"][0]
    if not selected:
        waiting = any(f["action"] == "send" for f in p["files"])
        if item["state"] == "outbox" and model["sync"] == "same" and not waiting:   # sent before, the move failed
            moved, move_error = _outbox_move(cfg, item)
        else:
            _nothing_selected(p["files"], "engine")
            moved = move_error = None
        return {"ok": True, "target": model["target"], "backup": None, "warnings": p["warnings"], "moved_to": moved,
                "forced": False, "results": _noop(p["files"]), "move_error": move_error}
    _check_expect(selected, expect)
    if model in selected and p["warnings"] and not accept_warnings:
        raise WarningsNotAccepted("fingerprint warnings: " + "; ".join(p["warnings"]))
    needs = [f for f in selected if f["force_reason"]]
    if needs and not force:
        raise sync.force_error(needs[0]["force_reason"], "engine")
    results = _transfer(cfg, "SEND", selected, p["files"], warnings=p["warnings"])
    ok = all(r["outcome"] in ("sent", "skipped") for r in results)
    moved = move_error = None
    if ok and item["state"] == "outbox" and model in selected:
        moved, move_error = _outbox_move(cfg, item)
    refresh_error = sync.refresh_after_transfer(cfg, agreed_path=model["target"] if model in selected and ok else None)
    model_result = next(r for r in results if r["id"] == model["id"])
    return {"ok": ok, "target": model["target"], "backup": model["backup"] if model_result["outcome"] == "sent" else None,
            "warnings": p["warnings"], "moved_to": moved, "forced": bool(needs) and force, "results": results,
            "refresh_error": refresh_error, "move_error": move_error}


def _outbox_move(cfg, item):
    """Moves a sent Outbox package into the game folders. The engine files are written already, so a failure is
    returned (the result's `move_error`), not raised; sending again retries the move."""
    try:
        return actions.set_state(cfg, item, "ingame"), None
    except (OSError, ValueError) as e:        # TimeoutError (busy) and FileExistsError are OSErrors
        return None, f"{type(e).__name__}: {e}"


# --- pull ---------------------------------------------------------------------------------------------------------

def plan_pull(cfg, item):
    """The package pull plan: files whose engine copy is newer are pulled; art-side changes are never overwritten by
    default (conflicts are unticked and need force)."""
    _engine_reachable(cfg)
    source = item.get("engine_path")
    if not source or not os.path.exists(source):
        raise Unavailable("no engine copy to pull")
    if not cfg.get("engine_root") or not sync.inside(source, cfg["engine_root"]):
        raise OutsideRoot("source outside engine root")
    if not sync.inside(item["path"], cfg["art_root"]):
        raise OutsideRoot("target outside art root")
    base = store.sync_base(cfg)
    model = _file_plan(cfg, item["id"], "model", item["path"], source, base, direction="pull")
    plan_files = [model]
    for tex in item.get("package", {}).get("files", [])[1:]:
        if tex.get("engine_path") and os.path.exists(tex["engine_path"]) and sync.inside(tex["engine_path"], cfg["engine_root"]):
            plan_files.append(_file_plan(cfg, tex["id"], tex["role"], tex["path"], tex["engine_path"], base,
                                         direction="pull", ambiguous=bool(tex.get("ambiguous"))))
    if item["name"].lower().endswith(".gltf"):       # the engine copy may name files the desktop does not have yet
        known = {f["name"] for f in item.get("package", {}).get("files", [])}
        refs = files.gltf_references(source, cfg["model_extensions"])
        for role, name in [("texture", n) for n in refs["images"]] + [("buffer", n) for n in refs["buffers"]]:
            if name not in known:
                art_path = os.path.join(os.path.dirname(item["path"]), name)
                file_id = os.path.relpath(art_path, cfg["art_root"]).replace("\\", "/")
                plan_files.append(_file_plan(cfg, file_id, role, art_path, os.path.join(os.path.dirname(source), name),
                                             base, direction="pull"))
    return {"source": source, "target": item["path"], "overwrites": True, "backup": model["backup"],
            "sync": model["sync"], "basis": model["basis"], "requires_force": _requires_force(plan_files),
            "force_reason": model["force_reason"], "files": plan_files}


def pull(cfg, item, files=None, force=False, expect=None):
    """Pulls the selected package files (default: every file the engine changed). `expect` as in send()."""
    _check_selection(files)
    p = plan_pull(cfg, item)
    selected = _select(p["files"], files, force)
    if not selected:
        _nothing_selected(p["files"], "art")
        return {"ok": True, "target": p["files"][0]["target"], "backup": None, "forced": False, "sync": "same",
                "results": _noop(p["files"])}
    _check_expect(selected, expect)
    needs = [f for f in selected if f["force_reason"]]
    if needs and not force:
        raise sync.force_error(needs[0]["force_reason"], "art")
    results = _transfer(cfg, "PULL", selected, p["files"])
    model = p["files"][0]
    model_result = next(r for r in results if r["id"] == model["id"])
    refresh_error = sync.refresh_after_transfer(cfg, agreed_path=model["target"] if model_result["outcome"] == "sent" else None)
    return {"ok": all(r["outcome"] in ("sent", "skipped") for r in results), "target": model["target"],
            "backup": model["backup"] if model_result["outcome"] == "sent" else None,
            "forced": bool(needs) and force, "sync": "same", "results": results, "refresh_error": refresh_error}


# --- bring in: an engine-only model into the art folder ----------------------------------------------------------

_FOLDER_NAME = re.compile(r"^[^\\/:*?\"<>|]+$")


def _guess_category(cfg, entry):
    """The first folder of the model's engine path that is a known category (any case), else None."""
    known = {c.lower(): c for c in cfg.get("categories", [])}
    rel = os.path.relpath(entry["engine_path"], cfg["engine_root"]).replace("\\", "/").split("/")[:-1]
    return next((known[p.lower()] for p in rel if p.lower() in known), None)


def _check_category(category):
    name = (category or "").strip()
    if not name or not _FOLDER_NAME.match(name) or name in (".", "..") or name.endswith((".", " ")):
        raise ValueError(f"category must be one folder name, got {category!r}")
    return name


def _engine_textures(cfg, source):
    """Absolute paths of the textures the engine model at `source` uses (catalog.textures_of), matched by file."""
    cat = catalog.build(cfg, engines.dump(cfg))
    root, prefix = engines.content_root(cfg), engines.of(cfg).prefix
    absolute = lambda p: os.path.normcase(os.path.normpath(os.path.join(root, *p[len(prefix):].split("/"))))
    by_path = {a["path"]: a for a in cat["assets"]}
    entry = next((a for a in cat["assets"] if absolute(a["path"]) == os.path.normcase(os.path.normpath(source))), None)
    return [os.path.join(root, *p[len(prefix):].split("/")) for p in catalog.textures_of(by_path, entry)] if entry else []


def plan_bring_in(cfg, entry, category=None):
    """Where bringing an engine-only model in would put it: FBX/<Category>/<Model>/<file>. Without `category` the
    guess from the engine path is used; when there is none, target and id are None and a category must be given.
    `textures` lists what can come along (bring_in with textures=True), each going beside the model."""
    source = entry["engine_path"]
    chosen = _check_category(category) if category else _guess_category(cfg, entry)
    target = item_id = None
    if chosen:
        stem = os.path.splitext(entry["name"])[0]
        target = os.path.join(cfg["state_dirs"]["ingame"], chosen, stem, entry["name"])
        item_id = os.path.relpath(target, cfg["art_root"]).replace("\\", "/")
    categories = sorted(set(cfg.get("categories", [])) | ({chosen} if chosen else set()), key=str.lower)
    textures = []
    for tex in _engine_textures(cfg, source):
        beside = os.path.join(os.path.dirname(target), os.path.basename(tex)) if target else None
        textures.append({"source": tex, "target": beside, "exists": bool(beside and os.path.exists(beside))})
    return {"source": source, "engine_path": engines.of(cfg).to_engine_path(cfg, source), "name": entry["name"],
            "category": chosen, "categories": categories, "target": target, "id": item_id,
            "exists": bool(target and os.path.exists(target)), "textures": textures}


def bring_in(cfg, entry, category, textures=False):
    """Copies the engine model to FBX/<Category>/<Model>/ (with textures=True also the textures the plan lists,
    beside it; without, they stay where the engine keeps them), records both sides as agreed, marks the item as
    brought in from the engine (`imported` in its notes, with its exact `engine_path`), and logs one BRING IN line.
    A file already at a target refuses the whole bring-in: nothing is overwritten."""
    _engine_reachable(cfg)
    p = plan_bring_in(cfg, entry, _check_category(category))
    source, target = p["source"], p["target"]
    if not os.path.isfile(source):
        raise Unavailable(f"the engine copy is gone: {source}")
    if not cfg.get("engine_root") or not sync.inside(source, cfg["engine_root"]):
        raise OutsideRoot("source outside engine root")
    if not sync.inside(target, cfg["art_root"]):
        raise OutsideRoot("target outside art root")
    extra = p["textures"] if textures else []
    with store.locked(cfg):
        for path in [target] + [t["target"] for t in extra]:
            if os.path.exists(path):
                raise Conflict(f"already in the art folder: {path}")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        sync.write_over(source, target)
        digest = files.sha(target)
        sync.record_base(cfg, p["id"], digest, files.sha(source))
        for t in extra:                                    # each texture as agreed by both sides, like the model
            sync.write_over(t["source"], t["target"])
            sync.record_base(cfg, os.path.relpath(t["target"], cfg["art_root"]).replace("\\", "/"),
                             files.sha(t["target"]), files.sha(t["source"]))
        data = store.notes(cfg)
        entry_notes = data["items"].setdefault(p["id"], {})
        entry_notes["engine_path"] = source
        entry_notes["imported"] = {"from": p["engine_path"], "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        store.save_notes(cfg, data)
        store.log(cfg, "BRING IN", source, target, *([f"+{len(extra)} textures"] if extra else []))
    refresh_error = sync.refresh_after_transfer(cfg, agreed_path=target)
    return {"ok": True, "id": p["id"], "path": target, "source": source, "engine_path": p["engine_path"],
            "textures": len(extra), "refresh_error": refresh_error}


# --- shared -------------------------------------------------------------------------------------------------------

def _engine_reachable(cfg):
    """Refuses every transfer while the configured engine folder cannot be read: a send would otherwise create
    folders at a stale path (a moved clone, an unplugged drive)."""
    if engines.unreachable(cfg):
        raise Unavailable(f"engine folder unreachable: {cfg['engine_root']}")


def _file_plan(cfg, file_id, role, art_path, engine_path, base, direction, ambiguous=False):
    """One file of a package plan. For send the engine side is overwritten, for pull the art side. The other side's
    newer work (by the sync base, or by date when there is none) is never in the default selection, nor is a texture
    whose engine copy was picked among several by name."""
    entry = base.get(file_id)
    exists = bool(engine_path) and os.path.exists(engine_path)
    if direction == "pull" and exists and not os.path.exists(art_path):    # named by the engine .gltf, new here
        return {"id": file_id, "role": role, "source": engine_path, "target": art_path, "action": "pull",
                "sync": "not_on_desktop", "basis": None, "force_reason": None, "overwrites": False, "backup": None,
                "team_changed": False, "art_changed": False, "ambiguous": False, "default": True,
                "target_sha": None, "source_sha": files.sha(engine_path)}
    state = basis = reason = None
    art_hash = engine_hash = None
    if exists:
        art_hash, engine_hash = files.sha(art_path), files.sha(engine_path)
        state, basis = sync.status(entry, art_hash, engine_hash, os.stat(art_path).st_mtime, os.stat(engine_path).st_mtime)
        if state != "same":
            overwritten, base_hash = (engine_hash, (entry or {}).get("engine")) if direction == "send" else (art_hash, (entry or {}).get("art"))
            reason = sync.force_reason(basis, overwritten, base_hash)
    elif engine_path:
        state = "missing_in_engine"
    against = TEAM_CHANGED if direction == "send" else ART_CHANGED
    protected = state in against                                  # the other side's work since the last sync
    if direction == "send":
        source, target = art_path, engine_path
        action = "no_target" if not engine_path else "skip" if state == "same" else "send"
        backup = sync.archive_path(cfg, "engine", cfg["engine_root"], engine_path) if exists else None
    else:
        source, target = engine_path, art_path
        action = "pull" if state in ("engine_newer", "conflict") else "skip"
        backup = sync.archive_path(cfg, "art", cfg["art_root"], art_path)
    return {"id": file_id, "role": role, "source": source, "target": target, "action": action, "sync": state,
            "basis": basis, "force_reason": reason, "overwrites": exists if direction == "send" else True,
            "backup": backup, "team_changed": protected if direction == "send" else False,
            "art_changed": protected if direction == "pull" else False, "ambiguous": ambiguous,
            "default": action in ("send", "pull") and not protected and not ambiguous,
            "target_sha": engine_hash if direction == "send" else art_hash,       # re-checked under the lock
            "source_sha": (files.sha(source) if source and os.path.exists(source) else None)}


def _check_selection(files):
    """An empty list would silently move nothing; leaving `files` out is how the default selection is asked for."""
    if files is not None and not files:
        raise ValueError("files is empty: leave it out for the default selection, or name the files to move")


def _requires_force(plan_files):
    """True when the call without `files` needs force: a default file, or the model, would overwrite changed work."""
    return any(f["force_reason"] and (f["default"] or f["role"] == "model")
               for f in plan_files if f["action"] in ("send", "pull"))


def _select(plan_files, ids, force=False):
    """Files to move. Without `ids`: the default selection, plus the model when the caller forces (the single-model
    force of the bridge core). Protected textures move only when named in `ids`."""
    movable = [f for f in plan_files if f["action"] in ("send", "pull")]
    if ids is None:
        return [f for f in movable if f["default"] or (force and f["role"] == "model")]
    wanted = set(ids)
    unknown = wanted - {f["id"] for f in plan_files}
    if unknown:
        raise ValueError(f"not in this package: {', '.join(sorted(unknown))}")
    return [f for f in movable if f["id"] in wanted]


def _check_expect(selected, expect):
    """Refuses before anything is written when a selected file differs from what the caller saw. `expect` maps a
    file id to its plan's `target_sha`, or to {"target": target_sha, "source": source_sha} to pin the source too (a
    re-export while the confirmation was open would otherwise go out under warnings accepted for the old file)."""
    for f in selected:
        seen = (expect or {}).get(f["id"], ...)
        if seen is ...:
            continue
        target, source = (seen.get("target"), seen.get("source", f["source_sha"])) if isinstance(seen, dict) else (seen, f["source_sha"])
        if target != f["target_sha"] or source != f["source_sha"]:
            raise Conflict(f"{os.path.basename(f['target'])} changed since the plan was made; look again before writing")


def _nothing_selected(plan_files, side):
    """Nothing to move: an error only when protected files are waiting for an explicit force."""
    protected = [f for f in plan_files if f["action"] in ("send", "pull") and not f["default"]]
    if protected:
        raise sync.force_error(protected[0]["force_reason"] or "changed", side)


def _noop(plan_files):
    return [{"id": f["id"], "role": f["role"], "outcome": "skipped", "target": f["target"], "backup": None} for f in plan_files]


def _transfer(cfg, verb, selected, all_files, warnings=()):
    """Writes the selected files, textures first and the model last, under the project lock; stops at the first
    failure. Every written file is archived first, logged and recorded as agreed. A target that changed or appeared
    after the plan was made (a git pull, the editor, another tool) is not written: the plan's force decision no
    longer holds for it."""
    order = sorted(selected, key=lambda f: f["role"] == "model")
    outcome = {f["id"]: "skipped" for f in all_files if f not in selected}
    backups = {}
    error = None
    with store.locked(cfg):
        failed = False
        for f in order:
            if failed:
                outcome[f["id"]] = "not_run"
                continue
            try:
                now = files.sha(f["target"]) if os.path.exists(f["target"]) else None
                if now != f.get("target_sha"):
                    outcome[f["id"]], failed = "failed", True
                    error = Conflict(f"{os.path.basename(f['target'])} changed since the plan was made; look again before writing")
                    continue
                backup = f["backup"] if f["overwrites"] else None
                if backup:
                    os.makedirs(os.path.dirname(backup), exist_ok=True)
                    shutil.copy2(f["target"], backup)
                os.makedirs(os.path.dirname(f["target"]), exist_ok=True)
                sync.write_over(f["source"], f["target"])
                content = files.sha(f["target"])
                if verb == "SEND":
                    fields = [f["id"], f["target"], backup or "", "; ".join(warnings) if f["role"] == "model" else ""]
                else:
                    fields = [f["id"], f["source"], backup or ""]
                store.log(cfg, verb, *fields, "FORCED" if f["force_reason"] else "")
                sync.record_base(cfg, f["id"], content, content)
                outcome[f["id"]], backups[f["id"]] = "sent", backup
            except OSError as e:
                outcome[f["id"]], failed, error = "failed", True, e
    if failed and not any(v == "sent" for v in outcome.values()):
        raise error                           # nothing was written: the caller gets the error itself
    return [{"id": f["id"], "role": f["role"], "outcome": outcome[f["id"]], "target": f["target"],
             "backup": backups.get(f["id"]), "error": str(error) if outcome[f["id"]] == "failed" else None}
            for f in all_files]

