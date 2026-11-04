"""Operations on the person's own records: tasks, notes, moves between states, history, the change feed."""
from .. import actions, changes, store, tasks
from .common import _cfg, _desktop_item


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
