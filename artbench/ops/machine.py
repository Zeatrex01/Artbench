"""Operations about this machine and its bridges: engine reports, the doctor, Blender's presence, opening a model."""
import os

from .. import blender_link, config, doctor, engines, live, scan
from ..errors import NotFound
from .common import _cfg, _desktop_item


def op_engine_report(args):
    return live.accept(_cfg(args["project"]), args["report"])


def op_doctor(args):
    return doctor.run(_cfg(args["project"]))


def op_engine_status(args):
    return live.status(_cfg(args["project"]))


def op_open_in_blender(args):
    cfg = _cfg(args["project"])
    if config.is_project_mode(cfg):
        state = scan.scan(cfg)
        entry = next((a for a in state["catalog"]["assets"] if a["id"] == args["id"]), None)
        if entry is None:
            raise NotFound(f"asset {args['id']}")
        if entry["kind"] != "model":
            raise ValueError(f"only models open in Blender; {entry['name']} is a {entry['kind']}")
        adapter = engines.of(cfg)
        path = os.path.join(adapter.content_root(cfg), *entry["path"][len(adapter.prefix):].split("/"))
    else:
        item = _desktop_item(cfg, args["id"])
        path = (item.get("blend") or {}).get("path") or item["path"]
    return blender_link.open_file(cfg, path)


def op_blender_status(_):
    return blender_link.status()


def op_blender_notes_send(args):
    return blender_link.send_notes(args["file"], args["notes"])


def op_blender_notes(args):
    return blender_link.notes(_cfg(args["project"]))


def op_blender_report(args):
    return blender_link.report(args["file"], args["blender"], args["pid"], bool(args.get("closing")))
