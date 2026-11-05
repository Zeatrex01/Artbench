"""Export: copy chosen models out of the game project, each with the textures it uses (catalog.textures_of), into a
folder of the person's own, one folder per model (two models with one name: Crate, Crate_2). Plan first: every file
with its target and whether something is already there; then copy. Nothing is overwritten or deleted, .meta files
stay behind, and the folder may not be inside the game project or the art folder. One EXPORT history line per run.
Ids are engine ones (engine:<path under the content root>), in either mode."""
import os
import shutil

from . import catalog, config, engines, scan, store


def _catalog(cfg):
    return scan.scan(cfg)["catalog"] if config.is_project_mode(cfg) else catalog.build(cfg, engines.dump(cfg))


def _inside(path, folder):
    if not folder:
        return False
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path == folder or path.startswith(folder.rstrip("\\/") + os.sep)


def _check_dest(cfg, dest):
    dest = (dest or "").strip()
    if not dest or not os.path.isabs(dest):
        raise ValueError("choose a folder (a full path) to export into")
    adapter = engines.of(cfg)
    for name, folder in (("the game project", adapter.project_root(cfg)), ("the art folder", cfg.get("art_root"))):
        if _inside(dest, folder):
            raise ValueError(f"the export folder is inside {name}: choose a folder of your own")
    return os.path.normpath(dest)


def plan(cfg, ids, dest):
    """{dest, models: [{id, name, folder, files: [{source, target, role, size, exists}]}], files, exists, bytes}."""
    dest = _check_dest(cfg, dest)
    if not ids:
        raise ValueError("no models chosen")
    cat = _catalog(cfg)
    by_id, by_path = {a["id"]: a for a in cat["assets"]}, {a["path"]: a for a in cat["assets"]}
    root, prefix = engines.content_root(cfg), engines.of(cfg).prefix
    taken, models = set(), []
    for asset_id in ids:
        entry = by_id.get(asset_id)
        if entry is None or entry["kind"] != "model":
            raise ValueError(f"not a model in the game project: {asset_id}")
        stem = os.path.splitext(entry["name"])[0]
        name, n = stem, 1
        while name.lower() in taken:
            n += 1
            name = f"{stem}_{n}"
        taken.add(name.lower())
        folder = os.path.join(dest, name)
        rows, names = [], set()
        for role, path in [("model", entry["path"])] + [("texture", p) for p in catalog.textures_of(by_path, entry)]:
            source = os.path.join(root, *path[len(prefix):].split("/"))
            base = os.path.basename(path)
            if base.lower() in names:                     # two textures of one name: the first one goes
                continue
            names.add(base.lower())
            target = os.path.join(folder, base)
            rows.append({"source": source, "target": target, "role": role, "path": path,
                         "size": os.path.getsize(source) if os.path.isfile(source) else None,
                         "exists": os.path.exists(target)})
        models.append({"id": asset_id, "name": entry["name"], "folder": folder, "files": rows})
    every = [f for m in models for f in m["files"]]
    return {"dest": dest, "models": models, "files": len(every), "exists": sum(1 for f in every if f["exists"]),
            "bytes": sum(f["size"] or 0 for f in every)}


def run(cfg, ids, dest):
    """Copies what the plan lists, skipping every file already there (and any source gone meanwhile).
    {dest, models, copied, skipped}."""
    p = plan(cfg, ids, dest)
    copied = skipped = 0
    for f in (f for m in p["models"] for f in m["files"]):
        if os.path.exists(f["target"]) or not os.path.isfile(f["source"]):
            skipped += 1
            continue
        os.makedirs(os.path.dirname(f["target"]), exist_ok=True)
        shutil.copy2(f["source"], f["target"])
        copied += 1
    with store.locked(cfg):
        store.log(cfg, "EXPORT", p["dest"], f"{len(p['models'])} models, {copied} files copied, {skipped} skipped")
    return {"dest": p["dest"], "models": len(p["models"]), "copied": copied, "skipped": skipped}
