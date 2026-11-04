"""Metadata snapshots of models and the structural difference between two of them: what a change actually changes
(vertices, objects, materials, textures, bones, animations, bounding box) instead of "the file changed". Snapshots
are produced by background Blender (model_meta.py) through blender_jobs and cached by content hash; this module
diffs them, renders the summary lines the card shows and the Unity-compatibility warnings the send plan shows."""
import json
import os

from . import blender_jobs, store

SNAPSHOT_VERSION = 1
META_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_meta.py")
CACHE_KIND = "meta"
CACHE_EXT = f"v{SNAPSHOT_VERSION}.json"


# --- snapshots ---------------------------------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def snapshot_for_hash(sha):
    """The cached snapshot of a content hash, or None (the content may no longer exist as a file)."""
    return _read(blender_jobs.cache_path_for_hash(CACHE_KIND, sha, CACHE_EXT))


def request_snapshot(cfg, path):
    """Queues a snapshot of `path` (snapshots run before thumbnails). Returns the job state; "none" without a file."""
    if not path or not os.path.isfile(path):
        return "none"
    return blender_jobs.request(cfg, META_SCRIPT, path, blender_jobs.cache_path(CACHE_KIND, path, CACHE_EXT),
                                priority=blender_jobs.PRIORITY_META)


def snapshot_status(cfg, path):
    """(state, snapshot | None): "ready" | "pending" | "failed" | "none" (no Blender or no file). A cache file that
    does not parse counts as failed, never as an empty snapshot."""
    state = request_snapshot(cfg, path)
    if state != "ready":
        return state, None
    snap = _read(blender_jobs.cache_path(CACHE_KIND, path, CACHE_EXT))
    return ("ready", snap) if snap else ("failed", None)


def snapshot_sync(cfg, path):
    """The snapshot now, running Blender on this thread when it is not cached (the send plan). None without Blender."""
    if not path or not os.path.isfile(path):
        return None
    out = blender_jobs.cache_path(CACHE_KIND, path, CACHE_EXT)
    if blender_jobs.run_now(cfg, META_SCRIPT, path, out):
        return _read(out)
    return None


def stats_of(snap):
    """The counts the catalog shows for a model: triangles, vertices, mesh objects, materials, textures, bones, animations."""
    totals = snap.get("totals") or {}
    return {"tris": totals.get("tris", 0), "verts": totals.get("verts", 0),
            "objects": sum(1 for o in snap.get("objects") or [] if o.get("type") == "MESH"),
            "materials": len(snap.get("materials") or []), "textures": len(snap.get("textures") or []),
            "bones": snap.get("bones") or 0, "animations": len(snap.get("actions") or [])}


def attach_stats(cfg, entries, path_of):
    """Puts "stats" on every model entry: stats_of() its cached snapshot, or None while Blender measures it (queued
    behind the previews; nothing is queued without Blender). path_of(entry) is the model's file."""
    for e in entries:
        if e.get("kind") != "model":
            continue
        path = path_of(e)
        snap = None
        if path and os.path.isfile(path):
            snap = _read(blender_jobs.cache_path(CACHE_KIND, path, CACHE_EXT))
            if snap is None:
                blender_jobs.request(cfg, META_SCRIPT, path, blender_jobs.cache_path(CACHE_KIND, path, CACHE_EXT),
                                     priority=blender_jobs.PRIORITY_STATS)
        e["stats"] = stats_of(snap) if snap else None
    return entries


# --- card payload -----------------------------------------------------------------------------------------------

def compare(cfg, item):
    """Everything the card's Changes section shows for a desktop item (schema in ARCHITECTURE.md, Compare)."""
    engine_path = item.get("engine_path") if item.get("engine_path") and os.path.exists(item["engine_path"]) else None
    size = {"art": os.path.getsize(item["path"]) if os.path.exists(item["path"]) else None,
            "engine": os.path.getsize(engine_path) if engine_path else None}
    out = {"state": "ready", "sync": item.get("sync"), "basis": item.get("basis"), "send": None, "after": None,
           "conflict": None, "affected": item.get("used_by") or [], "size": size}
    art_state, art_snap = snapshot_status(cfg, item["path"])
    states = [art_state]
    engine_snap = None
    if engine_path:
        engine_state, engine_snap = snapshot_status(cfg, engine_path)
        states.append(engine_state)
    for bad in ("none", "failed", "pending"):
        if bad in states:
            out["state"] = bad
            return out
    if engine_path:
        d = diff(engine_snap, art_snap)
        out["send"] = {"before": engine_snap, "after": art_snap, "diff": d, "summary": summary(d),
                       "warnings": warnings(engine_snap, art_snap)}
    else:
        out["after"] = art_snap
    if item.get("sync") == "conflict":
        base = store.sync_base(cfg).get(item["id"]) or {}
        base_snap = snapshot_for_hash(base["art"]) if base.get("art") else None
        if base_snap:
            d_art, d_engine = diff(base_snap, art_snap), diff(base_snap, engine_snap)
            out["conflict"] = {"art": {"diff": d_art, "summary": summary(d_art)},
                               "engine": {"diff": d_engine, "summary": summary(d_engine)}}
    return out


# --- diff ------------------------------------------------------------------------------------------------------


def names(snap, key):
    """Names under `key` ("objects" | "actions" | ...) for both the versioned shape (`<key>_names`) and the old
    fingerprint shape (a plain list of names under `key`)."""
    if not snap:
        return []
    if f"{key}_names" in snap:
        return list(snap[f"{key}_names"])
    value = snap.get(key) or []
    return [v if isinstance(v, str) else v.get("name") for v in value]


def _added_removed(before, after):
    b, a = set(before), set(after)
    return sorted(a - b), sorted(b - a)


def _totals(snap, key):
    if snap.get("totals") and key in snap["totals"]:
        return snap["totals"][key]
    return sum(o.get(key, 0) for o in snap.get("objects", []) if isinstance(o, dict))


def diff(before, after):
    """Structural difference between two snapshots (schema in ARCHITECTURE.md, Diff)."""
    before, after = before or {}, after or {}
    objs_b = {o["name"]: o for o in before.get("objects", []) if isinstance(o, dict)}
    objs_a = {o["name"]: o for o in after.get("objects", []) if isinstance(o, dict)}
    added_o, removed_o = _added_removed(names(before, "objects"), names(after, "objects"))
    changed_o = [{"name": n, "verts": [objs_b[n].get("verts", 0), objs_a[n].get("verts", 0)]}
                 for n in sorted(set(objs_b) & set(objs_a)) if objs_b[n].get("verts") != objs_a[n].get("verts")]
    added_m, removed_m = _added_removed(before.get("materials", []), after.get("materials", []))
    added_t, removed_t = _added_removed(before.get("textures", []), after.get("textures", []))
    added_b, removed_b = _added_removed(before.get("bone_names", []), after.get("bone_names", []))
    added_a, removed_a = _added_removed(names(before, "actions"), names(after, "actions"))
    acts_b = {a["name"]: a for a in before.get("actions", []) if isinstance(a, dict)}
    acts_a = {a["name"]: a for a in after.get("actions", []) if isinstance(a, dict)}
    ranges = [{"name": n, "before": [acts_b[n].get("start"), acts_b[n].get("end")], "after": [acts_a[n].get("start"), acts_a[n].get("end")]}
              for n in sorted(set(acts_b) & set(acts_a))
              if (acts_b[n].get("start"), acts_b[n].get("end")) != (acts_a[n].get("start"), acts_a[n].get("end"))]
    bbox_b, bbox_a = before.get("bbox"), after.get("bbox")
    out = {
        "geometry": {"verts": [_totals(before, "verts"), _totals(after, "verts")],
                     "polys": [_totals(before, "polys"), _totals(after, "polys")],
                     "tris": [_totals(before, "tris"), _totals(after, "tris")],
                     "objects_added": added_o, "objects_removed": removed_o, "objects_changed": changed_o},
        "materials": {"added": added_m, "removed": removed_m},
        "textures": {"added": added_t, "removed": removed_t},
        "skeleton": {"bones": [before.get("bones", 0), after.get("bones", 0)], "added": added_b, "removed": removed_b},
        "animations": {"added": added_a, "removed": removed_a, "range_changed": ranges},
        "bbox": {"before": bbox_b, "after": bbox_a, "changed": bool(bbox_b and bbox_a and bbox_b != bbox_a)},
    }
    g = out["geometry"]
    out["empty"] = not (g["verts"][0] != g["verts"][1] or g["polys"][0] != g["polys"][1] or g["tris"][0] != g["tris"][1]
                        or added_o or removed_o or changed_o or added_m or removed_m or added_t or removed_t
                        or out["skeleton"]["bones"][0] != out["skeleton"]["bones"][1] or added_b or removed_b
                        or added_a or removed_a or ranges or out["bbox"]["changed"])
    return out


def _n(v):
    return f"{v:,}" if isinstance(v, int) else str(v)


def summary(d):
    """Human-readable lines for a diff, in the order the card shows them."""
    if d.get("empty"):
        return []
    lines = []
    g = d["geometry"]
    for key, label in (("verts", "Vertices"), ("polys", "Polygons"), ("tris", "Triangles")):
        if g[key][0] != g[key][1]:
            lines.append(f"{label}: {_n(g[key][0])} → {_n(g[key][1])}")
    lines += [f"Added object: {n}" for n in g["objects_added"]]
    lines += [f"Removed object: {n}" for n in g["objects_removed"]]
    lines += [f"Changed object: {c['name']} (vertices {_n(c['verts'][0])} → {_n(c['verts'][1])})" for c in g["objects_changed"]]
    lines += [f"Added material: {n}" for n in d["materials"]["added"]]
    lines += [f"Removed material: {n}" for n in d["materials"]["removed"]]
    lines += [f"Added texture: {n}" for n in d["textures"]["added"]]
    lines += [f"Removed texture: {n}" for n in d["textures"]["removed"]]
    s = d["skeleton"]
    if s["bones"][0] != s["bones"][1]:
        lines.append(f"Bones: {_n(s['bones'][0])} → {_n(s['bones'][1])}")
    lines += [f"Added bone: {n}" for n in s["added"]]
    lines += [f"Removed bone: {n}" for n in s["removed"]]
    a = d["animations"]
    lines += [f"Added animation: {n}" for n in a["added"]]
    lines += [f"Removed animation: {n}" for n in a["removed"]]
    lines += [f"Animation range changed: {r['name']} {r['before'][0]}–{r['before'][1]} → {r['after'][0]}–{r['after'][1]}" for r in a["range_changed"]]
    if d["bbox"]["changed"]:
        lines.append("Bounding box changed")
    return lines


def warnings(before, after):
    """Differences that break Unity references, as the send plan has always worded them. Empty when either side is
    unknown."""
    if not before or not after:
        return []
    out = []
    for key, label in (("objects", "object"), ("materials", "material slot"), ("actions", "animation take")):
        old = names(before, key) if key != "materials" else list(before.get("materials", []))
        new = names(after, key) if key != "materials" else list(after.get("materials", []))
        added, gone = _added_removed(old, new)
        if gone:
            out.append(f"{label}s missing in the new file: {', '.join(gone)}")
        if added:
            out.append(f"new {label}s: {', '.join(added)}")
    if before.get("bones", 0) != after.get("bones", 0):
        out.append(f"bone count {before.get('bones', 0)} -> {after.get('bones', 0)}")
    return out
