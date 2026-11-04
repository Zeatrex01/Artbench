"""The engine adapter interface: everything Artbench needs to know about one game engine's project layout, asset paths,
sidecar files and asset dump. Modules ask `engines.of(cfg)` instead of assuming an engine, so a new engine is a new
adapter, not a change in every module. The dump shape every reader uses: {"assets": {id: {"path", "kind"}},
"refs": {id: [referrer paths]}, "scanned"}, with paths relative to the content root."""
import os

from .. import store

DUMP_FILE = "engine_index.json"      # written in the project's data folder (the art root in art mode)
DUMP_MAX_AGE = 60                    # seconds; older dumps are rebuilt (half a second with a warm cache)
DUMP_STALE_FILE = "engine_index_stale.json"   # beside the dump: when a bridge report last made it stale


class EngineAdapter:
    name = ""
    prefix = ""                      # how the engine writes a project path: "Assets/", "res://"
    id_kind = ""                     # the engine's own asset id: "guid", "uid"
    layout_defaults = []

    def detect(self, path):
        """{"project_root", "content_root"} of the engine project that contains `path`, or None."""
        return None

    def content_root(self, cfg):
        """The folder engine paths are relative to (Unity: Assets/, Godot: the project root)."""
        raise NotImplementedError

    def project_root(self, cfg):
        """The engine project's root folder (what a bridge reports as project_path)."""
        raise NotImplementedError

    def normalize_engine_path(self, value):
        """The canonical form of an engine path ("Assets/...", either slash accepted); ValueError when `value` is not
        an engine path or escapes the content root."""
        raise NotImplementedError

    def is_engine_path(self, value):
        """True when `value` claims to be inside the content root (it may still be malformed)."""
        return isinstance(value, str) and value.replace("\\", "/").startswith(self.prefix)

    def to_engine_path(self, cfg, abs_path):
        rel = os.path.relpath(abs_path, self.content_root(cfg)).replace("\\", "/")
        return self.normalize_engine_path(self.prefix + rel)

    def from_engine_path(self, cfg, value):
        """The absolute path of an engine path a caller wrote: either slash, and `.`, `..` and doubled slashes resolved
        as a joined string may carry them; ValueError when it is not under the prefix or leaves the content root.
        Bridge reports are held to the strict normalize_engine_path instead."""
        if not self.is_engine_path(value):
            raise ValueError(f"{value!r} is not a path inside {self.prefix}")
        root = os.path.normpath(self.content_root(cfg))
        path = os.path.normpath(os.path.join(root, value.replace("\\", "/")[len(self.prefix):]))
        try:
            inside = os.path.normcase(os.path.commonpath([root, path])) == os.path.normcase(root)
        except ValueError:                   # another drive
            inside = False
        if not inside:
            raise ValueError(f"{value!r} leaves {self.prefix}")
        return path

    def sidecars(self, path):
        """Files the engine keeps beside an asset (kept untouched when Artbench overwrites the asset)."""
        return []

    def build_dump(self, cfg, force=False, progress=None):
        """The engine's asset dump; `progress(stage, done, total, current)` hears how far a rebuild is."""
        raise NotImplementedError

    def lookup(self, dump):
        raise NotImplementedError

    def kind_of(self, path):
        """The asset kind of a file by its name ("model", "texture", ...); "other" when the engine does not say."""
        return "other"

    def dump_ignore(self, project_mode=False):
        """Folder names the dump reads for references but leaves out of its assets, when the config sets no
        engine_ignore_dump."""
        return []

    def mark_dump_stale(self, cfg, when):
        """A bridge report with asset events arrived at `when`: a dump scanned before it is rebuilt on the next look.
        The stamp is a file beside the dump, so every process (the page server, an agent's MCP process) sees it."""
        store._write_json(os.path.join(store.data_dir(cfg), DUMP_STALE_FILE), {"since": when})

    def dump_stale_since(self, cfg):
        """When the dump was last marked stale (epoch seconds); 0.0 when never, or when the stamp cannot be read."""
        data = store._read_json(os.path.join(store.data_dir(cfg), DUMP_STALE_FILE), {})
        try:
            return float(data.get("since") or 0) if isinstance(data, dict) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def usage(self, dump, asset_id):
        """How sure Artbench is that an asset is used: "used" (something references it), "unreferenced" (nothing in
        the files read references it), "by_name" (loaded by name from code, so references cannot show it),
        "unknown" (the project cannot be read for references)."""
        return "used" if dump["refs"].get(asset_id) else "unreferenced"
