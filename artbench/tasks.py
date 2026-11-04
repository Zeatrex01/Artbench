"""Task list per project (tasks.json next to the art root): things the artist wants to do, optionally tied to an
asset id. Tasks are not project files, so they may be deleted; every change is one history line."""
import time
import uuid

from . import store
from .errors import NotFound

STATUSES = ("todo", "doing", "done")
PRIORITIES = ("high", "normal", "low")
EDITABLE = ("title", "status", "asset", "note", "priority")


def _priority(value):
    if value not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}, not {value!r}")
    return value


def load(cfg):
    """Tasks in board order: by status (to do, doing, done), then priority (high first), then oldest first. Tasks
    saved before priorities existed read as normal."""
    out = store.tasks(cfg)
    for t in out:
        t.setdefault("priority", "normal")
    order = {s: i for i, s in enumerate(STATUSES)}
    rank = {p: i for i, p in enumerate(PRIORITIES)}
    return sorted(out, key=lambda t: (order.get(t.get("status"), 0), rank.get(t["priority"], 1), t.get("created") or 0))


def add(cfg, title, asset=None, note="", status="todo", priority="normal"):
    title = (title or "").strip()
    if not title:
        raise ValueError("task title is empty")
    now = time.time()
    task = {"id": uuid.uuid4().hex[:10], "title": title, "status": status if status in STATUSES else "todo",
            "priority": _priority(priority or "normal"),
            "asset": asset or None, "note": note or "", "created": now, "updated": now, "done": None}
    with store.locked(cfg):
        tasks = store.tasks(cfg)
        tasks.append(task)
        store.save_tasks(cfg, tasks)
        store.log(cfg, "TASK ADD", task["id"], task["title"], asset or "")
    return task


def update(cfg, task_id, **fields):
    if fields.get("priority") is not None:
        _priority(fields["priority"])
    with store.locked(cfg):
        tasks = store.tasks(cfg)
        task = _find(tasks, task_id)
        task.setdefault("priority", "normal")
        for key in EDITABLE:
            if fields.get(key) is not None:
                task[key] = fields[key]
        task["asset"] = task["asset"] or None             # "" clears the asset link
        if task["status"] not in STATUSES:
            task["status"] = "todo"
        task["updated"] = time.time()
        task["done"] = task["updated"] if task["status"] == "done" else None
        store.save_tasks(cfg, tasks)
        store.log(cfg, "TASK " + task["status"].upper(), task["id"], task["title"])
    return task


def delete(cfg, task_id):
    with store.locked(cfg):
        tasks = store.tasks(cfg)
        task = _find(tasks, task_id)
        tasks.remove(task)
        store.save_tasks(cfg, tasks)
        store.log(cfg, "TASK DELETE", task_id, task["title"])
    return True


def _find(tasks, task_id):
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise NotFound(f"task {task_id}")
