"""What the page's own routes (/api/*) need, in the shapes the page reads. These are not operations: no MCP tool and
no command line reach them (programs use /api/v1). The server only carries requests here; it holds the project lock
around the calls that scan or write, as before."""
import os

from .. import actions, asset_meta, blender_link, catalog, changes, config, deploy, engines, graph, live, marks, mcp_link, package, scan, store, tasks, thumbs
from ..errors import NotFound

ENGINE_REPORT_SCHEMA = live.SCHEMA


def project(pid):
    for cfg in config.projects():
        if cfg.get("id") == pid and "error" not in cfg:
            return cfg
    raise NotFound(f"project {pid}")


def find(cfg, item_id):
    for it in scan.scan(cfg)["items"]:
        if it["id"] == item_id:
            return it
    raise NotFound(f"no item {item_id!r}")


def projects():
    return [{"id": c.get("id"), "name": c.get("name", c.get("id")), "error": c.get("error"), "config_path": c.get("config_path"),
             "mode": c.get("mode"), "github_account": c.get("github_account"),
             **({} if c.get("error") else asset_meta.performance(c))} for c in config.projects()]


def state(cfg):
    """The state the page polls. The change feed grows with every look; in project mode the catalog rows are light
    (counts, not lists) and the answer carries what came after the person's last Mark as seen."""
    changes.update(cfg)
    data = scan.scan(cfg)
    if data.get("mode") == "project":
        data["catalog"] = catalog.light(data["catalog"])
        data["since_seen"] = changes.since_seen(cfg)
    data["ai_activity"] = mcp_link.recent(15)                # the page's AI line: what the AI did lately
    data["marks"] = marks.load(cfg)                          # stars and revision flags on rows, cards and the Marked view
    return data


def refresh(cfg):
    """Rebuilds the engine dump now (the page's refresh button), then the fresh state."""
    engines.dump(cfg, force=True)
    return state(cfg)


def recent_changes(cfg, limit):
    return changes.recent(cfg, limit)


def send_plan(cfg, item_id):
    return deploy.plan(cfg, find(cfg, item_id))


def meta_snapshot(cfg, path):
    """(state, snapshot): "ready" | "pending" | "failed" | "none"."""
    return asset_meta.snapshot_status(cfg, path)


def meta_diff(cfg, item_id):
    return asset_meta.compare(cfg, find(cfg, item_id))


def pull_plan(cfg, item_id):
    return package.plan_pull(cfg, find(cfg, item_id))


def reference_graph(cfg):
    return graph.build(cfg, engines.dump(cfg), scan.scan(cfg)["items"])


def pulse(cfg):
    """The page's light look between rescans: the board (with its live lines) and what the AI did. Reads a few small
    files; never scans the project."""
    return {"tasks": task_list(cfg), "ai_activity": mcp_link.recent(15)}


def task_list(cfg, archived=False):
    """The board; its tasks tied to an asset carry `live` (see _live) for the detailed cards. The AI's `tasks` op
    has none of it."""
    out = tasks.load(cfg, archived=archived)
    return out if archived else _live(cfg, out)


def _live(cfg, board):
    """live on each task tied to an asset: changed {time, what} (its newest file change), blender (the open .blend's
    name, when it is this asset's: the file itself, a model bound to it, or a model of the same name), revision (its
    revision note)."""
    ids = {t["asset"] for t in board if t.get("asset")}
    if not ids:
        return board
    latest = changes.latest_for(cfg, ids)
    session = blender_link.status()
    open_file = session.get("file") if session.get("open") and session.get("file") else None
    stem = os.path.splitext(os.path.basename(open_file))[0].lower() if open_file else None
    models = tuple(e.lower() for e in cfg.get("model_extensions") or ())
    revisions = marks.load(cfg)
    for t in board:
        asset = t.get("asset")
        if not asset:
            continue
        live, name = {}, asset.rsplit("/", 1)[-1]
        if asset in latest:
            live["changed"] = latest[asset]
        if open_file and (asset == session.get("asset") or asset in (session.get("models") or [])
                          or (name.lower().endswith(models) and os.path.splitext(name)[0].lower() == stem)):
            live["blender"] = os.path.basename(open_file)
        revision = (revisions.get(asset) or {}).get("revision")
        if revision:
            live["revision"] = revision.get("note") or ""
        if live:
            t["live"] = live
    return board


def thumb(cfg, path):
    """(state, file, content type): the preview file to serve when the state is "ready"."""
    st, file = thumbs.status(cfg, path)
    return st, file, (thumbs.content_type(file) if file else None)


def history(cfg):
    return store.history(cfg)


def move(cfg, item_id, new_state):
    return actions.set_state(cfg, find(cfg, item_id), new_state)


def set_meta(cfg, item_id, fields):
    actions.set_meta(cfg, item_id, **{k: fields.get(k) for k in actions.META_FIELDS if k in fields})


def reveal(path):
    actions.reveal(path)


def open_path(path):
    actions.open_file(path)


def send(cfg, item_id, accept_warnings, force, files, expect):
    return deploy.send(cfg, find(cfg, item_id), accept_warnings, force, files, expect)


def pull(cfg, item_id, force, files, expect):
    return package.pull(cfg, find(cfg, item_id), files=files, force=force, expect=expect)


def mark_seen(cfg):
    return changes.mark_seen(cfg)


def task(cfg, body):
    """The board's one route: op add (the default), update, delete, archive (a finished task), archive_done (every
    finished task) or restore (an archived one)."""
    op = body.get("op", "add")
    if op == "add":
        return tasks.add(cfg, body["title"], body.get("asset"), body.get("note", ""), body.get("status", "todo"),
                         body.get("priority") or "normal")
    if op == "update":
        return tasks.update(cfg, body["id"], **{k: body.get(k) for k in ("title", "status", "asset", "note", "priority") if k in body})
    if op == "delete":
        return {"ok": tasks.delete(cfg, body["id"])}
    if op == "archive":
        return {"archived": tasks.archive(cfg, [body["id"]])}
    if op == "archive_done":
        return {"archived": tasks.archive_done(cfg)}
    if op == "restore":
        return tasks.restore(cfg, body["id"])
    raise ValueError("unknown op")
