"""Operations that move files between the art folder and the engine, and what they read first: plans, sends,
pulls, model snapshots and diffs, previews, a forced refresh."""
from .. import asset_meta, deploy, engines, package, thumbs
from .common import _cfg, _desktop_item, _engine_only_entry
from .assets import op_overview


def op_send_plan(args):
    cfg = _cfg(args["project"])
    return deploy.plan(cfg, _desktop_item(cfg, args["id"]))


def op_send(args):
    cfg = _cfg(args["project"])
    return deploy.send(cfg, _desktop_item(cfg, args["id"]), bool(args.get("accept_warnings")), bool(args.get("force")), args.get("files"),
                       args.get("expect"))


def op_pull_plan(args):
    cfg = _cfg(args["project"])
    return package.plan_pull(cfg, _desktop_item(cfg, args["id"]))


def op_pull(args):
    cfg = _cfg(args["project"])
    return package.pull(cfg, _desktop_item(cfg, args["id"]), files=args.get("files"), force=bool(args.get("force")), expect=args.get("expect"))


def op_bring_in_plan(args):
    cfg = _cfg(args["project"])
    return package.plan_bring_in(cfg, _engine_only_entry(cfg, args["id"]), args.get("category") or None)


def op_bring_in(args):
    cfg = _cfg(args["project"])
    return package.bring_in(cfg, _engine_only_entry(cfg, args["id"]), args.get("category"))


def op_metadata_snapshot(args):
    cfg = _cfg(args["project"])
    state, snap = asset_meta.snapshot_status(cfg, _desktop_item(cfg, args["id"])["path"])
    return {"state": state, "snapshot": snap}


def op_metadata_diff(args):
    cfg = _cfg(args["project"])
    return asset_meta.compare(cfg, _desktop_item(cfg, args["id"]))


def op_refresh(args):
    cfg = _cfg(args["project"])
    engines.dump(cfg, force=True)
    return op_overview(args)


def op_preview(args):
    cfg = _cfg(args["project"])
    state, png = thumbs.status(cfg, _desktop_item(cfg, args["id"])["path"])
    return {"state": state, "path": png}
