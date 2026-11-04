"""Unity asset dump without Unity: every asset under a project's Assets folder (from its .meta files), what kind it
is, and which assets reference it (direct references, read from the text-serialized prefabs, scenes, materials,
ScriptableObjects and animator controllers). Nothing is written into the Unity project.

    python -m artbench.unity_dump <Assets folder> <out.json> [--ignore Name ...]

Needs the project's serialization set to Force Text (ProjectSettings > Editor), which Unity projects under version
control normally have. Reads are cached by (size, mtime), so a rescan of a few thousand files is quick.
"""
import json
import os
import re
import sys
import time

from . import config, store

CACHE_PATH = os.path.join(config.TOOL_ROOT, ".unity_dump_cache.json")
GUID_RE = re.compile(rb"guid: ([0-9a-f]{32})")
META_GUID_RE = re.compile(r"^guid: ([0-9a-f]{32})", re.M)
TEXT_GUID_RE = re.compile(r"guid: ([0-9a-f]{32})")
SERIALIZATION_RE = re.compile(r"m_SerializationMode:\s*(\d+)")
BUILD_SCENE_RE = re.compile(r"-\s*enabled:\s*(\d)\s*\n\s*path:[^\n]*\n\s*guid:\s*([0-9a-f]{32})")
MAX_META_FILE = 1 << 20          # bytes; a .meta larger than this is read for its guid only
# Text-serialized files that hold references to other assets.
REF_EXTS = (".prefab", ".unity", ".mat", ".asset", ".controller", ".anim", ".overridecontroller", ".playable",
            ".spriteatlas", ".shadergraph", ".vfx", ".preset")
KIND_BY_EXT = {
    ".fbx": "model", ".obj": "model", ".glb": "model", ".gltf": "model", ".blend": "model",
    ".png": "texture", ".tga": "texture", ".jpg": "texture", ".jpeg": "texture", ".psd": "texture", ".exr": "texture",
    ".tif": "texture", ".tiff": "texture",
    ".mat": "material", ".prefab": "prefab", ".unity": "scene", ".controller": "animator", ".anim": "clip",
    ".shader": "shader", ".shadergraph": "shader", ".hlsl": "shader", ".cginc": "shader",
    ".cs": "script", ".asmdef": "script", ".dll": "script",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".ttf": "font", ".otf": "font", ".spriteatlas": "atlas",
}
DEFAULT_IGNORE = ("Third_Party_Asset", "Third_Party_Assets", "Plugins", "Game VFX Mega Pack(Built-In)",
                  "ExternalDependencyManager", "TextMesh Pro", "StreamingAssets")
MAX_REF_FILE = 64 << 20          # bytes; a text asset larger than this is skipped


class _Cache(dict):
    """The file cache; `dirty` once an entry was added or replaced, so an unchanged project writes nothing."""
    dirty = False

    def __setitem__(self, key, value):
        self.dirty = True
        super().__setitem__(key, value)


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return _Cache(data if isinstance(data, dict) else {})
    except (OSError, ValueError):
        return _Cache()


def _walk(root, ignore):
    """(path, ignored) for every file: ignored folders are walked too, their files marked, so what they reference
    still counts while their own assets stay out of the dump. An entry without a slash is a folder name, matched
    anywhere ("Plugins"); one with a slash is a path from the Assets folder ("Assets/Art/Old"), that folder only."""
    names = {e for e in ignore if "/" not in e}
    paths = [(e[len("Assets/"):] if e.startswith("Assets/") else e).strip("/") for e in ignore if "/" in e]
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.endswith("~") and not x.startswith(".")]
        rel = os.path.relpath(d, root).replace("\\", "/")
        rel = "" if rel == "." else rel
        ignored = any(part in names for part in rel.split("/")) or any(rel == p or rel.startswith(p + "/") for p in paths)
        for f in files:
            yield os.path.join(d, f), ignored


def _read_meta(p, cache):
    """(guid, [guids of the model import remaps]) of a .meta file, cached by size and time."""
    st = os.stat(p)
    key = p.lower()
    entry = cache.get(key)
    if entry and entry.get("meta") and entry["size"] == st.st_size and int(entry["mtime"]) == int(st.st_mtime):
        return entry["guid"], entry["remaps"]
    with open(p, encoding="utf-8", errors="replace") as f:
        text = f.read(MAX_META_FILE if st.st_size <= MAX_META_FILE else 600)
    m = META_GUID_RE.search(text[:600])
    guid = m.group(1) if m else None
    remaps = []
    at = text.find("externalObjects:")
    if guid and at >= 0:
        remaps = sorted(set(TEXT_GUID_RE.findall(text[at:])) - {guid})
    cache[key] = {"meta": True, "size": st.st_size, "mtime": st.st_mtime, "guid": guid, "remaps": remaps}
    return guid, remaps


def _project_settings(assets_root):
    """(force_text: True | False | None, [guids of the enabled build scenes], {guid: [settings files that name it]})
    from the ProjectSettings beside Assets. Assets named there (player icons, splash logos, always-included shaders,
    render pipeline assets) are loaded by the game without any asset referencing them."""
    settings = os.path.join(os.path.dirname(assets_root), "ProjectSettings")
    named = {}
    try:
        names = sorted(n for n in os.listdir(settings) if n.endswith(".asset") and n != "EditorBuildSettings.asset")
    except OSError:
        names = []
    for name in names:
        try:
            with open(os.path.join(settings, name), "rb") as f:
                data = f.read(MAX_REF_FILE)
        except OSError:
            continue
        for g in sorted(set(x.decode() for x in GUID_RE.findall(data))):
            named.setdefault(g, []).append("ProjectSettings/" + name)
    force_text = None
    try:
        with open(os.path.join(settings, "EditorSettings.asset"), encoding="utf-8", errors="replace") as f:
            m = SERIALIZATION_RE.search(f.read())
        if m:
            force_text = m.group(1) == "2"
    except OSError:
        pass
    scenes = []
    try:
        with open(os.path.join(settings, "EditorBuildSettings.asset"), encoding="utf-8", errors="replace") as f:
            scenes = [g for enabled, g in BUILD_SCENE_RE.findall(f.read().replace("\r", "")) if enabled == "1"]
    except OSError:
        pass
    return force_text, scenes, named


def _kind(path, head):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".asset":
        head = head.replace(b"\r", b"")           # files saved with CRLF
        if b"\nMesh:\n" in head:
            return "mesh"
        if b"\nMonoBehaviour:\n" in head:
            return "data"
        return "asset"
    return KIND_BY_EXT.get(ext, "other")


def build(assets_root, ignore=DEFAULT_IGNORE, log=print):
    """{"assets": {guid: {"path", "kind"}}, "refs": {guid: [referrer paths]}, "uses": {path: [guids]},
    "build_scenes": [guids], "force_text": bool | None, "settings_refs": {guid: [ProjectSettings files]},
    "outside": {guid: path} (assets of ignored folders), "scanned", "assets_root"}. Folders in `ignore` add their
    references but not their assets; a model's import remaps (externalObjects in its .meta) are references by the
    model."""
    t0 = time.time()
    assets_root = os.path.normpath(assets_root)
    cache = _load_cache()
    assets, by_path = {}, {}
    ref_files = []
    refs, uses, outside = {}, {}, {}
    for p, ignored in _walk(assets_root, set(ignore)):
        if p.endswith(".meta"):
            target = p[:-5]
            if not os.path.isfile(target):
                continue                              # folder meta or stale meta
            guid, remaps = _read_meta(p, cache)
            if not guid:
                continue
            rel = os.path.relpath(target, assets_root).replace("\\", "/")
            by_path[rel] = guid
            if not ignored:
                assets[guid] = {"path": rel, "kind": None}
            else:
                outside[guid] = rel
            for g in remaps:
                refs.setdefault(g, []).append(rel)
            if remaps:
                uses[rel] = list(remaps)
        elif p.lower().endswith(REF_EXTS):
            ref_files.append(p)

    # Kinds and references, with the cache.
    read = 0
    for p in ref_files:
        rel = os.path.relpath(p, assets_root).replace("\\", "/")
        st = os.stat(p)
        key = p.lower()
        entry = cache.get(key)
        if not entry or entry["size"] != st.st_size or int(entry["mtime"]) != int(st.st_mtime):
            if st.st_size > MAX_REF_FILE:
                continue
            with open(p, "rb") as f:
                data = f.read()
            read += 1
            entry = {"size": st.st_size, "mtime": st.st_mtime, "kind": _kind(p, data[:4000]),
                     "guids": sorted(set(g.decode() for g in GUID_RE.findall(data)))}
            cache[key] = entry
        own = by_path.get(rel)
        if own and own in assets:
            assets[own]["kind"] = entry["kind"]
        used = [g for g in entry["guids"] if g != own]
        for g in used:
            refs.setdefault(g, []).append(rel)
        if used:
            uses[rel] = sorted(set(uses.get(rel, [])) | set(used))
    for guid, a in assets.items():
        if a["kind"] is None:
            a["kind"] = _kind(a["path"], b"")
    for g in refs:
        refs[g] = sorted(set(refs[g]))

    if cache.dirty:
        store._write_json(CACHE_PATH, cache, compact=True)  # atomic: another process may read it meanwhile
    force_text, build_scenes, settings_refs = _project_settings(assets_root)
    out = {"scanned": time.time(), "assets_root": assets_root, "assets": assets, "refs": refs, "uses": uses,
           "build_scenes": build_scenes, "force_text": force_text, "settings_refs": settings_refs, "outside": outside}
    log(f"unity dump: {len(assets)} assets, {len(ref_files)} reference files ({read} read, rest cached), "
        f"{len(refs)} referenced guids, {time.time() - t0:.1f}s")
    return out


def write(assets_root, out_path, ignore=DEFAULT_IGNORE, log=print):
    data = build(assets_root, ignore, log)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def lookup(dump):
    """Helpers over a dump: path -> guid, path -> [(referrer path, referrer kind)]."""
    assets_root = dump["assets_root"]
    guid_of = {a["path"]: g for g, a in dump["assets"].items()}
    kind_of = {a["path"]: a["kind"] for a in dump["assets"].values()}

    def used_by(abs_or_rel_path):
        rel = abs_or_rel_path
        if os.path.isabs(rel):
            rel = os.path.relpath(rel, assets_root).replace("\\", "/")
        g = guid_of.get(rel)
        if not g:
            return None
        return [{"path": r, "kind": kind_of.get(r, "other"), "name": os.path.basename(r)} for r in dump["refs"].get(g, [])]

    return guid_of, kind_of, used_by


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    ignore = list(DEFAULT_IGNORE)
    if "--ignore" in argv:
        i = argv.index("--ignore")
        ignore += argv[i + 1:]
        argv = argv[:i]
    write(argv[0], argv[1], ignore)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
