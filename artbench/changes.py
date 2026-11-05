"""Change feed: what changed on disk since the last look, on both sides, whoever changed it. Each update compares a
snapshot of the tracked files (models, textures, Blender sources under the art root; models and textures under the
engine root) with the previous snapshot and appends ADDED / CHANGED / REMOVED lines to changes.log in the art
folder. The first update only records a baseline.

Project mode (the engine project alone) tracks every asset of the catalog's kinds by its id (Unity: the guid), so a
file moved with its .meta is one MOVED line, not a removal and an addition. "Since the last look" there is whatever
came after the person's last Mark as seen (`mark_seen`), kept in seen.json beside the log: page polls and agent calls
grow the log but never move the mark."""
import json
import os
import time

from . import config, engines, files, store

SNAPSHOT_FILE = "snapshot.json"
CHANGES_FILE = "changes.log"
SEEN_FILE = "seen.json"
SIDES = ("art", "engine")


BUFFER_EXTENSIONS = [".bin"]                 # a .gltf's geometry: a change there is a change to the model


def _tracked_exts(cfg):
    return tuple(cfg["model_extensions"] + cfg["texture_extensions"] + cfg["blend_extensions"] + BUFFER_EXTENSIONS)


def snapshot(cfg):
    """{"art:<rel>" | "engine:<rel>": {"hash", "size"}} for every tracked file."""
    exts = _tracked_exts(cfg)
    out = {}
    roots = [("art", cfg["art_root"], cfg["ignore"])] if cfg.get("art_root") else []
    if cfg.get("engine_root") and os.path.isdir(cfg["engine_root"]):
        roots.append(("engine", cfg["engine_root"], cfg["engine_ignore"]))
    for side, root, ignore in roots:
        for p in files.walk(root, ignore):
            if p.lower().endswith(exts):
                rel = os.path.relpath(p, root).replace("\\", "/")
                out[f"{side}:{rel}"] = {"hash": files.sha(p), "size": os.path.getsize(p)}
    return out


LOOK_LOCK_TIMEOUT = 2.0         # seconds; a look that finds the project busy is skipped, the next one catches up


def _asset_snapshot(cfg, force=False):
    """Project mode: ({asset id: {"path", "hash", "size"}} for every dump asset of the catalog's kinds, whether a dump
    path was missing); (None, False) when the engine project cannot be read. The hash covers the asset and its .meta,
    so a change of import settings is a change too."""
    dump = engines.dump(cfg, force=force)
    if not dump:
        return None, False
    prefix = engines.of(cfg).prefix
    kinds = set(cfg.get("catalog_kinds") or [])
    out, missing = {}, False
    for asset_id, a in dump["assets"].items():
        if a["kind"] not in kinds:
            continue
        p = os.path.normpath(os.path.join(dump["assets_root"], a["path"]))
        try:
            meta = p + ".meta"
            digest = files.sha(p) + ":" + (files.sha(meta) if os.path.exists(meta) else "")
            out[asset_id] = {"path": prefix + a["path"], "hash": digest, "size": os.path.getsize(p)}
        except OSError:
            missing = True                            # moved or deleted since the dump was read
    return out, missing


def _project_update(cfg, path):
    try:
        with open(path, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = None
    current, missing = _asset_snapshot(cfg) if not engines.unreachable(cfg) else (None, False)
    if missing:
        # The cached dump (up to a minute old) names a file that is gone: read the project again before diffing, so a
        # move is one MOVED line and not a removal now and an addition at the next rebuild.
        current, _ = _asset_snapshot(cfg, force=True)
    if current is None:
        # an unplugged drive or a moved clone is not a mass removal: nothing is logged until it can be read again
        files.save_cache()
        return []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entries = []
    if previous is None:
        entries.append({"time": stamp, "change": "BASELINE", "side": "engine", "path": f"{len(current)} assets"})
    else:
        for asset_id, info in current.items():
            old = previous.get(asset_id)
            if old is None:
                entries.append({"time": stamp, "change": "ADDED", "side": "engine", "path": info["path"]})
            elif old["path"] != info["path"]:
                entries.append({"time": stamp, "change": "MOVED", "side": "engine", "path": info["path"],
                                "from": old["path"]})
            elif old["hash"] != info["hash"]:
                entries.append({"time": stamp, "change": "CHANGED", "side": "engine", "path": info["path"]})
        for asset_id, old in previous.items():
            if asset_id not in current:
                entries.append({"time": stamp, "change": "REMOVED", "side": "engine", "path": old["path"]})
    if entries:
        _append(cfg, entries)
        store._write_json(path, current)
    files.save_cache()
    return entries


def _append(cfg, entries):
    with open(os.path.join(store.data_dir(cfg), CHANGES_FILE), "a", encoding="utf-8") as f:
        for e in entries:
            fields = [e["time"], e["change"], e["side"], e["path"]] + ([e["from"]] if e.get("from") else [])
            f.write("\t".join(fields) + "\n")


def update(cfg):
    """Compares with the stored snapshot, logs the differences, stores the new snapshot. Returns the new entries.
    Under the project lock, so the page server and an agent's MCP process looking at once cannot both log one change;
    a look that finds the project busy is skipped (the next look catches up)."""
    try:
        with store.locked(cfg, timeout=LOOK_LOCK_TIMEOUT):
            return _update(cfg)
    except TimeoutError:
        return []


def _update(cfg):
    path = os.path.join(store.data_dir(cfg), SNAPSHOT_FILE)
    if config.is_project_mode(cfg):
        return _project_update(cfg, path)
    try:
        with open(path, encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = None
    current = snapshot(cfg)
    if previous is not None and engines.unreachable(cfg):
        # an unplugged drive or moved clone is not a mass removal: keep the engine side as it was last seen
        current.update({k: v for k, v in previous.items() if k.startswith("engine:")})
    entries = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if previous is None:
        entries.append({"time": stamp, "change": "BASELINE", "side": "art", "path": f"{len(current)} files"})
    else:
        for key, info in current.items():
            old = previous.get(key)
            if old is None:
                entries.append(_entry(stamp, "ADDED", key))
            elif old["hash"] != info["hash"]:
                entries.append(_entry(stamp, "CHANGED", key))
        for key in previous:
            if key not in current:
                entries.append(_entry(stamp, "REMOVED", key))
    if entries:
        _append(cfg, entries)
        store._write_json(path, current)                   # a quiet look rewrites nothing (OneDrive, locks)
    files.save_cache()
    return entries


def _lines(cfg):
    path = os.path.join(store.data_dir(cfg), CHANGES_FILE)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _parse(lines):
    """Entries newest first; a MOVED line carries a fifth field, the path it came from."""
    out = []
    for line in reversed(lines):
        parts = line.split("\t")
        if len(parts) in (4, 5):
            e = {"time": parts[0], "change": parts[1], "side": parts[2], "path": parts[3]}
            if len(parts) == 5:
                e["from"] = parts[4]
            out.append(e)
    return out


def recent(cfg, limit=300):
    """The last `limit` change entries, newest first."""
    return _parse(_lines(cfg)[-limit:])


def mark_seen(cfg):
    """The person has seen everything logged so far. Returns {"seen": time, "lines": log lines covered}."""
    mark = {"seen": time.strftime("%Y-%m-%d %H:%M:%S"), "lines": len(_lines(cfg))}
    store._write_json(os.path.join(store.data_dir(cfg), SEEN_FILE), mark)
    return mark


def since_seen(cfg):
    """Change entries logged after the last mark_seen (all of them before the first), newest first; the baseline is
    not a change."""
    mark = store._read_json(os.path.join(store.data_dir(cfg), SEEN_FILE), {})
    start = mark.get("lines") if isinstance(mark, dict) and isinstance(mark.get("lines"), int) else 0
    return [e for e in _parse(_lines(cfg)[start:]) if e["change"] != "BASELINE"]


def _entry(stamp, change, key):
    side, rel = key.split(":", 1)
    return {"time": stamp, "change": change, "side": side, "path": rel}


def _names(field, keys, tails):
    """Whether one history field names the asset: one of its ids, or a path ending in one of its paths."""
    field = field.replace("\\", "/")
    return field in keys or any(field == t or field.endswith("/" + t) for t in tails)


def timeline(cfg, keys, tails):
    """One asset's own history, newest first: the history lines with a field naming it (`keys` are its ids and change
    keys, `tails` its paths) and the change feed's entries for its file. [{time, source: history | change, what,
    detail}]."""
    out = []
    for line in store.history(cfg, last=10 ** 6):
        parts = line.split("\t")
        if len(parts) > 2 and any(_names(f, keys, tails) for f in parts[2:]):
            out.append({"time": parts[0], "source": "history", "what": parts[1], "detail": " · ".join(parts[2:])})
    for e in _parse(_lines(cfg)):
        if e["change"] == "BASELINE":
            continue
        if f"{e['side']}:{e['path']}" in keys or any(_names(p, set(), tails) for p in (e["path"], e.get("from") or "") if p):
            out.append({"time": e["time"], "source": "change", "what": e["change"],
                        "detail": e["path"] + (f" (from {e['from']})" if e.get("from") else "")})
    return sorted(out, key=lambda e: e["time"], reverse=True)
