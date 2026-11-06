"""Godot 4: a project is a folder with project.godot, asset paths are "res://...", every imported asset has an .import
file beside it (its uid and import settings) and scripts a .uid file, and the dump is read from the project's text
files (godot_dump.py) without Godot running. The content root is the project folder itself."""
import os
import re
import time

from .. import godot_dump, store
from .base import DUMP_FILE, DUMP_MAX_AGE, EngineAdapter

NO_COMPRESSION = (0, 3)                  # compress/mode: lossless and VRAM uncompressed are not compressed for the GPU


class GodotAdapter(EngineAdapter):
    name = "godot"
    prefix = "res://"
    id_kind = "uid"
    layout_defaults = []                 # Godot has no folder convention: Layout learns the project's own

    def detect(self, path):
        p = os.path.normpath(path)
        while True:
            if os.path.isfile(os.path.join(p, "project.godot")):
                return {"project_root": p, "content_root": p}
            parent = os.path.dirname(p)
            if parent == p:
                return None
            p = parent

    def content_root(self, cfg):
        """config engine_assets_root, else the nearest project.godot ancestor of engine_root (the project folder)."""
        if cfg.get("engine_assets_root"):
            return cfg["engine_assets_root"]
        root = cfg.get("engine_root")
        found = self.detect(root) if root else None
        return found["content_root"] if found else root

    def project_root(self, cfg):
        return self.content_root(cfg)

    def normalize_engine_path(self, value):
        if not isinstance(value, str):
            raise ValueError("path missing")
        path = value.replace("\\", "/")
        parts = path[len(self.prefix):].split("/") if path.startswith(self.prefix) else []
        if not parts or ".." in parts or "" in parts or any(":" in part for part in parts):
            raise ValueError(f"{value!r} is not a path inside res://")
        return path

    def sidecars(self, path):
        return [path + ".import", path + ".uid"]

    def import_settings(self, path):
        """The importer's settings in the asset's .import file: a texture's {max_size (process/size_limit), compressed
        (compress/mode), mipmaps}, a model's importer only. Read only; no .import file gives {}."""
        try:
            with open(path + ".import", encoding="utf-8", errors="replace") as f:
                text = f.read(1 << 16)
        except OSError:
            return {}

        def number(key):
            m = re.search(r"^" + re.escape(key) + r"=(-?\d+)\s*$", text, re.M)
            return int(m.group(1)) if m else None

        def flag(key):
            m = re.search(r"^" + re.escape(key) + r"=(true|false)\s*$", text, re.M)
            return None if m is None else m.group(1) == "true"
        importer = re.search(r'^importer="([^"]+)"', text, re.M)
        importer = importer.group(1) if importer else ""
        if importer.startswith("texture"):
            mode = number("compress/mode")
            return {"importer": "texture", "max_size": number("process/size_limit") or None,
                    "compressed": None if mode is None else mode not in NO_COMPRESSION,
                    "mipmaps": flag("mipmaps/generate"), "readable": None}
        if importer == "scene":
            return {"importer": "model", "readable": None}
        return {}

    def build_dump(self, cfg, force=False, progress=None):
        """The asset dump, rebuilt when missing, older than DUMP_MAX_AGE, forced, or older than the last bridge report
        that carried asset events. None without a readable project folder."""
        root = self.content_root(cfg)
        if not root or not os.path.isdir(root):
            return None
        path = os.path.join(store.data_dir(cfg), DUMP_FILE)
        dump = None if force else godot_dump.load(path)
        if dump is None or time.time() - dump.get("scanned", 0) > DUMP_MAX_AGE or \
                dump.get("scanned", 0) < self.dump_stale_since(cfg):
            ignore = cfg.get("engine_ignore_dump", self.dump_ignore())
            dump = godot_dump.write(root, path, ignore, log=lambda *_: None, progress=progress)
        return dump

    def lookup(self, dump):
        return godot_dump.lookup(dump)

    def kind_of(self, path):
        return godot_dump.KIND_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")

    def dump_ignore(self, project_mode=False):
        """Add-ons are read for references only."""
        return list(godot_dump.DEFAULT_IGNORE)

    def usage(self, dump, asset_id):
        """Used: something references it, it is the main scene, or project.godot names it (an autoload, the icon).
        Otherwise unreferenced: a path a script builds at run time cannot be seen (check before deleting)."""
        if dump["refs"].get(asset_id) or asset_id in dump.get("build_scenes", ()) or asset_id in dump.get("settings_refs", {}):
            return "used"
        return "unreferenced"
