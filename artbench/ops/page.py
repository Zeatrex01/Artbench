"""What the page's own routes (/api/*) need, in the shapes the page reads. These are not operations: no MCP tool and
no command line reach them (programs use /api/v1). The server only carries requests here; it holds the project lock
around the calls that scan or write, as before."""
from .. import actions, asset_meta, catalog, changes, config, deploy, engines, graph, live, marks, package, scan, store, tasks, thumbs
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
             "mode": c.get("mode"), "github_account": c.get("github_account")} for c in config.projects()]


def state(cfg):
    """The state the page polls. The change feed grows with every look; in project mode the catalog rows are light
    (counts, not lists) and the answer carries what came after the person's last Mark as seen."""
    changes.update(cfg)
    data = scan.scan(cfg)
    if data.get("mode") == "project":
        data["catalog"] = catalog.light(data["catalog"])
        data["since_seen"] = changes.since_seen(cfg)
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


def task_list(cfg):
    return tasks.load(cfg)


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
    """The board's one route: op add (the default), update or delete."""
    op = body.get("op", "add")
    if op == "add":
        return tasks.add(cfg, body["title"], body.get("asset"), body.get("note", ""), body.get("status", "todo"),
                         body.get("priority") or "normal")
    if op == "update":
        return tasks.update(cfg, body["id"], **{k: body.get(k) for k in ("title", "status", "asset", "note", "priority") if k in body})
    if op == "delete":
        return {"ok": tasks.delete(cfg, body["id"])}
    raise ValueError("unknown op")
