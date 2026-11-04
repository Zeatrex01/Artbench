"""Live engine reports: what an engine bridge (the Unity editor tool, later) tells Artbench while the editor is open.
A report carries scene contents (every node and the assets it uses directly) and asset events (imported, moved,
deleted). Reports are derived engine knowledge, not project data: they are kept in the tool's own cache, written
atomically without the project lock and without a history line. The passive dump stays the ground truth; a scene's
live entry only counts while it is fresh (per scene, by the time Artbench received it). Every merge into the cache
holds an OS lock beside it, so reports from any process are never lost."""
import os
import time

from . import config, engines, store
from .errors import Unavailable

CACHE_DIR = os.path.join(config.TOOL_ROOT, ".cache", "live")
SCHEMA = 1
MAX_EVENTS = 200
ACCEPT_TIMEOUT = 10                  # seconds a report waits for another writer of the same cache
EVENT_TYPES = ("imported", "moved", "deleted")
DEFAULT_LIMITS = {"scenes": 200, "nodes": 200000, "uses": 1000000}


def limits(cfg):
    """Per-report limits: config report_limits over DEFAULT_LIMITS. A malformed value is the project config's fault,
    not the bridge's: Unavailable naming the config."""
    extra = cfg.get("report_limits") or {}
    if not isinstance(extra, dict) or set(extra) - set(DEFAULT_LIMITS) or \
            any(type(v) is not int or v < 0 for v in extra.values()):
        raise Unavailable(f"report_limits in {cfg.get('config_path') or 'the project config'} must map "
                          f"{', '.join(DEFAULT_LIMITS)} to whole numbers of 0 or more")
    return dict(DEFAULT_LIMITS, **extra)


def _same_folder(a, b):
    """Two folder paths name the same place whatever slashes or trailing separator a bridge used."""
    norm = lambda p: os.path.normcase(os.path.normpath(p.replace("\\", "/")))
    return norm(a) == norm(b)


def cache_file(cfg):
    return os.path.join(CACHE_DIR, f"{cfg['id']}.json")


def lock_file(cfg):
    """The OS lock serialising every read-modify-write of this project's report cache, whichever process writes."""
    return os.path.join(CACHE_DIR, f"{cfg['id']}.lock")


_memo = {}                                   # cache file -> ((mtime_ns, size), parsed data): one parse per change


def _load(cfg):
    """The stored reports, parsed once per change of the file (the page polls status every few seconds)."""
    path = cache_file(cfg)
    try:
        st = os.stat(path)
    except OSError:
        return {}
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _memo.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    data = store._read_json(path, {})
    data = data if isinstance(data, dict) else {}
    _memo[path] = (stamp, data)
    return data


def _asset_path(adapter, value, what):
    """An engine path in the engine's own form ("Assets/...", "res://...") or ValueError; never anything outside it."""
    try:
        return adapter.normalize_engine_path(value)
    except ValueError as e:
        raise ValueError(f"{what}: {e}") from None


def _objects(value, what):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise ValueError(f"{what} must be a list of objects")
    return value


def _validate(cfg, report):
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    if report.get("schema") != SCHEMA:
        raise ValueError(f"report schema must be {SCHEMA}")
    adapter = engines.of(cfg)
    own = adapter.project_root(cfg)
    sent = report.get("project_path")
    if not own or not isinstance(sent, str) or not _same_folder(sent, own):
        raise ValueError(f"report is for another engine project ({sent!r}), expected {own!r}")
    cap, total = limits(cfg), {"scenes": 0, "nodes": 0, "uses": 0}

    def count(name):
        total[name] += 1
        if total[name] > cap[name]:
            raise ValueError(f"report over the {name} limit ({cap[name]})")
    scenes = []
    for s in _objects(report.get("scenes"), "scenes"):
        count("scenes")
        uses, skipped, nodes = {}, 0, 0
        for n in _objects(s.get("nodes"), "nodes"):
            count("nodes")
            nodes += 1
            mine = {}
            for u in _objects(n.get("uses"), "uses"):
                count("uses")
                raw = u.get("path")
                if not adapter.is_engine_path(raw):
                    skipped += 1                 # built-in and package resources: not art Artbench tracks
                    continue
                use = {"id": str(u.get("id") or ""), "path": _asset_path(adapter, raw, "uses"), "kind": str(u.get("kind") or "")}
                mine[use["id"] or use["path"]] = use
            for key, use in mine.items():        # a node counts once per asset it uses
                uses.setdefault(key, dict(use, count=0))["count"] += 1
        scenes.append({"path": _asset_path(adapter, s.get("path"), "scene"), "loaded": bool(s.get("loaded")),
                       "dirty": bool(s.get("dirty")), "node_count": nodes, "uses": list(uses.values()), "skipped_uses": skipped})
    events = []
    for e in _objects(report.get("events"), "events"):
        if e.get("type") not in EVENT_TYPES:
            raise ValueError(f"unknown event type {e.get('type')!r}")
        event = {"type": e["type"], "path": _asset_path(adapter, e.get("path"), "event"), "time": e.get("time")}
        if e["type"] == "moved":
            event["from"] = _asset_path(adapter, e.get("from"), "event from")
        events.append(event)
    return scenes, events


def accept(cfg, report):
    """Validates a bridge report and stores it; nothing is stored when any part is invalid. Returns status()."""
    scenes, events = _validate(cfg, report)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with store.locked_path(lock_file(cfg), ACCEPT_TIMEOUT):     # load-merge-write: no other writer in between
        _memo.pop(cache_file(cfg), None)                         # another process may have written since
        now = time.time()
        data = dict(_load(cfg))
        data["scenes"] = dict(data.get("scenes") or {})
        data.update({"bridge": str(report.get("bridge") or "unknown"), "engine": report.get("engine"),
                     "engine_version": report.get("engine_version"), "last_report": now})
        stored = data["scenes"]
        for s in scenes:
            stored[s["path"]] = dict(s, time=now, report_time=report.get("time"))
        if events:
            data["events"] = ((data.get("events") or []) + events)[-MAX_EVENTS:]
            engines.of(cfg).mark_dump_stale(cfg, now)        # first: a failure here stores nothing
        data.pop("invalidated", None)                        # the stale mark before 2026-11-02; the adapter keeps it now
        store._write_json(cache_file(cfg), data, compact=True)
        _memo.pop(cache_file(cfg), None)
        _load(cfg)                           # parse once now, not on the next poll
    return status(cfg)


def is_fresh(cfg, entry):
    """True while a stored scene entry is younger than bridge_fresh_seconds."""
    return bool(entry) and time.time() - entry.get("time", 0) <= float(cfg.get("bridge_fresh_seconds", 600))


def scenes(cfg):
    """{scene path: stored live entry} (read-only)."""
    return _load(cfg).get("scenes") or {}


def scene(cfg, path):
    """The stored live entry for a scene path ("Assets/...", either slash), or None."""
    return (_load(cfg).get("scenes") or {}).get(path.replace("\\", "/"))


def status(cfg):
    data = _load(cfg)
    return {"bridge": data.get("bridge"), "last_report": data.get("last_report"),
            "scenes": [{"path": p, "time": s.get("time"), "fresh": is_fresh(cfg, s), "loaded": s.get("loaded", False),
                        "skipped_uses": s.get("skipped_uses", 0)}
                       for p, s in sorted((data.get("scenes") or {}).items())],
            "events": data.get("events") or []}
