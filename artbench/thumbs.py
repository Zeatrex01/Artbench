"""Previews: models are rendered by background Blender through blender_jobs; textures in a format the browser shows
(PNG, JPEG) and no larger than DIRECT_MAX are their own preview; other image formats, and larger images, are scaled
down by the same background Blender. Rendered previews are cached by content hash under Artbench/.cache/thumbs,
so a file is rendered once per version; the page asks again until the file exists. Only files inside the project's
own folders (the art folder, the engine project) get a preview."""
import os

from . import blender_jobs, engines

RENDER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thumb_render.py")
SIZE = 256
DIRECT_MAX = 2 << 20                  # bytes: a PNG or JPEG up to this size is served as it is
DIRECT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
blender = blender_jobs.blender


def thumb_path(path):
    return blender_jobs.cache_path("thumbs", path, "png")


def content_type(path):
    """The type a preview file is served as: the image's own for a direct one, PNG for a rendered one."""
    return DIRECT.get(os.path.splitext(path)[1].lower(), "image/png")


def _inside_project(cfg, path):
    roots = [cfg.get("art_root"), cfg.get("engine_root")]
    try:
        roots.append(engines.of(cfg).project_root(cfg))
    except Exception:  # noqa: BLE001  (an engine the adapter cannot read: the other roots still count)
        pass
    target = os.path.normcase(os.path.realpath(path))
    for root in filter(None, roots):
        base = os.path.normcase(os.path.realpath(root))
        if target.startswith(base.rstrip(os.sep) + os.sep):
            return True
    return False


def status(cfg, path):
    """("ready", file) | ("pending", None) | ("failed", None) | ("none", None)."""
    if not path or not os.path.isfile(path) or not _inside_project(cfg, path):
        return "none", None
    if os.path.splitext(path)[1].lower() in DIRECT and os.path.getsize(path) <= DIRECT_MAX:
        return "ready", path
    if cfg.get("previews") == "off":
        return "none", None              # model previews turned off: no Blender, the page shows the placeholder tile
    png = thumb_path(path)
    state = blender_jobs.request(cfg, RENDER_SCRIPT, path, png, (str(SIZE),), blender_jobs.PRIORITY_THUMB)
    if state == "none":
        return "failed", None            # Blender missing: the page shows the placeholder tile, as before
    return state, (png if state == "ready" else None)
