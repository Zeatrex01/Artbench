"""Shared by the operations: the error type, the operation record, argument schemas, paging and lookups."""
from .. import catalog, config, scan
from ..errors import NotFound


WRITE_OPS = {"task_add", "task_update", "mark", "export", "checks_settings", "note", "meta", "move", "send", "pull", "bring_in", "engine_report", "doctor", "blender_report", "blender_notes_send",
             "open_in_blender", "layout_settings"}


BRIDGE_ONLY = {"engine_report", "blender_report", "blender_notes_send"}   # the bridges' doors (HTTP), not an agent's (MCP, command line)


PAGE_ONLY = {"export_plan", "export"}     # the page's and the command line's: an AI has no folder of the person's to fill


# Operations on the art folder: a project-mode project (the engine project alone) has none of these.
ART_ONLY = {"note", "move", "history", "send_plan", "send", "pull_plan", "pull", "bring_in_plan", "bring_in", "metadata_snapshot", "metadata_diff",
            "meta", "preview"}


CODES = ("bad_request", "not_found", "needs_force", "warnings", "busy", "outside_root", "conflict", "unavailable",
         "wrong_mode", "internal")


LIST_CAP = 50                         # rows of used_by / uses an asset answer carries; the counts say how many exist


GRAPH_CAP = 200                       # edges a graph_neighbors answer carries; edges_total says how many exist


_PAGE = {"offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 25}}   # small pages: an AI pays per row


def _page(rows, args):
    """(rows[offset:offset+limit], total) with limit capped like the catalog's."""
    offset = max(0, int(args.get("offset") or 0))
    limit = max(1, min(int(args.get("limit") or 25), catalog.MAX_PAGE))
    return rows[offset:offset + limit], len(rows)


class OpError(Exception):
    """An operation failure with a code from CODES; `detail` carries structured context when there is any."""

    def __init__(self, code, message, detail=None):
        super().__init__(message)
        self.code, self.message, self.detail = code, message, detail


class Op:
    def __init__(self, name, description, params, fn, write=False, agents=True, modes=("art", "project")):
        self.name, self.description, self.params, self.fn, self.write = name, description, params, fn, write
        self.agents = agents                 # offered over MCP and the command line
        self.modes = modes                   # the project modes it serves


def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


_P = {"project": {"type": "string"}}            # the id from artbench_projects (said once there)


def _cfg(project):
    for cfg in config.projects():
        if cfg.get("id") == project and "error" not in cfg:
            return cfg
    raise NotFound(f"unknown project {project!r}; list the projects")


def _item_summary(item):
    keys = ("id", "name", "state", "category", "sync", "usage", "note")
    out = {k: item.get(k) for k in keys}
    out["used_by_count"] = len(item.get("used_by") or [])
    return out


def _engine_only_entry(cfg, entry_id):
    entry = next((e for e in scan.scan(cfg)["engine_only"] if e["id"] == entry_id), None)
    if not entry:
        raise NotFound(f"no engine-only model {entry_id!r} (it may already have a desktop copy)")
    return entry


def _desktop_item(cfg, item_id):
    item = next((i for i in scan.scan(cfg)["items"] if i["id"] == item_id), None)
    if not item:
        raise NotFound(f"no desktop model {item_id!r}")
    return item
