"""Reference graph of the art side, built from the Unity dump: every art asset under the engine root (models, meshes,
textures, materials, prefabs, scenes, clips, animators) is a node, every direct reference an edge
(referrer -> referenced). Scripts and shaders are left out; referrers outside the engine root are kept so that a
block prefab used by a scene in _PROJECT still shows as used."""
import os

ART_KINDS = ("model", "mesh", "texture", "material", "prefab", "scene", "clip", "animator", "data", "atlas", "audio")
# What the graph shows. Unity ".asset" files (ScriptableObject data, code-made meshes, physics materials) are left
# out: not every .asset is art, and they drown the picture. Placeholder meshes have their own list in the scan state.
GRAPH_KINDS = tuple(k for k in ART_KINDS if k not in ("data", "mesh"))


def build(cfg, dump, items=None):
    if not dump:
        return {"nodes": [], "edges": []}
    aroot = dump["assets_root"]
    rel_root = os.path.relpath(cfg["engine_root"], aroot).replace("\\", "/").rstrip("/")
    eroot = "" if rel_root == "." else rel_root + "/"          # project mode: the engine root is the content root
    kind_of = {a["path"]: a["kind"] for a in dump["assets"].values()}
    path_of = {g: a["path"] for g, a in dump["assets"].items()}
    desktop = {}
    for it in items or []:
        if it.get("engine_path"):
            rel = os.path.relpath(it["engine_path"], aroot).replace("\\", "/")
            desktop[rel] = it["id"]

    nodes, edges = {}, []

    def node(path):
        if path in nodes:
            return nodes[path]
        kind = kind_of.get(path, "other")
        inside = path.startswith(eroot)
        rel = path[len(eroot):] if inside else path
        n = {"id": path, "name": os.path.basename(path), "kind": kind, "inside": inside,
             "category": rel.split("/")[0] if "/" in rel else "(root)", "in": 0, "out": 0}
        if inside:
            n["engine_id"] = "engine:" + rel          # the id engine_only / placeholder entries use
        if path in desktop:
            n["desktop_id"] = desktop[path]
        nodes[path] = n
        return n

    for path, kind in kind_of.items():
        if path.startswith(eroot) and kind in GRAPH_KINDS:
            node(path)
    for guid, referrers in dump["refs"].items():
        target = path_of.get(guid)
        if not target or kind_of.get(target) not in GRAPH_KINDS:
            continue
        if target not in nodes:
            continue                      # referenced asset outside the art root (shared core asset)
        for r in referrers:
            if kind_of.get(r) not in GRAPH_KINDS:
                continue
            node(r)
            edges.append({"from": r, "to": target})
            nodes[r]["out"] += 1
            nodes[target]["in"] += 1
    return {"nodes": list(nodes.values()), "edges": edges, "root": eroot}
