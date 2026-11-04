"""Analysis: the catalog of a game project on its own (project mode). Every asset of the engine dump whose kind the
project lists (config `catalog_kinds`), with how sure Artbench is that it is used (the engine adapter decides: used,
unreferenced, by_name, unknown), what uses it and what it uses. Pure: reads the config, the dump, file sizes and,
for textures, the first bytes of the file (size and format)."""
import os

from . import engines, image_info

MAX_PAGE = 500


def build(cfg, dump):
    """{"assets": [entry], "counts": {"kinds", "usage", "hidden"}, "force_text"} (see ARCHITECTURE.md, Schemas)."""
    if not dump:
        return {"assets": [], "counts": {"kinds": {}, "usage": {}, "hidden": 0}, "force_text": None}
    adapter = engines.of(cfg)
    prefix = adapter.prefix
    shown = set(cfg.get("catalog_kinds") or [])
    assets = dump["assets"]
    outside = dump.get("outside") or {}             # assets of ignored folders: used, not listed
    settings = dump.get("settings_refs") or {}
    build_scenes = set(dump.get("build_scenes") or ())

    path_kind = {a["path"]: a["kind"] for a in assets.values()}

    def link(rel):
        kind = path_kind.get(rel) or adapter.kind_of(rel)
        return {"path": prefix + rel, "kind": kind, "name": os.path.basename(rel)}

    out, hidden = [], 0
    kinds, usage_counts = {}, {}
    for guid, a in assets.items():
        if a["kind"] not in shown:
            hidden += 1
            continue
        rel = a["path"]
        try:
            st = os.stat(os.path.normpath(os.path.join(dump["assets_root"], rel)))
            size, mtime = st.st_size, st.st_mtime
        except OSError:
            size = mtime = None
        used = adapter.usage(dump, guid)
        entry = {
            "id": "engine:" + rel, "name": os.path.basename(rel), "kind": a["kind"], "path": prefix + rel,
            "folder": (prefix + rel).rsplit("/", 1)[0], "size": size, "mtime": mtime, "usage": used,
            "used_by": [link(r) for r in dump["refs"].get(guid, [])]
                       + [{"path": f, "kind": "settings", "name": os.path.basename(f)} for f in settings.get(guid, [])],
            "uses": [link(assets[g]["path"]) for g in (dump.get("uses") or {}).get(rel, []) if g in assets]
                    + [dict(link(outside[g]), ignored=True) for g in (dump.get("uses") or {}).get(rel, []) if g in outside],
            "in_build": (guid in build_scenes) if a["kind"] == "scene" else None,
        }
        if a["kind"] == "texture":
            entry["image"] = image_info.read(os.path.normpath(os.path.join(dump["assets_root"], rel)))
        out.append(entry)
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
        usage_counts[used] = usage_counts.get(used, 0) + 1
    out.sort(key=lambda e: (e["kind"], e["path"].lower()))
    return {"assets": out, "counts": {"kinds": kinds, "usage": usage_counts, "hidden": hidden},
            "force_text": dump.get("force_text")}



def light(cat):
    """The catalog the page polls: each entry carries used_by_count and uses_count instead of the two lists (the card
    asks for one asset in full)."""
    def row(e):
        r = {k: v for k, v in e.items() if k not in ("used_by", "uses")}
        r["used_by_count"], r["uses_count"] = len(e["used_by"]), len(e["uses"])
        return r
    return {**cat, "assets": [row(e) for e in cat["assets"]]}

def query(cat, kind=None, usage=None, folder=None, search=None, offset=0, limit=100):
    """{"total", "offset", "assets"}: the catalog filtered (kind, usage, a folder prefix, a case-insensitive name or
    path search) and paged (limit capped at MAX_PAGE)."""
    hits = cat["assets"]
    if kind:
        hits = [a for a in hits if a["kind"] == kind]
    if usage:
        hits = [a for a in hits if a["usage"] == usage]
    if folder:
        top = folder.replace("\\", "/").rstrip("/")
        hits = [a for a in hits if a["folder"] == top or a["folder"].startswith(top + "/")]
    if search:
        q = search.lower()
        hits = [a for a in hits if q in a["name"].lower() or q in a["path"].lower()]
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 100), MAX_PAGE))
    return {"total": len(hits), "offset": offset, "assets": hits[offset:offset + limit]}
