"""Inventory state of one project: the models under the art root's state folders, their textures and Blender
sources, how each compares with its engine copy and where the engine uses it. Pure read: the only thing written is
the tool's own hash cache. Schemas are listed in ARCHITECTURE.md."""
import os
import time

from . import asset_meta, catalog, config, engines, files, layout, store, sync

# --- engine side ------------------------------------------------------------------------------------------------

def engine_models(cfg, dump):
    """Model files under the engine root, by lower-case file name -> [absolute path]."""
    return engine_files(cfg, dump, "model", tuple(cfg["model_extensions"]))


def engine_files(cfg, dump, kind, exts):
    """Files of one kind under the engine root, by lower-case file name -> [absolute path]. Found by name anywhere,
    so files the team moved are followed on the next scan."""
    root = cfg.get("engine_root")
    index = {}
    if not root or not os.path.isdir(root):
        return index
    seen = set()
    if dump:
        prefix = os.path.normpath(root).lower()
        for asset in dump["assets"].values():
            if asset["kind"] != kind:
                continue
            p = os.path.normpath(os.path.join(dump["assets_root"], asset["path"]))
            if p.lower().startswith(prefix):
                index.setdefault(os.path.basename(p).lower(), []).append(p)
                seen.add(os.path.normcase(p))
    # Files the dump does not know yet (no .meta until Unity imports them, e.g. just sent) still count.
    for p in files.walk(root, cfg["engine_ignore"]):
        if p.lower().endswith(exts) and os.path.normcase(os.path.normpath(p)) not in seen:
            index.setdefault(os.path.basename(p).lower(), []).append(os.path.normpath(p))
    return index


class _Usage:
    """usage(path) -> ("used" | "unused" | None, [referrers]) from the engine dump."""

    def __init__(self, dump, adapter):
        self._used_by = adapter.lookup(dump)[2] if dump else (lambda p: None)

    def __call__(self, path):
        refs = self._used_by(path)
        if refs is None:
            return None, []
        return ("used" if refs else "unused"), refs


# --- scan ---------------------------------------------------------------------------------------------------------

def scan(cfg):
    """The full inventory state of a project (see ARCHITECTURE.md, Schemas)."""
    if config.is_project_mode(cfg):
        return _project_scan(cfg)
    dump = engines.dump(cfg)
    engine = engine_models(cfg, dump)
    usage = _Usage(dump, engines.of(cfg))
    notes = store.notes(cfg)["items"]
    base = store.sync_base(cfg)

    textures = engine_files(cfg, dump, "texture", tuple(cfg["texture_extensions"]))
    blends = _blends(cfg)
    unreachable = engines.unreachable(cfg)
    items, seen_engine, agreed = _desktop_items(cfg, engine, usage, notes, base, compare=not unreachable)
    for item in items:
        _package(cfg, item, notes, textures, base, agreed, compare=not unreachable)
        item["blend"] = _blend_of(cfg, item, notes, blends)
    _record_agreed(cfg, base, agreed)
    state = {
        "project": cfg["id"], "name": cfg.get("name", cfg["id"]),
        "art_root": cfg["art_root"], "engine_root": cfg.get("engine_root"),
        "scanned": time.time(), "engine_scanned": dump["scanned"] if dump else None,
        "engine_unreachable": unreachable,
        "items": items,
        "engine_only": _engine_only(cfg, engine, seen_engine, usage, notes),
        "placeholders": _placeholders(cfg, dump, usage, notes),
        "blends": blends,
        "unsorted": _unsorted(cfg),
        "layout_issues": layout.check(cfg, dump),
        "layout": layout.status(cfg, dump),
        "states": list(cfg["states"].keys()),
        "categories": sorted({i["category"] for i in items} | set(cfg.get("categories", []))),
        "mode": "art",
    }
    files.save_cache()
    return state


def _project_scan(cfg):
    """Project mode: the engine project's catalog, placeholders and layout issues; no art folder, so no desktop items.
    The art-mode keys stay (empty) so every reader of the state works on both."""
    dump = engines.dump(cfg)
    usage = _Usage(dump, engines.of(cfg))
    notes = store.notes(cfg)["items"]
    cat = catalog.build(cfg, dump)
    if dump:                                             # model statistics: cached, or measured in the background
        prefix = engines.of(cfg).prefix
        asset_meta.attach_stats(cfg, cat["assets"], lambda e: os.path.normpath(os.path.join(dump["assets_root"], e["path"][len(prefix):])))
    return {
        "project": cfg["id"], "name": cfg.get("name", cfg["id"]), "mode": "project",
        "art_root": None, "engine_root": cfg.get("engine_root"),
        "scanned": time.time(), "engine_scanned": dump["scanned"] if dump else None,
        "engine_unreachable": engines.unreachable(cfg),
        "catalog": cat,
        "hidden_folders": cfg.get("engine_ignore_dump", engines.of(cfg).dump_ignore(project_mode=True)),
        "placeholders": _placeholders(cfg, dump, usage, notes),
        "layout_issues": layout.check(cfg, dump),
        "layout": layout.status(cfg, dump),
        "items": [], "engine_only": [], "blends": [], "unsorted": [], "states": [], "categories": [],
    }


def _record_agreed(cfg, base, agreed):
    """Items seen identical on both sides become the base. Opportunistic: skipped when another process holds the
    lock, so the page's poll never fails on it."""
    new = {k: v for k, v in agreed.items() if (base.get(k) or {}).get("art") != v or (base.get(k) or {}).get("engine") != v}
    if not new:
        return
    try:
        with store.locked(cfg, timeout=0):
            current = store.sync_base(cfg)
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            for k, v in new.items():
                current[k] = {"art": v, "engine": v, "time": stamp}
            store.save_sync_base(cfg, current)
    except (TimeoutError, OSError):
        pass


def _desktop_items(cfg, engine, usage, notes, base, compare=True):
    """Models under the state folders. Returns (items, set of engine paths matched to a desktop model). Without
    `compare` (engine folder unreachable) no engine copy is looked for and sync stays unknown."""
    art = cfg["art_root"]
    exts = tuple(cfg["model_extensions"])
    tex_exts = tuple(cfg["texture_extensions"])
    state_of = _state_resolver(cfg)
    items, seen_engine, agreed = [], set(), {}
    for root in [d for d in cfg["state_dirs"].values() if os.path.isdir(d)]:
        for p in files.walk(root, cfg["ignore"]):
            if not p.lower().endswith(exts):
                continue
            state, state_dir = state_of(p)
            if state_dir != root:
                continue                      # belongs to a more specific state folder nested in this one
            rel = _rel(p, art)
            parts = _rel(p, state_dir).split("/")
            folder = os.path.dirname(p)
            st = os.stat(p)
            meta = notes.get(rel, {})
            item = {
                "id": rel, "name": os.path.basename(p), "state": state,
                "category": _category(parts, cfg, state),
                "folder": folder, "path": p, "size": st.st_size, "mtime": st.st_mtime,
                "textures": sorted(f for f in os.listdir(folder) if f.lower().endswith(tex_exts)),
                "note": meta.get("note", ""), "source": meta.get("source", ""),
                "imported": _imported(meta),
                "engine_path": None, "sync": None, "basis": None, "usage": None, "used_by": [],
                "engine_mtime": None, "engine_size": None, "synced_at": None,
            }
            if compare and state in ("ingame", "outbox"):
                _match_engine(cfg, item, meta, engine, usage, seen_engine, base, agreed)
            items.append(item)
    return items, seen_engine, agreed


SEPARATORS = ("_", "-", ".", " ")
STATE_RANK = {"conflict": 0, "desktop_newer": 1, "engine_newer": 2, "missing_in_engine": 3, "same": 4}


def package_members(folder, model_name, models_in_folder, exts, listing=None):
    """Files in `folder` with `exts` that belong to the model: the name starts with the model's stem plus a
    separator (case-insensitive) and no longer stem in the folder claims it; when the model is alone in the folder,
    every such file is its own. `models_in_folder` is in preference order: when two models share a stem
    (Crate.fbx, Crate.glb) the first one owns the files, so a texture belongs to one package only."""
    files = sorted(f for f in (os.listdir(folder) if listing is None else listing) if f.lower().endswith(exts))
    if len(models_in_folder) <= 1:
        return files
    first_of = {}
    for m in models_in_folder:
        first_of.setdefault(os.path.splitext(m)[0].lower(), m)
    if first_of.get(os.path.splitext(model_name)[0].lower()) != model_name:
        return []
    stems = sorted({os.path.splitext(m)[0].lower() for m in models_in_folder}, key=len, reverse=True)
    own = os.path.splitext(model_name)[0].lower()
    out = []
    for f in files:
        low = f.lower()
        owner = next((s for s in stems if low.startswith(s) and len(low) > len(s) and low[len(s)] in SEPARATORS), None)
        if owner == own:
            out.append(f)
    return out


def _claims(cfg, folder, models, pkg_exts, listing):
    """{file name: [model names]}: which models in a folder claim each file, by name (package textures) or because
    their .gltf names it. `listing` is the folder's listing, read once."""
    claims = {}
    for m in models:
        names = package_members(folder, m, models, pkg_exts, listing) if pkg_exts else []
        if m.lower().endswith(".gltf"):
            refs = files.gltf_references(os.path.join(folder, m), cfg["model_extensions"])
            names = names + refs["images"] + refs["buffers"]
        for n in names:
            if m not in claims.setdefault(n, []):
                claims[n].append(m)
    return claims


def _package(cfg, item, notes, textures, base, agreed, compare=True):
    """item["package"]: the model plus the files that travel with it, each with its own sync state: the engine-ready
    textures, and for a .gltf the buffers and images it names beside itself (they go beside the model's engine copy,
    where its relative URIs look); other texture files that belong to it (.psd, .exr, ...) are listed as sources.
    A file another model in the folder also claims carries `shared` (those models' ids): a state move refuses it,
    since moving it would break the other package. URIs that cannot travel are listed as `unresolved`."""
    folder = item["folder"]
    order = [e.lower() for e in cfg["model_extensions"]]

    def preference(name):                    # model_extensions order first: Crate.fbx before Crate.glb
        ext = os.path.splitext(name)[1].lower()
        return (order.index(ext) if ext in order else len(order), name.lower())
    listing = os.listdir(folder)
    models = sorted((f for f in listing if f.lower().endswith(tuple(order))), key=preference)
    pkg_exts = tuple(e.lower() for e in cfg.get("package_extensions") or [])
    src_exts = tuple(e.lower() for e in cfg["texture_extensions"] if e.lower() not in pkg_exts)
    members = [{"id": item["id"], "role": "model", "name": item["name"], "path": item["path"],
                "engine_path": item["engine_path"], "sync": item["sync"], "basis": item["basis"]}]
    compare = compare and item["state"] in ("ingame", "outbox")
    refs = files.gltf_references(item["path"], cfg["model_extensions"]) if item["name"].lower().endswith(".gltf") \
        else {"buffers": [], "images": [], "unresolved": []}
    named = package_members(folder, item["name"], models, pkg_exts, listing) if pkg_exts else []
    claims = _claims(cfg, folder, models, pkg_exts, listing) if len(models) > 1 else {}
    beside_names = set(refs["images"]) | set(refs["buffers"])
    entries = [("texture", n) for n in named if n not in beside_names]
    entries += [("texture", n) for n in refs["images"]] + [("buffer", n) for n in refs["buffers"]]
    for role, name in entries:
        path = os.path.join(folder, name)
        entry = {"id": _rel(path, cfg["art_root"]), "role": role, "name": name, "path": path,
                 "engine_path": None, "sync": None, "basis": None}
        if name in beside_names:
            entry["beside"] = True
        others = [_rel(os.path.join(folder, m), cfg["art_root"]) for m in claims.get(name, []) if m != item["name"]]
        if others:
            entry["shared"] = sorted(others)
        if compare and not entry.get("beside"):
            _match_texture(cfg, entry, notes.get(entry["id"], {}), textures, base, agreed, item)
        elif compare:
            beside = os.path.join(os.path.dirname(item["engine_path"]), name) if item.get("engine_path") else None
            _compare_engine_copy(entry, beside, base, agreed)
        members.append(entry)
    states = [f["sync"] for f in members if f["sync"] in STATE_RANK]
    listed = {f["name"] for f in members}
    item["package"] = {"files": members, "state": min(states, key=STATE_RANK.get) if states else None,
                       "sources": [n for n in package_members(folder, item["name"], models, src_exts, listing) if n not in listed]
                       if src_exts else [], "unresolved": refs["unresolved"]}


def _match_texture(cfg, tex, meta, textures, base, agreed, model):
    """Finds the texture's engine copy by name. A copy beside the model's engine copy wins; a name that does not carry
    the model's stem (Albedo.png) is matched only there, so it never binds to another model's file."""
    candidates = textures.get(tex["name"].lower(), [])
    pinned = meta.get("engine_path") if sync.engine_note_ok(cfg, tex["name"], meta.get("engine_path")) else None
    if not pinned:
        model_dir = os.path.normcase(os.path.dirname(model["engine_path"])) if model.get("engine_path") else None
        near = [c for c in candidates if model_dir and os.path.normcase(os.path.dirname(c)) == model_dir]
        stem, low = os.path.splitext(model["name"])[0].lower(), tex["name"].lower()
        named = low.startswith(stem) and len(low) > len(stem) and low[len(stem)] in SEPARATORS
        candidates = near or (candidates if named else [])
    target = pinned or (candidates[0] if candidates else None)
    if not _compare_engine_copy(tex, target, base, agreed):
        return
    if len(candidates) > 1 and not pinned:
        tex["ambiguous"] = candidates


def _compare_engine_copy(entry, target, base, agreed):
    """Fills a package file's engine_path / sync / basis from its engine copy at `target`; False when there is none."""
    if not target or not os.path.exists(target):
        entry["sync"] = "missing_in_engine"
        return False
    entry["engine_path"] = target
    art_hash, engine_hash = files.sha(entry["path"]), files.sha(target)
    entry["sync"], entry["basis"] = sync.status(base.get(entry["id"]), art_hash, engine_hash,
                                                os.stat(entry["path"]).st_mtime, os.stat(target).st_mtime)
    if entry["sync"] == "same":
        agreed[entry["id"]] = art_hash
    return True


def _blend_of(cfg, item, notes, blends):
    """The .blend the model comes from: an explicit binding (note field "blend") or the same-stem file under Blend/."""
    bound = (notes.get(item["id"]) or {}).get("blend")
    if bound:
        path = os.path.normpath(os.path.join(cfg["art_root"], bound))
        return {"id": bound, "path": path, "bound": True}
    stem = os.path.splitext(item["name"])[0].lower()
    hit = next((b for b in blends if os.path.splitext(b["name"])[0].lower() == stem), None)
    return {"id": hit["id"], "path": hit["path"], "bound": False} if hit else None


def _match_engine(cfg, item, meta, engine, usage, seen_engine, base, agreed):
    """Fills engine_path / sync / usage of a desktop item from the engine copy with the same file name, or the one
    its engine_path note pins (honoured only when it passes sync.engine_note_ok)."""
    candidates = engine.get(item["name"].lower(), [])
    pinned = meta.get("engine_path") if sync.engine_note_ok(cfg, item["name"], meta.get("engine_path")) else None
    target = pinned or (candidates[0] if candidates else None)
    if not target or not os.path.exists(target):
        item["sync"] = "missing_in_engine"
        return
    item["engine_path"] = target
    seen_engine.add(os.path.normcase(target))
    item["usage"], item["used_by"] = usage(target)
    st = os.stat(target)
    item["engine_mtime"], item["engine_size"] = st.st_mtime, st.st_size
    entry = base.get(item["id"])
    item["synced_at"] = (entry or {}).get("time")
    art_hash, engine_hash = files.sha(item["path"]), files.sha(target)
    item["sync"], item["basis"] = sync.status(entry, art_hash, engine_hash, item["mtime"], st.st_mtime)
    if item["sync"] == "same":
        agreed[item["id"]] = art_hash
    if len(candidates) > 1 and not pinned:
        item["ambiguous"] = candidates


def _imported(meta):
    """{from, time} when the model was brought in from the engine (package.bring_in), else None; a hand-edited
    entry of another shape is ignored."""
    mark = meta.get("imported")
    if isinstance(mark, dict) and isinstance(mark.get("from"), str):
        return {"from": mark["from"], "time": str(mark.get("time") or "")}
    return None


def _engine_only(cfg, engine, seen_engine, usage, notes):
    """Engine models that have no desktop copy."""
    out = []
    for paths in engine.values():
        for p in paths:
            if os.path.normcase(p) in seen_engine:
                continue
            rel = _rel(p, cfg["engine_root"])
            used, refs = usage(p)
            out.append({"id": "engine:" + rel, "name": os.path.basename(p), "engine_path": p,
                        "category": rel.split("/")[0], "state": "engine_only", "sync": "not_on_desktop",
                        "usage": used, "used_by": refs, "note": notes.get("engine:" + rel, {}).get("note", "")})
    return sorted(out, key=lambda e: e["id"].lower())


def _placeholders(cfg, dump, usage, notes):
    """Meshes made in code and saved as .asset under the engine root: placeholders waiting for a real model."""
    out = []
    if not dump:
        return out
    prefix = os.path.normpath(cfg["engine_root"]).lower()
    for asset in dump["assets"].values():
        if asset["kind"] != "mesh":
            continue
        p = os.path.normpath(os.path.join(dump["assets_root"], asset["path"]))
        if not p.lower().startswith(prefix):
            continue
        rel = _rel(p, cfg["engine_root"])
        used, refs = usage(p)
        out.append({"id": "engine:" + rel, "name": os.path.basename(p), "engine_path": p,
                    "category": rel.split("/")[0], "usage": used, "used_by": refs,
                    "note": notes.get("engine:" + rel, {}).get("note", "")})
    return sorted(out, key=lambda e: e["id"].lower())


def _blends(cfg):
    """Blender sources under blend_root."""
    out = []
    if not os.path.isdir(cfg["blend_dir"]):
        return out
    exts = tuple(cfg["blend_extensions"])
    for p in files.walk(cfg["blend_dir"], ["__pycache__"]):
        if p.lower().endswith(exts):
            parts = _rel(p, cfg["blend_dir"]).split("/")
            out.append({"id": _rel(p, cfg["art_root"]), "name": os.path.basename(p),
                        "category": parts[0] if len(parts) > 1 else "(root)", "path": p,
                        "mtime": os.stat(p).st_mtime})
    return out


def _unsorted(cfg):
    """Models dropped somewhere in the art root but outside every state folder and the Blender root."""
    art = cfg["art_root"]
    exts = tuple(cfg["model_extensions"])
    state_of = _state_resolver(cfg)
    skip = list(cfg["ignore"]) + [os.path.basename(d) for d in cfg["state_dirs"].values()] + [cfg["blend_root"]]
    out = []
    for p in files.walk(art, skip):
        if p.lower().endswith(exts) and state_of(p)[0] is None and not p.lower().startswith(cfg["blend_dir"].lower()):
            out.append({"id": _rel(p, art), "name": os.path.basename(p), "path": p})
    return out


# --- helpers ------------------------------------------------------------------------------------------------------

def _state_resolver(cfg):
    """path -> (state, state folder); the most specific (longest) state folder wins when they nest."""
    ordered = sorted(cfg["state_dirs"].items(), key=lambda kv: -len(kv[1]))

    def state_of(path):
        low = path.lower()
        for state, d in ordered:
            if low.startswith(d.lower() + os.sep):
                return state, d
        return None, None

    return state_of


def _category(parts, cfg, state):
    """Category of a model from its path segments under the state folder: the first segment that is a known
    category, else the first folder segment. Archive folders are dated, so there an unknown path is "(other)"."""
    folders = parts[:-1]
    if not folders:
        return "(root)"
    known = {c.lower(): c for c in cfg.get("categories", [])}
    for segment in folders:
        if segment.lower() in known:
            return known[segment.lower()]
    return "(other)" if state == "archive" else folders[0]


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")
