"""Project configs: one `art_inventory.json` per project (kept in the project's art folder), listed in the tool's
`projects.json`. Relative paths in a config are resolved from the folder the config sits in."""
import json
import os

from . import __author__, __version__

TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION, AUTHOR = __version__, __author__           # the release and the signature, for the transports
REGISTRY = os.path.join(TOOL_ROOT, "projects.json")
CONFIG_NAME = "art_inventory.json"
PORT = 8765                                         # the page server: http://127.0.0.1:8765/
DATA_ROOT = os.path.join(TOOL_ROOT, "projects")     # project-mode configs and their files: projects/<id>/
# Asset kinds a project-mode catalog lists; the rest (scripts, data assets, other) are counted, not listed.
CATALOG_KINDS = ["model", "texture", "material", "prefab", "scene", "animator", "clip", "shader", "audio", "font",
                 "atlas", "mesh"]

DEFAULTS = {
    "engine": "unity",
    "model_extensions": [".fbx", ".glb", ".gltf", ".obj"],
    "texture_extensions": [".png", ".tga", ".jpg", ".jpeg", ".psd", ".exr"],
    "package_extensions": [".png", ".tga", ".jpg", ".jpeg"],    # textures that travel with a model; the rest are sources
    "engine_layout": "follow",                                   # "per_model": model + textures in one engine folder
    "engine_texture_targets": {},                                # category -> engine folder for new textures (follow)
    "bridge_fresh_seconds": 600,                                # a live scene report counts this long
    "report_limits": {},                                        # over live.DEFAULT_LIMITS: scenes, nodes, uses
    "blend_extensions": [".blend"],
    "states": {"ingame": "FBX", "outbox": "Outbox", "stock": "Stock", "archive": "../_Archive"},
    "blend_root": "Blend",
    "textures_root": "Textures",
    "ignore": ["__pycache__", ".git", "Textures", "textures"],
    "engine_ignore": ["Third_Party", "Library", "Plugins", "Game VFX Mega Pack"],
}


def is_project_mode(cfg):
    """True for a project that names only the engine project (no art folder)."""
    return (cfg or {}).get("mode") == "project"


def registry():
    if not os.path.exists(REGISTRY):
        return []
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f).get("projects", [])


def load(path):
    path = os.path.abspath(path)
    base = os.path.dirname(path)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULTS)
    merged.update(cfg)
    merged["states"] = {**DEFAULTS["states"], **cfg.get("states", {})}
    merged["config_path"] = path
    merged["id"] = cfg.get("id") or os.path.splitext(os.path.basename(path))[0]

    def resolve(p):
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))

    merged["mode"] = "project" if cfg.get("mode") == "project" else "art"
    merged["catalog_kinds"] = list(cfg.get("catalog_kinds") or CATALOG_KINDS)
    merged["engine_root"] = resolve(cfg["engine_root"]) if cfg.get("engine_root") else None
    if merged["mode"] == "project":
        # No art folder: the config, the dump and every tracking file live in the config's own folder, outside the
        # engine project.
        merged["art_root"] = None
        merged["data_dir"] = base
        merged["states"], merged["state_dirs"], merged["blend_dir"] = {}, {}, None
    else:
        merged["art_root"] = resolve(cfg.get("art_root", "."))
        merged["data_dir"] = merged["art_root"]
        merged["state_dirs"] = {k: os.path.normpath(os.path.join(merged["art_root"], v)) for k, v in merged["states"].items()}
        merged["blend_dir"] = os.path.normpath(os.path.join(merged["art_root"], merged["blend_root"]))
    merged["inventory_path"] = os.path.join(merged["data_dir"], "inventory.json")
    merged["history_path"] = os.path.join(merged["data_dir"], "inventory_history.log")
    return merged


def load_quiet(path):
    """load() that returns {"error": ...} instead of raising (for registry listings)."""
    try:
        return load(path)
    except (OSError, ValueError, KeyError) as e:
        return {"id": os.path.basename(path), "error": str(e), "config_path": path}


def projects():
    out = []
    for p in registry():
        try:
            out.append(load(p))
        except (OSError, ValueError, KeyError) as e:
            out.append({"id": os.path.basename(p), "error": str(e), "config_path": p})
    return out
