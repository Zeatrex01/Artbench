"""Godot asset dump without Godot: every asset under a project's folder, what kind it is, and which assets reference it,
read from the project's text files, in the same shape the Unity dump has (so the catalog, usage, graph and checks read
either). Nothing is written into the Godot project.

An asset's id is the engine's own uid: from its .import file (imported files), its .uid file (scripts and shaders,
Godot 4.4+) or the header of a text scene or resource; a file with none gets "path:<path>". References are the
"res://..." and "uid://..." strings in scenes (.tscn), resources (.tres), scripts (.gd, .cs), shaders and
project.godot, and the ones an .import file points at (a model's external materials). A scene another scene instances
is a prefab; any other scene is a scene. The main scene and everything project.godot names count as used.

    python -m artbench.godot_dump <project folder> <out.json> [--ignore Name ...]

Reads are kept in memory by (size, mtime) for as long as the process runs, so a rescan of a few thousand files is quick.
"""
import json
import os
import re
import sys
import time

DEFAULT_IGNORE = ("addons",)
SIDECARS = (".import", ".uid")
NOT_ASSETS = ("project.godot", "export_presets.cfg", "override.cfg")
REF_EXTS = (".tscn", ".tres", ".gd", ".cs", ".gdshader", ".gdshaderinc")
MAX_FILE = 64 << 20                                  # bytes; a larger text file is not read for references
KIND_BY_EXT = {
    ".glb": "model", ".gltf": "model", ".fbx": "model", ".obj": "model", ".blend": "model", ".dae": "model",
    ".png": "texture", ".jpg": "texture", ".jpeg": "texture", ".tga": "texture", ".webp": "texture", ".exr": "texture",
    ".hdr": "texture", ".svg": "texture", ".bmp": "texture", ".tif": "texture", ".tiff": "texture", ".dds": "texture",
    ".tscn": "scene", ".scn": "scene",
    ".gdshader": "shader", ".gdshaderinc": "shader", ".gd": "script", ".cs": "script",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
}
RESOURCE_KIND = {                                    # a .tres by its type (the header's gd_resource type)
    "material": ("StandardMaterial3D", "ORMMaterial3D", "ShaderMaterial", "CanvasItemMaterial", "ParticleProcessMaterial",
                 "PanoramaSkyMaterial", "ProceduralSkyMaterial", "PhysicalSkyMaterial", "StandardMaterial2D"),
    "clip": ("Animation", "AnimationLibrary"),
    "animator": ("AnimationNodeStateMachine", "AnimationNodeBlendTree", "AnimationNodeBlendSpace1D",
                 "AnimationNodeBlendSpace2D"),
    "mesh": ("ArrayMesh", "BoxMesh", "SphereMesh", "CapsuleMesh", "CylinderMesh", "PlaneMesh", "QuadMesh", "PrimitiveMesh"),
    "atlas": ("AtlasTexture", "SpriteFrames", "TileSet"),
    "shader": ("Shader", "VisualShader"),
    "texture": ("ImageTexture", "PortableCompressedTexture2D", "CompressedTexture2D", "GradientTexture1D",
                "GradientTexture2D", "NoiseTexture2D", "Image"),
}
QUOTED_RES = re.compile(r"""["']\*?(res://[^"']+)["']""")
QUOTED_UID = re.compile(r"""["'](uid://[a-z0-9]+)["']""")
OWN_UID = re.compile(r"""^uid=["'](uid://[a-z0-9]+)["']""", re.M)
HEADER_UID = re.compile(r"""^\[gd_(?:scene|resource)[^\]\n]*\buid=["'](uid://[a-z0-9]+)["']""", re.M)
HEADER_TYPE = re.compile(r"""^\[gd_resource[^\]\n]*\btype=["'](\w+)["']""", re.M)
MAIN_SCENE = re.compile(r"""^run/main_scene=["']([^"']+)["']""", re.M)
# A script that builds a path: a quoted folder ("res://a/b/") and quoted file names ("x.otf", "sub/y.tres") in the same
# file; each name is tried under each folder. A name with no folder that matches one file only is a reference too.
SCRIPT_EXTS = (".gd", ".cs")
QUOTED_DIR = re.compile(r"""["'](res://[^"'\n]*/)["']""")
QUOTED_NAME = re.compile(r"""["']([\w.\-/]+\.(\w{2,8}))["']""")
# Binary resources (.res, .scn): "RSRC" plain, "RSCC" compressed (mode 0 FastLZ, 1 Deflate, 2 Zstd, 3 Gzip).
BIN_RES = re.compile(rb"res://[\x21-\x7e]+")
BIN_UID = re.compile(rb"uid://[a-z0-9]+")

_MEM = {}                                            # abs path -> (size, mtime_ns, parsed)


def _kind_of_resource(rtype):
    for kind, types in RESOURCE_KIND.items():
        if rtype in types:
            return kind
    return "asset"


def _read(path):
    """The parsed text file {uid, type, paths, uids}, from memory when it has not changed."""
    st = os.stat(path)
    hit = _MEM.get(path)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    parsed = {"uid": None, "type": None, "paths": [], "uids": [], "names": []}
    ext = os.path.splitext(path)[1].lower()
    if st.st_size <= MAX_FILE and ext in (".res", ".scn"):
        parsed.update(_read_binary(path))
    elif st.st_size <= MAX_FILE and ext == ".gltf":
        parsed["paths"] = _gltf_uris(path)
    elif st.st_size <= MAX_FILE:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        own = OWN_UID.search(text) if path.endswith(".import") else HEADER_UID.search(text)
        parsed["uid"] = own.group(1) if own else None
        rtype = HEADER_TYPE.search(text)
        parsed["type"] = rtype.group(1) if rtype else None
        parsed["paths"] = sorted({p[len("res://"):] for p in QUOTED_RES.findall(text)
                                  if not p[len("res://"):].startswith(".godot/")})
        parsed["uids"] = sorted(set(QUOTED_UID.findall(text)))
        if ext in SCRIPT_EXTS:
            names = {n for n, e in QUOTED_NAME.findall(text) if "." + e.lower() in KIND_BY_EXT or e.lower() in ("tres", "res")}
            names -= {n for n in names if n.startswith("res:")}
            dirs = {d[len("res://"):] for d in QUOTED_DIR.findall(text)}
            parsed["paths"] = sorted(set(parsed["paths"]) | {d + n for d in dirs for n in names})
            parsed["names"] = sorted(n for n in names if "/" not in n)
    _MEM[path] = (st.st_size, st.st_mtime_ns, parsed)
    return parsed


def _gltf_uris(path):
    """Project-relative paths of the files a .gltf names by uri (its textures, its .bin), resolved from its folder."""
    import json
    from urllib.parse import unquote
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return []
    root = _project_root_of(path)
    out = set()
    for key in ("images", "buffers"):
        for item in doc.get(key) or ():
            uri = item.get("uri") if isinstance(item, dict) else None
            if uri and not uri.startswith("data:") and "://" not in uri:
                full = os.path.normpath(os.path.join(os.path.dirname(path), unquote(uri)))
                if root:
                    out.add(os.path.relpath(full, root).replace("\\", "/"))
    return sorted(out)


def _project_root_of(path):
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.isfile(os.path.join(d, "project.godot")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def _decompress(mode, data):
    """One RSCC block, or None when this Python cannot (FastLZ always; Zstd before Python 3.14)."""
    import zlib
    try:
        if mode == 1:
            return zlib.decompress(data)
        if mode == 3:
            return zlib.decompress(data, 16 + zlib.MAX_WBITS)
        if mode == 2:
            from compression import zstd             # Python 3.14+
            return zstd.decompress(data)
    except Exception:
        return None
    return None


def _read_binary(path):
    """{type, paths, uids, unreadable} of a binary resource: the class in its header and the res:// and uid://
    strings it holds (its external resources). A compressed file this Python cannot open is marked unreadable."""
    import struct
    with open(path, "rb") as f:
        raw = f.read()
    out = {"paths": [], "uids": [], "type": None, "unreadable": False}
    if raw[:4] == b"RSCC":
        mode, block, total = struct.unpack_from("<III", raw, 4)
        count = total // block + 1                # Godot writes one block more than whole blocks, always
        sizes = struct.unpack_from("<%dI" % count, raw, 16)
        pos, parts = 16 + 4 * count, []
        for n in sizes:
            part = _decompress(mode, raw[pos:pos + n])
            if part is None:
                out["unreadable"] = True
                return out
            parts.append(part)
            pos += n
        raw = b"".join(parts)                     # what follows the RSRC magic (the magic itself is not compressed)
    elif raw[:4] != b"RSRC":
        return out
    else:
        raw = raw[4:]
    try:                                          # big_endian, use_real64, major, minor, format, then the class name
        length = struct.unpack_from("<I", raw, 20)[0]
        out["type"] = raw[24:24 + length].rstrip(b"\0").decode("ascii", "replace") or None
    except struct.error:
        pass
    out["paths"] = sorted({m.decode("ascii")[len("res://"):] for m in BIN_RES.findall(raw)})
    out["uids"] = sorted({m.decode("ascii") for m in BIN_UID.findall(raw)})
    return out


def _walk(root, ignore):
    """(path, ignored) for every file: hidden folders (.godot, .git) and folders holding a .gdignore are skipped,
    ignored folders are walked too and their files marked, so what they reference still counts. An entry without a
    slash is a folder name, matched anywhere; one with a slash (or "res://") is a path from the project folder."""
    names = {e for e in ignore if "/" not in e}
    paths = [e[len("res://"):].strip("/") if e.startswith("res://") else e.strip("/") for e in ignore if "/" in e or e.startswith("res://")]
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".")]
        if ".gdignore" in files:
            dirs[:] = []
            continue
        rel = os.path.relpath(d, root).replace("\\", "/")
        rel = "" if rel == "." else rel
        ignored = any(part in names for part in rel.split("/")) or any(rel == p or rel.startswith(p + "/") for p in paths)
        for f in files:
            if not f.startswith("."):
                yield os.path.join(d, f), ignored


def _reporter(progress, total):
    step = max(1, total // 200)
    return lambda stage, done, current: progress(stage, done, total, current) if done % step == 0 or done == total else None


def build(root, ignore=DEFAULT_IGNORE, log=print, progress=None):
    """{"assets": {id: {"path", "kind"}}, "refs": {id: [referrer paths]}, "uses": {path: [ids]}, "build_scenes": [ids],
    "force_text": True, "settings_refs": {id: ["project.godot"]}, "outside": {id: path} (assets of ignored folders),
    "scanned", "assets_root"}; paths are relative to the project folder. `progress(stage, done, total, current)`
    hears how far the reading is: "files", "meta" (ids), "refs", "settings"."""
    t0 = time.time()
    root = os.path.normpath(root)
    progress = progress or (lambda *_: None)
    rel_of = lambda p: os.path.relpath(p, root).replace("\\", "/")
    listed = []
    for item in _walk(root, set(ignore)):
        listed.append(item)
        if len(listed) % 500 == 0:
            progress("files", len(listed), 0, rel_of(item[0]))
    progress("files", len(listed), len(listed), "")
    sidecar_of = {p for p, _ in listed if p.endswith(SIDECARS)}
    candidates = [(p, ig) for p, ig in listed if p not in sidecar_of and os.path.basename(p) not in NOT_ASSETS]

    # Ids: an .import file, a .uid file or the file's own header names the uid; none: the path.
    report = _reporter(progress, len(candidates))
    assets, outside, id_of, id_by_uid, sources = {}, {}, {}, {}, []
    for done, (p, ignored) in enumerate(candidates, 1):
        rel = rel_of(p)
        report("meta", done, rel)
        uid = None
        if p + ".import" in sidecar_of:
            uid = _read(p + ".import")["uid"]
            sources.append((p + ".import", rel, True))         # a model's external materials, from its .import
        elif p + ".uid" in sidecar_of:
            with open(p + ".uid", encoding="utf-8", errors="replace") as f:
                found = re.search(r"uid://[a-z0-9]+", f.read(200))
            uid = found.group(0) if found else None
        ext = os.path.splitext(p)[1].lower()
        rtype = None
        if ext in (".tscn", ".tres", ".res", ".scn"):
            parsed = _read(p)
            uid = uid or parsed["uid"]
            rtype = parsed["type"]
        asset_id = uid or "path:" + rel
        id_of[rel] = asset_id
        if uid:
            id_by_uid[uid] = asset_id
        if ext in REF_EXTS or ext in (".res", ".scn", ".gltf"):
            sources.append((p, rel, False))
        kind = "other"
        if ext == ".tres":
            kind = _kind_of_resource(rtype)
        elif ext in (".res", ".scn"):
            kind = "scene" if rtype == "PackedScene" else _kind_of_resource(rtype) if rtype else "asset"
        elif ext in KIND_BY_EXT:
            kind = KIND_BY_EXT[ext]
        (outside if ignored else assets)[asset_id] = rel if ignored else {"path": rel, "kind": kind}

    # References: strings in scenes, resources, scripts and .import files, resolved by path, else by uid.
    refs, uses, unreadable = {}, {}, []
    by_name = {}
    for q in id_of:
        by_name.setdefault(q.rsplit("/", 1)[-1], []).append(q)
    report = _reporter(progress, len(sources))
    for done, (p, rel, is_import) in enumerate(sources, 1):
        report("refs", done, rel)
        parsed = _read(p)
        own = id_of.get(rel)
        found = {id_of[q] for q in parsed["paths"] if q in id_of} | {id_by_uid[u] for u in parsed["uids"] if u in id_by_uid}
        found |= {id_of[by_name[n][0]] for n in parsed.get("names", ()) if len(by_name.get(n, ())) == 1}
        if parsed.get("unreadable"):
            unreadable.append(rel)
        found.discard(own)
        for g in found:
            refs.setdefault(g, []).append(rel)
        if found:
            uses[rel] = sorted(set(uses.get(rel, [])) | found)
    for g in refs:
        refs[g] = sorted(set(refs[g]))

    # project.godot: the main scene, the autoloads, the icon: everything it names is used.
    progress("settings", 0, 1, "project.godot")
    build_scenes, settings_refs = [], {}
    settings = os.path.join(root, "project.godot")
    if os.path.isfile(settings):
        with open(settings, encoding="utf-8", errors="replace") as f:
            text = f.read()
        named = {id_of[q[len("res://"):]] for q in QUOTED_RES.findall(text) if q[len("res://"):] in id_of}
        named |= {id_by_uid[u] for u in QUOTED_UID.findall(text) if u in id_by_uid}
        for g in named:
            settings_refs[g] = ["project.godot"]
        main = MAIN_SCENE.search(text)
        if main:
            value = main.group(1)
            target = id_of.get(value[len("res://"):]) if value.startswith("res://") else id_by_uid.get(value)
            if target:
                build_scenes.append(target)
    progress("settings", 1, 1, "project.godot")

    # A scene another scene instances is a prefab (the main scene never is).
    for g, a in assets.items():
        if a["path"].endswith(".tscn") and g not in build_scenes and any(r.endswith(".tscn") for r in refs.get(g, ())):
            a["kind"] = "prefab"
    for key in [k for k in _MEM if k.startswith(root + os.sep) and not os.path.exists(k)]:
        del _MEM[key]
    out = {"scanned": time.time(), "assets_root": root, "assets": assets, "refs": refs, "uses": uses,
           "build_scenes": build_scenes, "force_text": True, "settings_refs": settings_refs, "outside": outside,
           "unreadable": sorted(unreadable)}
    log(f"godot dump: {len(assets)} assets, {len(sources)} reference files, {len(refs)} referenced ids, "
        f"{len(unreadable)} compressed resources not readable here, {time.time() - t0:.1f}s")
    return out


def write(root, out_path, ignore=DEFAULT_IGNORE, log=print, progress=None):
    data = build(root, ignore, log, progress)
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
    """Helpers over a dump: path -> id, path -> kind, path -> [{path, kind, name} of what references it]."""
    root = dump["assets_root"]
    id_of = {a["path"]: g for g, a in dump["assets"].items()}
    kind_of = {a["path"]: a["kind"] for a in dump["assets"].values()}

    def used_by(abs_or_rel_path):
        rel = abs_or_rel_path
        if os.path.isabs(rel):
            rel = os.path.relpath(rel, root).replace("\\", "/")
        g = id_of.get(rel)
        if not g:
            return None
        return [{"path": r, "kind": kind_of.get(r, "other"), "name": os.path.basename(r)} for r in dump["refs"].get(g, [])]

    return id_of, kind_of, used_by


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
