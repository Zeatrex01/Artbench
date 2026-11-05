"""Operations on the person's own records: tasks, notes, moves between states, history, the change feed."""
import os

from .. import actions, asset_meta, changes, marks, scan, store, tasks
from .common import _cfg, _desktop_item, _page


def op_tasks(args):
    """The board in board order; status "open" is to do and doing. Empty fields are left out of each row."""
    out = tasks.load(_cfg(args["project"]))
    status = args.get("status")
    if status == "open":
        out = [t for t in out if t["status"] != "done"]
    elif status:
        out = [t for t in out if t["status"] == status]
    if args.get("assets"):
        wanted = set(args["assets"])
        out = [t for t in out if t.get("asset") in wanted]
    return [{k: v for k, v in t.items() if v not in (None, "")} for t in out[:int(args.get("limit") or 50)]]


def op_task_add(args):
    return tasks.add(_cfg(args["project"]), args["title"], args.get("asset"), args.get("note", ""),
                     priority=args.get("priority") or "normal")


def op_task_update(args):
    fields = {k: args.get(k) for k in ("status", "title", "note", "asset", "priority") if k in args}
    return tasks.update(_cfg(args["project"]), args["id"], **fields)


def op_mark(args):
    return marks.set_marks(_cfg(args["project"]), args["ids"], favorite=args.get("favorite"),
                           revision=args.get("revision"), note=args.get("note"),
                           add_tags=args.get("tags_add"), remove_tags=args.get("tags_remove"))


def op_marks(args):
    """The marked assets, those waiting for a revision first; tag narrows to the assets carrying it."""
    rows = []
    tag = marks.tag_name(args["tag"]) if args.get("tag") else None
    for asset, e in marks.load(_cfg(args["project"])).items():
        if args.get("filter") and not e.get(args["filter"]):
            continue
        if tag and tag not in (e.get("tags") or []):
            continue
        row = {"id": asset}
        if e.get("favorite"):
            row["favorite"] = True
        if e.get("revision"):
            row.update(revision=True, note=e["revision"]["note"])
        if e.get("tags"):
            row["tags"] = e["tags"]
        rows.append(row)
    rows.sort(key=lambda r: (not r.get("revision"), r["id"].lower()))
    return rows[:int(args.get("limit") or 50)]


def op_note(args):
    actions.set_meta(_cfg(args["project"]), args["id"], note=args["note"])
    return {"ok": True}


def op_move(args):
    cfg = _cfg(args["project"])
    return {"ok": True, "path": actions.set_state(cfg, _desktop_item(cfg, args["id"]), args["state"])}


def op_history(args):
    return store.history(_cfg(args["project"]), int(args.get("limit") or 50))


def op_changes(args):
    cfg = _cfg(args["project"])
    changes.update(cfg)
    if args.get("mark_seen"):
        return changes.mark_seen(cfg)
    if args.get("since_seen"):
        return changes.since_seen(cfg)[:int(args.get("limit") or 100)]
    return changes.recent(cfg, int(args.get("limit") or 100))


def op_meta(args):
    actions.set_meta(_cfg(args["project"]), args["id"], **{k: args[k] for k in actions.META_FIELDS if k in args})
    return {"ok": True}


def op_asset_history(args):
    """One asset's history lines and file changes, newest first, paged (20 unless limit says otherwise)."""
    cfg, wanted = _cfg(args["project"]), args["id"]
    keys, tails = {wanted}, set()
    if wanted.startswith("engine:"):
        tails.add(wanted[len("engine:"):])
    else:                                                    # an art-folder item: its file, and its engine copy
        keys.add("art:" + wanted)
        tails.add(wanted)
        item = next((i for i in scan.scan(cfg).get("items") or [] if i["id"] == wanted), None)
        if item and item.get("engine_path") and cfg.get("engine_root"):
            rel = os.path.relpath(item["engine_path"], cfg["engine_root"]).replace("\\", "/")
            keys.add("engine:" + rel)
    page, total = _page(changes.timeline(cfg, keys, tails), {**args, "limit": args.get("limit") or 20})
    return {"total": total, "entries": page}


def op_performance_settings(args):
    """How much background Blender work the project asks for; previews and model_stats change it."""
    cfg = _cfg(args["project"])
    if args.get("previews") is None and args.get("model_stats") is None:
        return asset_meta.performance(cfg)
    return asset_meta.set_performance(cfg, previews=args.get("previews"), model_stats=args.get("model_stats"))
