"""Send a desktop model to the engine project: the engine copy is backed up to the archive, the file is written
over it (its .meta stays, so Unity keeps every import setting and reference), and a model that came from the Outbox
moves to the in-game folder on the desktop. Before writing, both FBX files are fingerprinted by background Blender
and differences that break Unity references (object names, material slots, bones, animation takes) are reported as
warnings; the send goes ahead only when the caller accepts them. The bridge rule (sync.py) applies: when the engine
copy changed since the last agreed state, the send needs an explicit force, and the old copy is archived either way."""
from . import package


def plan(cfg, item):
    """The package send plan (package.plan_send): top-level fields describe the model, `files` every package file."""
    return package.plan_send(cfg, item)


def send(cfg, item, accept_warnings=False, force=False, files=None, expect=None):
    """Sends the package (package.send): default selection unless `files` names the file ids to send."""
    return package.send(cfg, item, files=files, accept_warnings=accept_warnings, force=force, expect=expect)
