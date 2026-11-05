"""Unity: projects are folders with Assets/ and ProjectSettings/, asset paths are "Assets/...", every asset has a
.meta sidecar holding its guid and import settings, and the dump is read from the text-serialized files
(unity_dump.py) without Unity running."""
import os
import re
import time

from .. import store, unity_dump
from .base import DUMP_FILE, DUMP_MAX_AGE, EngineAdapter


class UnityAdapter(EngineAdapter):
    name = "unity"
    prefix = "Assets/"
    id_kind = "guid"
    # Unity's folder rules, used by layout.check when a project has no "layout_rules". Patterns are folders relative
    # to the engine root, fnmatch style, matched against the asset's folder (with a trailing slash). The first rule
    # whose kinds include the asset wins.
    layout_defaults = [
        {"kinds": ["model"], "allow": ["Art/*/", "Art/*/*/", "TechArt/Content/Models/", "Lab/Models/*"],
         "hint": "Models live in Art/<Category>/ (or TechArt/Content/Models/ for tech-art models), never at the root."},
        {"kinds": ["texture"], "allow": ["Art/*/", "Art/*/*/", "TechArt/Content/Textures/*", "TechArt/Content/Vfx/*",
                                         "TechArt/Content/Ground/*", "UI/*", "Lab/*"],
         "hint": "Textures sit next to their model in Art/<Category>/ or under TechArt/Content/Textures/."},
        {"kinds": ["material"], "allow": ["Art/", "Art/*/", "Art/*/*/", "Data/Materials/*", "TechArt/Materials/",
                                          "TechArt/Content/Materials/*", "TechArt/Content/Vfx/*", "UI/*", "Lab/*"],
         "hint": "Materials go to Data/Materials/, TechArt/Content/Materials/ or beside their model in Art/."},
        {"kinds": ["prefab"], "allow": ["Prefabs/*", "Art/*/", "Art/*/*/", "TechArt/Content/*", "UI/*", "Lab/*"],
         "hint": "Prefabs go to Prefabs/ or TechArt/Content/Prefabs/."},
    ]

    def detect(self, path):
        p = os.path.normpath(path)
        while True:
            if os.path.isdir(os.path.join(p, "Assets")) and os.path.isdir(os.path.join(p, "ProjectSettings")):
                return {"project_root": p, "content_root": os.path.join(p, "Assets")}
            parent = os.path.dirname(p)
            if parent == p:
                return None
            p = parent

    def content_root(self, cfg):
        """config engine_assets_root, else the nearest Assets ancestor of engine_root."""
        if cfg.get("engine_assets_root"):
            return cfg["engine_assets_root"]
        p = cfg.get("engine_root")
        while p and os.path.basename(p) != "Assets" and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        return p if p and os.path.basename(p) == "Assets" else cfg.get("engine_root")

    def project_root(self, cfg):
        root = self.content_root(cfg)
        return os.path.dirname(root) if root else None

    def normalize_engine_path(self, value):
        if not isinstance(value, str):
            raise ValueError("path missing")
        path = value.replace("\\", "/")
        parts = path.split("/")
        if parts[0] != "Assets" or ".." in parts or "" in parts[1:] or ":" in path:
            raise ValueError(f"{value!r} is not a path inside Assets/")
        return path

    def sidecars(self, path):
        return [path + ".meta"]

    def import_settings(self, path):
        """The texture or model importer's settings in the asset's .meta (the default platform's: the first value of
        each key). Read only; a missing or unreadable .meta gives {}."""
        try:
            with open(path + ".meta", encoding="utf-8", errors="replace") as f:
                text = f.read(1 << 16)
        except OSError:
            return {}
        def first(key):
            m = re.search(r"^\s*" + key + r":\s*(-?\d+)", text, re.M)
            return int(m.group(1)) if m else None
        if "TextureImporter:" in text:
            out = {"importer": "texture", "max_size": first("maxTextureSize"), "readable": first("isReadable")}
            comp, mips = first("textureCompression"), first("enableMipMap")
            out["compressed"] = None if comp is None else comp != 0
            out["mipmaps"] = None if mips is None else mips != 0
        elif "ModelImporter:" in text:
            out = {"importer": "model", "readable": first("isReadable")}
        else:
            return {}
        if out["readable"] is not None:
            out["readable"] = out["readable"] != 0
        return out

    def build_dump(self, cfg, force=False, progress=None):
        """The asset dump, rebuilt when missing, older than DUMP_MAX_AGE, forced, or older than the last bridge report
        that carried asset events (dump_stale_since). None without a readable content root."""
        root = self.content_root(cfg)
        if not root or not os.path.isdir(root):
            return None
        path = os.path.join(store.data_dir(cfg), DUMP_FILE)
        dump = None if force else unity_dump.load(path)
        if dump is None or time.time() - dump.get("scanned", 0) > DUMP_MAX_AGE or \
                dump.get("scanned", 0) < self.dump_stale_since(cfg):
            ignore = cfg.get("engine_ignore_dump", self.dump_ignore())
            dump = unity_dump.write(root, path, ignore, log=lambda *_: None, progress=progress)
        return dump

    def lookup(self, dump):
        return unity_dump.lookup(dump)

    def kind_of(self, path):
        return unity_dump.KIND_BY_EXT.get(os.path.splitext(path)[1].lower(), "other")

    def dump_ignore(self, project_mode=False):
        """Third-party folders read for references only. Project mode keeps StreamingAssets: its files are loaded by
        name, and the catalog lists them as such."""
        ignore = list(unity_dump.DEFAULT_IGNORE)
        return [d for d in ignore if d != "StreamingAssets"] if project_mode else ignore

    def usage(self, dump, asset_id):
        """Unknown without Force Text (the files cannot be read for references); scenes enabled in the build settings
        and assets named in ProjectSettings are roots, so used; assets in a Resources folder or StreamingAssets are loaded by name from code."""
        if dump.get("force_text") is False:
            return "unknown"
        if dump["refs"].get(asset_id) or asset_id in dump.get("build_scenes", ()) or asset_id in dump.get("settings_refs", {}):
            return "used"
        path = dump["assets"].get(asset_id, {}).get("path", "")
        if "Resources" in path.split("/")[:-1] or path.startswith("StreamingAssets/"):
            return "by_name"
        return "unreferenced"
