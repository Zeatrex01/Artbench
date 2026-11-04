"""Scene inventory, read-only: what each scene uses. From the passive engine dump, the scene's references are
followed through prefabs, nested prefabs and materials until art leaves (models, meshes, textures); a fresh, loaded
live report from an engine bridge replaces the files view for that scene (it also sees unsaved changes) and its
asset-to-asset references are expanded the same way. Every used asset is matched to its art item. Nothing here
writes anything, anywhere."""
import collections
import os

from . import engines, live, scan
from .errors import NotFound

LEAF_KINDS = ("model", "mesh", "texture", "sprite")
THROUGH_KINDS = ("prefab", "material")           # followed; scripts, data assets, animators, audio are not
MAX_DEPTH = 8
KIND_ORDER = ("prefab", "model", "mesh", "material", "texture", "sprite")


def inventory(cfg, scene=None):
    """[{path, source, time, dirty, uses: [...]}] for every scene, or only `scene` ("Assets/..."); KeyError if unknown."""
    dump = engines.dump(cfg) or {"assets": {}, "refs": {}}
    prefix = engines.of(cfg).prefix
    graph = _Graph(dump, prefix)
    state = scan.scan(cfg)
    match = _matcher(cfg, state)
    reported = live.scenes(cfg)
    paths = sorted({prefix + a["path"] for a in dump["assets"].values() if a["kind"] == "scene"} |
                   {p for p, e in reported.items() if e.get("loaded") and live.is_fresh(cfg, e)})
    if scene is not None:
        wanted = scene.replace("\\", "/")
        if wanted not in paths:
            raise NotFound(f"no scene {scene!r}")
        paths = [wanted]
    return [_one(cfg, path, reported.get(path), graph, match) for path in paths]


def _one(cfg, path, entry, graph, match):
    prefix = graph.prefix
    if entry and entry.get("loaded") and entry.get("node_count") and live.is_fresh(cfg, entry):
        reported = {}
        for u in entry["uses"]:                  # a use sent by path only is the same asset as one sent by id
            asset_id = u.get("id") or graph.guid_of.get(u["path"][len(prefix):], "")
            merged = reported.setdefault(asset_id or u["path"], dict(u, id=asset_id, count=0))
            merged["count"] += u["count"]
        counts = {key: u["count"] for key, u in reported.items()}
        found = {}
        for key, u in reported.items():
            known = graph.assets.get(key)
            found[key] = ((prefix + known["path"]) if known else u["path"], known["kind"] if known else u["kind"])
            if known and found[key][1] in THROUGH_KINDS:
                found.update(graph.reach(key))
        uses = [_use(p, k, counts.get(key), match) for key, (p, k) in found.items()]
        return {"path": path, "source": "live", "time": entry.get("time"), "dirty": entry.get("dirty", False),
                "uses": _sorted(uses)}
    own = graph.guid_of.get(path[len(prefix):])
    uses = [_use(p, k, None, match) for p, k in graph.reach(own).values()] if own else []
    return {"path": path, "source": "files", "time": None, "dirty": False, "uses": _sorted(uses)}


class _Graph:
    """Outgoing references by guid, from the dump's referrer lists."""

    def __init__(self, dump, prefix):
        self.prefix = prefix
        self.assets = dump["assets"]
        self.guid_of = {a["path"]: g for g, a in self.assets.items()}
        self.out = collections.defaultdict(set)
        for target, referrers in dump["refs"].items():
            for r in referrers:
                if r in self.guid_of:
                    self.out[self.guid_of[r]].add(target)

    def reach(self, start):
        """{guid: (Assets path, kind)} of everything reachable from start, stopping at art leaves; cycles end."""
        found, seen, frontier = {}, {start}, [start]
        for _ in range(MAX_DEPTH):
            nxt = []
            for g in frontier:
                for t in sorted(self.out.get(g, ())):
                    if t in seen or t not in self.assets:
                        continue
                    seen.add(t)
                    a = self.assets[t]
                    if a["kind"] not in KIND_ORDER:
                        continue
                    found[t] = (self.prefix + a["path"], a["kind"])
                    if a["kind"] in THROUGH_KINDS:
                        nxt.append(t)
            frontier = nxt
            if not frontier:
                break
        return found


def _matcher(cfg, state):
    """Absolute engine path -> what the art side knows about it."""
    index = {}
    for item in state["items"]:
        files = (item.get("package") or {}).get("files") or []
        for f in files[1:]:
            if f.get("engine_path"):
                index[_key(f["engine_path"])] = {"desktop_id": item["id"], "file_id": f["id"], "sync": f.get("sync")}
        if item.get("engine_path"):
            index[_key(item["engine_path"])] = {"desktop_id": item["id"], "file_id": None,
                                               "sync": (item.get("package") or {}).get("state") or item.get("sync")}
    for entry in state["engine_only"]:
        index.setdefault(_key(entry["engine_path"]), {"desktop_id": None, "file_id": None, "sync": None,
                                                      "engine_id": entry["id"]})
    for entry in state["placeholders"]:
        index.setdefault(_key(entry["engine_path"]), {"desktop_id": None, "file_id": None, "sync": None,
                                                      "engine_id": entry["id"], "placeholder": True})
    adapter = engines.of(cfg)
    root, prefix = adapter.content_root(cfg), adapter.prefix
    for entry in (state.get("catalog") or {}).get("assets", []):        # project mode: every asset has an engine id
        index.setdefault(_key(os.path.join(root, entry["path"][len(prefix):])),
                         {"desktop_id": None, "file_id": None, "sync": None, "engine_id": entry["id"]})

    def match(path):
        return index.get(_key(os.path.join(root, path[len(prefix):])), {})
    return match


def _key(path):
    return os.path.normcase(os.path.normpath(path))


def _use(path, kind, count, match):
    m = match(path)
    return {"path": path, "kind": kind, "count": count, "desktop_id": m.get("desktop_id"), "file_id": m.get("file_id"),
            "engine_id": m.get("engine_id"), "sync": m.get("sync"), "placeholder": m.get("placeholder", False)}


def _sorted(uses):
    rank = {k: i for i, k in enumerate(KIND_ORDER)}
    return sorted(uses, key=lambda u: (rank.get(u["kind"], len(rank)), u["path"].lower()))
