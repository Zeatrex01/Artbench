"""Operations that read the inventory: projects, overview, search, one asset, unused, the catalog, placeholders,
layout, the reference graph, scene contents."""
import os

from .. import catalog, changes, config, engines, github_link, graph, layout, scan, scenes, tasks
from ..errors import NotFound
from .common import GRAPH_CAP, LIST_CAP, _cfg, _item_summary, _page


def op_projects(_):
    return [{"id": c.get("id"), "name": c.get("name"), "mode": c.get("mode"), "art_root": c.get("art_root"),
             "engine_root": c.get("engine_root"), "error": c.get("error")} for c in config.projects()]


def _catalog_summary(entry):
    return {"id": entry["id"], "name": entry["name"], "kind": entry["kind"], "path": entry["path"],
            "usage": entry["usage"], "used_by_count": len(entry["used_by"])}


def _project_overview(cfg, state):
    cat = state["catalog"]
    return {
        "project": cfg["id"], "name": cfg.get("name"), "mode": "project", "engine_root": cfg.get("engine_root"),
        "kinds": cat["counts"]["kinds"], "usage": cat["counts"]["usage"], "hidden": cat["counts"]["hidden"],
        "placeholders": len(state["placeholders"]),
        "placeholders_in_use": sum(1 for p in state["placeholders"] if p["usage"] == "used"),
        "layout_issues": len(state["layout_issues"]), "force_text": cat["force_text"],
        "engine_unreachable": state["engine_unreachable"], "engine_scanned": state["engine_scanned"],
        "changes_since_seen": _changes_since_seen(cfg),
    }


def _changes_since_seen(cfg):
    changes.update(cfg)                      # the change feed grows with every look, as on the page
    return len(changes.since_seen(cfg))


def op_overview(args):
    cfg = _cfg(args["project"])
    state = scan.scan(cfg)
    if config.is_project_mode(cfg):
        return {**_project_overview(cfg, state), "github": github_link.github_status(cfg)}
    per_state = {}
    for it in state["items"]:
        per_state[it["state"]] = per_state.get(it["state"], 0) + 1
    ingame = [i for i in state["items"] if i["state"] == "ingame"]
    return {
        "project": cfg["id"], "name": cfg.get("name"), "art_root": cfg["art_root"], "engine_root": cfg.get("engine_root"),
        "models": len(state["items"]), "per_state": per_state,
        "ingame_used": sum(1 for i in ingame if i["usage"] == "used"),
        "ingame_unused": sum(1 for i in ingame if i["usage"] == "unused"),
        "out_of_sync": sum(1 for i in ingame if i["sync"] not in ("same", None)),
        "engine_only": len(state["engine_only"]),
        "placeholders": len(state["placeholders"]),
        "placeholders_in_use": sum(1 for p in state["placeholders"] if p["usage"] == "used"),
        "layout_issues": len(state["layout_issues"]), "unsorted": len(state["unsorted"]),
        "engine_unreachable": state["engine_unreachable"],
        "open_tasks": sum(1 for t in tasks.load(cfg) if t["status"] != "done"),
        "engine_scanned": state["engine_scanned"],
        "github": github_link.github_status(cfg),
    }


def op_search(args):
    cfg = _cfg(args["project"])
    q = args["query"].lower()
    limit = int(args.get("limit") or 30)
    state = scan.scan(cfg)
    if config.is_project_mode(cfg):
        return [_catalog_summary(e) for e in catalog.query(state["catalog"], search=q, limit=limit)["assets"]]
    hits = []
    for group, entries in (("desktop", state["items"]), ("engine_only", state["engine_only"]), ("placeholder", state["placeholders"])):
        for e in entries:
            hay = (e["id"] + " " + e["name"] + " " + (e.get("engine_path") or "")).lower()
            if q in hay:
                hits.append({"group": group, **_item_summary(e)})
    return hits[:limit]


def op_asset(args):
    cfg = _cfg(args["project"])
    state = scan.scan(cfg)
    wanted = _asset_id(cfg, args, state)
    if config.is_project_mode(cfg):
        entry = next((e for e in state["catalog"]["assets"] if e["id"] == wanted), None)
        if entry is None:
            entry = next((e for e in state["placeholders"] if e["id"] == wanted), None)
        if entry is None:
            raise NotFound(f"no asset {wanted!r}; search for it")
        out = dict(entry)
        for key in ("used_by", "uses"):
            rows = entry.get(key) or []
            out[key], out[key + "_count"] = rows[:LIST_CAP], len(rows)
        out["tasks"] = [t for t in tasks.load(cfg) if t.get("asset") == entry["id"]]
        return out
    for entries in (state["items"], state["engine_only"], state["placeholders"]):
        for e in entries:
            if e["id"] == wanted:
                out = dict(e)
                out["tasks"] = [t for t in tasks.load(cfg) if t.get("asset") == e["id"]]
                return out
    raise NotFound(f"no asset {wanted!r}; search for it")


def op_unused(args):
    cfg = _cfg(args["project"])
    state = scan.scan(cfg)
    if config.is_project_mode(cfg):
        assets = state["catalog"]["assets"]
        unref, unref_total = _page([_catalog_summary(a) for a in assets if a["usage"] == "unreferenced"], args)
        by_name, by_name_total = _page([_catalog_summary(a) for a in assets if a["usage"] == "by_name"], args)
        return {"unreferenced": unref, "unreferenced_total": unref_total, "by_name": by_name,
                "by_name_total": by_name_total, "unknown": sum(1 for a in assets if a["usage"] == "unknown")}
    return {"desktop_ingame": [_item_summary(i) for i in state["items"] if i["state"] == "ingame" and i["usage"] == "unused"],
            "engine_only": [_item_summary(i) for i in state["engine_only"] if i["usage"] == "unused"]}


def op_placeholders(args):
    state = scan.scan(_cfg(args["project"]))
    return [{"id": p["id"], "name": p["name"], "usage": p["usage"], "used_by": [r["path"] for r in p["used_by"]], "note": p["note"]}
            for p in state["placeholders"]]


def op_layout_issues(args):
    cfg = _cfg(args["project"])
    issues = scan.scan(cfg)["layout_issues"]
    if config.is_project_mode(cfg):
        rows, total = _page(issues, args)
        return {"total": total, "offset": max(0, int(args.get("offset") or 0)), "issues": rows}
    return issues


def op_graph_neighbors(args):
    cfg = _cfg(args["project"])
    dump = engines.dump(cfg)
    g = graph.build(cfg, dump, scan.scan(cfg)["items"])
    nodes = {n["id"]: n for n in g["nodes"]}
    start = _graph_start(engines.of(cfg), nodes, args["path"])
    hops = max(1, min(int(args.get("hops") or 1), 3))
    seen, frontier = {start}, {start}
    edges_out = []
    for _ in range(hops):
        nxt = set()
        for e in g["edges"]:
            if e["from"] in frontier or e["to"] in frontier:
                edges_out.append(e)
                nxt.update((e["from"], e["to"]))
        frontier = nxt - seen
        seen |= nxt
    uniq = list({(e["from"], e["to"]): e for e in edges_out}.values())
    kept = uniq[:GRAPH_CAP]
    shown = {start} | {e["from"] for e in kept} | {e["to"] for e in kept}
    return {"start": nodes[start], "nodes": [nodes[n] for n in sorted(shown)], "edges": kept,
            "edges_total": len(uniq), "truncated": len(uniq) > len(kept)}


def _graph_start(adapter, nodes, given):
    """The graph node a caller means: an engine:... id, an Assets/... path or a path relative to the content root
    (exact, case-insensitive), else a file name that only one node has. Several nodes with that name: refused with
    the candidates, never a guess."""
    wanted = given.replace("\\", "/")
    if wanted.startswith("engine:"):
        wanted = wanted[len("engine:"):]
    elif wanted.startswith(adapter.prefix):
        wanted = wanted[len(adapter.prefix):]
    by_lower = {nid.lower(): nid for nid in nodes}
    if wanted.lower() in by_lower:
        return by_lower[wanted.lower()]
    name = os.path.basename(wanted).lower()
    same_name = sorted(nid for nid in nodes if os.path.basename(nid).lower() == name)
    if len(same_name) == 1:
        return same_name[0]
    if same_name:
        raise ValueError(f"several assets are named {os.path.basename(wanted)!r}: "
                         f"{', '.join(adapter.prefix + n for n in same_name[:10])}; give the path")
    raise NotFound(f"no graph node for {given!r}")


def op_scene_inventory(args):
    return scenes.inventory(_cfg(args["project"]), args.get("scene"))


def op_layout_settings(args):
    cfg = _cfg(args["project"])
    dump = engines.dump(cfg)
    if args.get("enabled") is None and not args.get("allow_kind"):
        return layout.status(cfg, dump)
    return layout.settings(cfg, dump, enable=args.get("enabled"), allow_kind=args.get("allow_kind"),
                           allow_folder=args.get("allow_folder"))


def op_catalog(args):
    cfg = _cfg(args["project"])
    return catalog.query(scan.scan(cfg)["catalog"] if config.is_project_mode(cfg)
                         else catalog.build(cfg, engines.dump(cfg)),
                         kind=args.get("kind"), usage=args.get("usage"), folder=args.get("folder"),
                         search=args.get("search"), offset=args.get("offset") or 0, limit=args.get("limit") or 100)


def _asset_id(cfg, args, state):
    """The id an asset call names: `id`, or the item whose engine copy is at `engine_path` / has `guid`."""
    if args.get("id"):
        return args["id"]
    rel = args.get("engine_path")
    if not rel and args.get("guid"):
        entry = ((engines.dump(cfg) or {}).get("assets") or {}).get(args["guid"])
        if not entry:
            raise NotFound(f"no engine asset with guid {args['guid']!r}")
        rel = entry["path"]
    if not rel:
        raise ValueError("asset needs id, engine_path or guid")
    adapter = engines.of(cfg)
    rel = rel.replace("\\", "/")
    if adapter.is_engine_path(rel):
        path = adapter.from_engine_path(cfg, rel)
    else:                                    # a path relative to the content root (as the dump writes it)
        path = os.path.normpath(os.path.join(adapter.content_root(cfg), rel))
    path = os.path.normcase(os.path.normpath(path))
    root = adapter.content_root(cfg)
    for e in (state.get("catalog") or {}).get("assets", []):
        if os.path.normcase(os.path.normpath(os.path.join(root, e["path"][len(adapter.prefix):]))) == path:
            return e["id"]
    for entries in (state["items"], state["engine_only"], state["placeholders"]):
        for e in entries:
            if e.get("engine_path") and os.path.normcase(os.path.normpath(e["engine_path"])) == path:
                return e["id"]
    raise NotFound(f"no asset at {rel!r}")


def catalog_counts(cfg):
    """The catalog's counts for a freshly connected project (what setup prints): {"kinds", "usage", "hidden"}."""
    return catalog.build(cfg, engines.dump(cfg))["counts"]
