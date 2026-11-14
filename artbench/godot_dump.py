"""Godot asset dump without Godot: every asset under a project's folder, what kind it is, and which assets reference it,
read from the project's text files, in the same shape the Unity dump has (so the catalog, usage, graph and checks read
either). Nothing is written into the Godot project.

An asset's id is the engine's own uid: from its .import file (imported files), its .uid file (scripts and shaders,
Godot 4.4+) or the header of a text scene or resource; a file with none gets "path:<path>". References are the
"res://..." and "uid://..." strings in scenes (.tscn), resources (.tres), scripts (.gd, .cs), shaders and
project.godot, the ones an .import file points at (a model's external materials), the external resources of a
binary resource (.res, .scn), and the uris of a .gltf. A script's quoted folder + quoted file name is a reference; a
bare file name alone only names the file ("named": usage by_name). Scripts in dev folders (DEFAULT_DEV) do neither. A
file that cannot be read (damaged, too large, compressed in a way this Python cannot open) is listed in "unreadable"
with the reason; it never stops the scan. A scene another scene instances is a prefab; any other scene is a scene.
The main scene and everything project.godot names count as used.

    python -m artbench.godot_dump <project folder> <out.json> [--ignore Name ...] [--dev Name ...]

Reads are kept in memory by (size, mtime) for as long as the process runs, so a rescan of a few thousand files is quick.
"""
import json
import os
import posixpath
import re
import stat
import struct
import sys
import time
import zlib

DEFAULT_IGNORE = ("addons",)
# Scripts in these folders are the project's own tools, probes and tests, not the game: a bare file name or a
# folder + name they quote does not make a file used (their full res:// paths still do). An entry without a slash is
# a folder name matched anywhere; one with a slash (or "res://") is a path from the project folder. Config key
# engine_dev_dirs replaces the list.
DEFAULT_DEV = ("tools", "tool", "probes", "probe", "dev", "debug", "test", "tests", "scratch")
SIDECARS = (".import", ".uid")
NOT_ASSETS = ("project.godot", "export_presets.cfg", "override.cfg")
REF_EXTS = (".tscn", ".tres", ".gd", ".cs", ".gdshader", ".gdshaderinc")
MAX_FILE = 64 << 20                                  # bytes; a larger file is not read and is listed as unreadable
MAX_UNPACKED = 256 << 20                             # bytes; a compressed resource that unpacks larger is not read
KIND_BY_EXT = {
    ".glb": "model", ".gltf": "model", ".fbx": "model", ".obj": "model", ".blend": "model", ".dae": "model",
    ".png": "texture", ".jpg": "texture", ".jpeg": "texture", ".tga": "texture", ".webp": "texture", ".exr": "texture",
    ".hdr": "texture", ".svg": "texture", ".bmp": "texture", ".tif": "texture", ".tiff": "texture", ".dds": "texture",
    ".ktx": "texture", ".ktx2": "texture",
    ".tscn": "scene", ".scn": "scene",
    ".gdshader": "shader", ".gdshaderinc": "shader", ".gd": "script", ".cs": "script",
    ".wav": "audio", ".mp3": "audio", ".ogg": "audio",
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font", ".pfb": "font", ".pfm": "font",
}
RESOURCE_KIND = {                                    # a .tres / .res by its class (the header's type)
    "material": ("StandardMaterial3D", "ORMMaterial3D", "ShaderMaterial", "CanvasItemMaterial", "ParticleProcessMaterial",
                 "PanoramaSkyMaterial", "ProceduralSkyMaterial", "PhysicalSkyMaterial", "FogMaterial"),
    "clip": ("Animation", "AnimationLibrary"),
    "animator": ("AnimationNodeStateMachine", "AnimationNodeBlendTree", "AnimationNodeBlendSpace1D",
                 "AnimationNodeBlendSpace2D", "AnimationNodeAnimation", "AnimationNodeOneShot",
                 "AnimationNodeTransition", "AnimationNodeAdd2", "AnimationNodeBlend2"),
    "mesh": ("ArrayMesh", "BoxMesh", "SphereMesh", "CapsuleMesh", "CylinderMesh", "PlaneMesh", "QuadMesh", "PrismMesh",
             "TorusMesh", "TextMesh", "PointMesh", "TubeTrailMesh", "RibbonTrailMesh", "ImmediateMesh", "PrimitiveMesh",
             "PlaceholderMesh", "MeshLibrary", "ArrayOccluder3D"),
    "atlas": ("AtlasTexture", "SpriteFrames", "TileSet"),
    "shader": ("Shader", "VisualShader", "ShaderInclude"),
    "texture": ("ImageTexture", "PortableCompressedTexture2D", "CompressedTexture2D", "GradientTexture1D",
                "GradientTexture2D", "NoiseTexture2D", "NoiseTexture3D", "Image", "CurveTexture", "CurveXYZTexture",
                "Texture2DArray", "Texture3D", "ImageTexture3D", "Cubemap", "CubemapArray", "CompressedTexture3D",
                "CompressedTexture2DArray", "CompressedCubemap", "CompressedCubemapArray", "AnimatedTexture",
                "CanvasTexture", "PlaceholderTexture2D", "CameraTexture", "MeshTexture"),
    "audio": ("AudioStreamWAV", "AudioStreamOggVorbis", "AudioStreamMP3", "AudioStreamRandomizer",
              "AudioStreamPlaylist", "AudioStreamInteractive", "AudioStreamSynchronized", "AudioStreamPolyphonic"),
    "font": ("FontFile", "FontVariation", "SystemFont"),
}
QUOTED_RES = re.compile(r"""["']\*?(res://[^"']+)["']""")
QUOTED_UID = re.compile(r"""["'](uid://[a-z0-9]+)["']""")
OWN_UID = re.compile(r"""^uid=["'](uid://[a-z0-9]+)["']""", re.M)
HEADER_UID = re.compile(r"""^\[gd_(?:scene|resource)[^\]\n]*\buid=["'](uid://[a-z0-9]+)["']""", re.M)
HEADER_TYPE = re.compile(r"""^\[gd_resource[^\]\n]*\btype=["'](\w+)["']""", re.M)
MAIN_SCENE = re.compile(r"""^run/main_scene=["']([^"']+)["']""", re.M)
# A script that builds a path: a quoted folder ("res://a/b/", or "res://" itself) that the script joins onto something
# (the literal, or the const / var holding it, is followed by + or .path_join), and quoted file names ("x.otf",
# "sub/y.tres") in the same file; a joined folder + name that is a file of the project is a reference. A name that is
# a dictionary key ("x.tres": ...) never joins. A name that joins nothing only names the file: usage "by_name", weaker
# than used. Scripts in DEFAULT_DEV folders do neither.
SCRIPT_EXTS = (".gd", ".cs")
QUOTED_DIR = re.compile(r"""["'](res://(?:[^"'\n]*/)?)["']""")
QUOTED_NAME = re.compile(r"""["']([\w.\-/ ]+\.(\w{2,8}))["']""")
DIR_HOLDER = re.compile(r"""(?:const|var|static\s+var)\s+(\w+)\s*(?::\s*[\w\[\]]*\s*)?:?=\s*$""")
JOIN_AFTER = re.compile(r"""\s*(?:\+|\.path_join\b|\.plus_file\b)""")
DICT_KEY_AFTER = re.compile(r"""\s*:(?!=)""")
# Binary resources (.res, .scn): "RSRC" plain, "RSCC" compressed (mode 0 FastLZ, 1 Deflate, 2 Zstd, 3 Gzip, 4 Brotli).
RES_MARK = b"res://"
UID_MARK = b"uid://"
UID_CHARS = "abcdefghijklmnopqrstuvwxy012345678"   # core/io/resource_uid.cpp uuid_characters (34)
FORMAT_FLAG_UIDS, FORMAT_FLAG_HAS_SCRIPT_CLASS, RESERVED_FIELDS = 2, 8, 11   # core/io/resource_format_binary.h

_MEM = {}                                            # abs path -> (size, mtime_ns, parsed)


class Unreadable(Exception):
    """A file whose references cannot be read; the message is the reason the dump lists."""


def _kind_of_resource(rtype):
    for kind, types in RESOURCE_KIND.items():
        if rtype in types:
            return kind
    return "asset"


def uid_text(n):
    """Godot's text form of a uid number (ResourceUID::id_to_text): base 34, most significant digit first."""
    if n < 0:
        return None
    out = ""
    while True:
        out = UID_CHARS[n % 34] + out
        n //= 34
        if not n:
            return "uid://" + out


def _clean_res(p):
    """A project-relative path from a res:// string: no scheme, no sub-resource suffix ("::id")."""
    return p[len("res://"):].split("::", 1)[0]


def _read(path):
    """The parsed file {uid, type, paths, uids, names, dirs, unreadable}, from memory when it has not changed. Never
    raises: a file that cannot be read gets unreadable = the reason, and whatever was read before the fault."""
    parsed = {"uid": None, "type": None, "paths": [], "uids": [], "names": [], "dirs": [], "unreadable": None}
    try:
        st = os.stat(path)
    except OSError as e:
        parsed["unreadable"] = f"cannot be read: {e.strerror or e}"
        return parsed
    if not stat.S_ISREG(st.st_mode):                 # a pipe, socket or device would block or never end
        parsed["unreadable"] = "not a regular file (a pipe, socket or device): not read"
        return parsed
    hit = _MEM.get(path)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    ext = os.path.splitext(path)[1].lower()
    try:
        if st.st_size > MAX_FILE:
            raise Unreadable(f"too large to read ({st.st_size / (1 << 20):.0f} MB; the limit is {MAX_FILE >> 20} MB)")
        if ext in (".res", ".scn"):
            _read_binary(path, parsed)
        elif ext == ".gltf":
            _read_gltf(path, parsed)
        else:
            _read_text(path, ext, parsed)
    except Unreadable as e:
        parsed["unreadable"] = str(e)
    except OSError as e:
        parsed["unreadable"] = f"cannot be read: {e.strerror or e}"
    except Exception as e:                           # a reader fault must never stop the scan
        parsed["unreadable"] = f"corrupt: {type(e).__name__}: {e}"
    _MEM[path] = (st.st_size, st.st_mtime_ns, parsed)
    return parsed


def _read_text(path, ext, parsed):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    own = OWN_UID.search(text) if path.endswith(".import") else HEADER_UID.search(text)
    parsed["uid"] = own.group(1) if own else None
    rtype = HEADER_TYPE.search(text)
    parsed["type"] = rtype.group(1) if rtype else None
    parsed["paths"] = sorted({q for q in (_clean_res(p) for p in QUOTED_RES.findall(text)) if not q.startswith(".godot/")})
    parsed["uids"] = sorted(set(QUOTED_UID.findall(text)))
    if ext in SCRIPT_EXTS:
        names, joinable = set(), set()
        for m in QUOTED_NAME.finditer(text):
            n, e = m.group(1).strip(), m.group(2).lower()
            if not n or n.startswith(("res:", "/")) or not ("." + e in KIND_BY_EXT or e in ("tres", "res")):
                continue
            names.add(n)
            if not DICT_KEY_AFTER.match(text, m.end()):
                joinable.add(n)
        parsed["names"], parsed["join_names"] = sorted(names), sorted(joinable)
        parsed["dirs"] = sorted(_joined_dirs(text))


def _joined_dirs(text):
    """The quoted res:// folders a script joins onto something: the literal itself is followed by + or .path_join, or
    it is the value of a const / var whose name is followed by one of them somewhere in the script."""
    out, joined_names = set(), None
    for m in QUOTED_DIR.finditer(text):
        d = m.group(1)[len("res://"):]
        if JOIN_AFTER.match(text, m.end()):
            out.add(d)
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        holder = DIR_HOLDER.search(text[line_start:m.start()])
        if holder:
            if joined_names is None:              # every identifier followed by + or .path_join, found once
                joined_names = set(re.findall(r"\b(\w+)" + JOIN_AFTER.pattern, text))
            if holder.group(1) in joined_names:
                out.add(d)
    return out


def _read_gltf(path, parsed):
    """The files a .gltf names by uri (its textures, its .bin), as absolute paths resolved from its folder; the dump
    makes them project-relative against the scanned folder."""
    from urllib.parse import unquote
    try:
        with open(path, encoding="utf-8-sig") as f:   # a byte order mark is allowed, as in files.py
            doc = json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        raise Unreadable(f"corrupt: not JSON ({e})")
    if not isinstance(doc, dict):
        raise Unreadable("corrupt: not a glTF document (the JSON is not an object)")
    out, faults = set(), []
    for key in ("images", "buffers"):
        items = doc.get(key)
        if items is None:
            continue
        if not isinstance(items, list):
            faults.append(f"{key} is not a list")
            continue
        for i, item in enumerate(items):
            uri = item.get("uri") if isinstance(item, dict) else None
            if uri is None:
                continue                              # a bufferView image or a .glb's own buffer: no file
            if not isinstance(uri, str):
                faults.append(f"{key}[{i}].uri is not a string")
                continue
            if uri and not uri.startswith("data:") and "://" not in uri:
                out.add(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)), unquote(uri))))
    parsed["abs_paths"] = sorted(out)
    if faults:
        parsed["unreadable"] = "corrupt: " + "; ".join(faults[:3]) + (" ..." if len(faults) > 3 else "")


def _zstd():
    try:
        from compression import zstd                 # Python 3.14+
        return zstd
    except ImportError:
        return None


def _unpack(raw):
    """The bytes after the RSRC magic of an RSCC file (FileAccessCompressed: mode, block size, total size, one
    compressed size per block, the blocks)."""
    if len(raw) < 16:
        raise Unreadable("corrupt: truncated compressed header")
    mode, block, total = struct.unpack_from("<III", raw, 4)
    if block == 0:
        raise Unreadable("corrupt: block size 0")
    if mode in (0, 4):
        raise Unreadable(f"compressed with {'FastLZ' if mode == 0 else 'Brotli'}, which Artbench cannot read")
    if mode not in (1, 2, 3):
        raise Unreadable(f"corrupt: unknown compression mode {mode}")
    if total > MAX_UNPACKED:
        raise Unreadable(f"too large to read (unpacks to {total >> 20} MB; the limit is {MAX_UNPACKED >> 20} MB)")
    count = total // block + 1                     # Godot writes one block more than whole blocks, always
    if 16 + 4 * count > len(raw):
        raise Unreadable(f"corrupt: truncated ({count} blocks listed, the file ends inside the list)")
    sizes = struct.unpack_from("<%dI" % count, raw, 16)
    if 16 + 4 * count + sum(sizes) > len(raw):
        raise Unreadable(f"corrupt: truncated (the blocks need {16 + 4 * count + sum(sizes)} bytes, the file has {len(raw)})")
    if mode == 2:
        zstd = _zstd()
        if zstd is None:
            raise Unreadable("compressed with Zstd: needs Python 3.14 or newer to read "
                             f"(this is {sys.version_info[0]}.{sys.version_info[1]})")
    pos, parts = 16 + 4 * count, []
    for i, n in enumerate(sizes):
        want = block if i < count - 1 else total - block * (count - 1)
        data = raw[pos:pos + n]
        if len(data) < n:
            raise Unreadable(f"corrupt: truncated (block {i + 1} of {count} is cut short)")
        if want == 0:
            pos += n
            continue
        try:
            if mode == 2:
                part = zstd.ZstdDecompressor().decompress(data, want)
            else:
                part = zlib.decompressobj(zlib.MAX_WBITS if mode == 1 else 16 + zlib.MAX_WBITS).decompress(data, want)
        except Exception as e:
            raise Unreadable(f"corrupt: block {i + 1} of {count} does not unpack ({e})")
        if len(part) != want:
            raise Unreadable(f"corrupt: block {i + 1} of {count} unpacks to {len(part)} bytes, not {want}")
        parts.append(part)
        pos += n
    return b"".join(parts)


class _Bin:
    """Reads Godot's binary resource header (ResourceLoaderBinary::open) from bytes, never past the end."""

    def __init__(self, data):
        self.d, self.p, self.e = data, 0, "<"

    def take(self, n):
        if n < 0 or self.p + n > len(self.d):
            raise Unreadable("corrupt: truncated (the header runs past the end of the file)")
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def u32(self):
        return struct.unpack(self.e + "I", self.take(4))[0]

    def i64(self):
        return struct.unpack(self.e + "q", self.take(8))[0]

    def count(self, least):
        n = self.u32()
        if n * least > len(self.d) - self.p:
            raise Unreadable(f"corrupt: a count of {n} is larger than the file")
        return n

    def string(self):                             # get_unicode_string: int32 length (with the \0), UTF-8 bytes
        n = self.u32()
        if n & 0x80000000:                        # Godot reads the length as a signed int: negative is a broken file
            raise Unreadable(f"corrupt: a string length of {n:#x} (negative in Godot)")
        return self.take(n).split(b"\0", 1)[0].decode("utf-8", "replace")


def _body_strings(data, mark, endian):
    """Every length-prefixed string in the body that starts with `mark` (res:// or uid://): Godot stores a String
    value as u32 length (with its \0) + UTF-8, so spaces and non-ASCII names come out whole."""
    out, i = set(), data.find(mark)
    while i >= 0:
        s = None
        if i >= 4:
            n = struct.unpack(endian + "I", data[i - 4:i])[0] & 0x7FFFFFFF
            if len(mark) < n <= len(data) - i and data[i + n - 1] == 0:
                s = data[i:i + n - 1].split(b"\0", 1)[0].decode("utf-8", "replace")
        if s is None:                             # not a length-prefixed string: read up to a quote, \0 or control byte
            end = i
            while end < len(data) and data[end] > 0x20 and data[end] not in b"\"'":
                end += 1
            s = data[i:end].decode("utf-8", "replace")
        out.add(s)
        i = data.find(mark, i + len(mark))
    return out


def _read_binary(path, parsed):
    """The class in a binary resource's header, its own uid, its external resources (path + uid, read as Godot writes
    them: a length-prefixed path and a raw int64 uid) and any res:// / uid:// strings in its body. A compressed file
    this Python cannot open, or a damaged one, raises Unreadable with the reason."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:4] == b"RSCC":
        data = _unpack(raw)
    elif raw[:4] == b"RSRC":
        data = raw[4:]
    else:
        raise Unreadable("corrupt: not a Godot binary resource (no RSRC or RSCC magic)")
    r = _Bin(data)
    big_endian = r.u32()
    r.u32()                                       # use_real64
    r.e = ">" if big_endian else "<"
    r.u32(), r.u32(), r.u32()                     # major, minor, format version
    parsed["type"] = r.string() or None
    r.i64()                                       # import metadata offset
    flags = r.u32()
    own = r.i64()                                 # the uid field is always there; it holds the uid with FORMAT_FLAG_UIDS
    if flags & FORMAT_FLAG_UIDS:
        parsed["uid"] = uid_text(own)
    if flags & FORMAT_FLAG_HAS_SCRIPT_CLASS:
        r.string()
    r.take(4 * RESERVED_FIELDS)
    for _ in range(r.count(4)):                   # string table (property names)
        r.string()
    paths, uids, rel_paths = set(), set(), set()
    for _ in range(r.count(8)):                   # external resources: type, path, uid
        r.string()
        p = r.string()
        if p.startswith("res://"):
            paths.add(_clean_res(p))
        elif p.startswith("uid://"):
            uids.add(p)
        elif p and "://" not in p:
            rel_paths.add(p.split("::", 1)[0])    # saved with FLAG_RELATIVE_PATHS: relative to this file's folder
        if flags & FORMAT_FLAG_UIDS:
            u = uid_text(r.i64())
            if u:
                uids.add(u)
    for _ in range(r.count(12)):                  # internal resources: "local://N" or the path it was saved under,
        r.string()                                # and an offset. Not a reference: a renamed or moved file still
        r.take(8)                                 # holds its old path here, and Godot does not load it.
    body = data[r.p:]
    paths |= {_clean_res(s) for s in _body_strings(body, RES_MARK, r.e)}
    uids |= {s for s in _body_strings(body, UID_MARK, r.e) if re.fullmatch(r"uid://[a-z0-9]+", s)}
    parsed["paths"] = sorted(p for p in paths if p and not p.startswith(".godot/"))
    parsed["uids"] = sorted(uids)
    parsed["rel_paths"] = sorted(rel_paths)


def _matcher(entries):
    """rel folder -> True when an entry names it or a folder above it: an entry without a slash is a folder name,
    matched anywhere (any letter case); one with a slash (or "res://") is a path from the project folder."""
    entries = [e for e in (entries or ()) if isinstance(e, str) and e.strip("/")]
    names = {e.lower() for e in entries if "/" not in e and not e.startswith("res://")}
    paths = [e[len("res://"):].strip("/") if e.startswith("res://") else e.strip("/")
             for e in entries if "/" in e or e.startswith("res://")]
    paths = [q for q in paths if q]
    return lambda rel: any(part.lower() in names for part in rel.split("/") if part) or \
        any(rel == q or rel.startswith(q + "/") for q in paths)


def _utf8(name):
    try:
        name.encode("utf-8")
        return True
    except UnicodeEncodeError:                       # bytes the file system holds that are not UTF-8 (surrogates)
        return False


def _shown(rel):
    """A path that is safe to write as UTF-8 JSON: bytes that are not UTF-8 become U+FFFD."""
    return rel.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _walk(root, ignore, bad_names=None):
    """(path, ignored) for every file: hidden folders (.godot, .git) and folders holding a .gdignore are skipped,
    ignored folders are walked too and their files marked, so what they reference still counts. A file or folder
    whose name is not UTF-8 (Godot cannot open it either) is left out and added to `bad_names`."""
    is_ignored = _matcher(ignore)
    bad_names = [] if bad_names is None else bad_names
    for d, dirs, files in os.walk(root):
        rel = os.path.relpath(d, root).replace("\\", "/")
        rel = "" if rel == "." else rel
        bad_names += [(rel + "/" if rel else "") + x + "/" for x in dirs if not x.startswith(".") and not _utf8(x)]
        dirs[:] = [x for x in dirs if not x.startswith(".") and _utf8(x)]
        if ".gdignore" in files:
            dirs[:] = []
            continue
        ignored = is_ignored(rel)
        for f in files:
            if f.startswith("."):
                continue
            if not _utf8(f):
                bad_names.append((rel + "/" if rel else "") + f)
                continue
            yield os.path.join(d, f), ignored


def _reporter(progress, total):
    step = max(1, total // 200)
    return lambda stage, done, current: progress(stage, done, total, current) if done % step == 0 or done == total else None


def build(root, ignore=DEFAULT_IGNORE, log=print, progress=None, dev=DEFAULT_DEV):
    """{"assets": {id: {"path", "kind"}}, "refs": {id: [referrer paths]}, "uses": {path: [ids]}, "build_scenes": [ids],
    "force_text": True, "settings_refs": {id: ["project.godot"]}, "outside": {id: path} (assets of ignored folders),
    "named": {id: [game scripts that name the file by its bare name]}, "unreadable": [{path, reason}],
    "scanned", "assets_root"}; paths are relative to the project folder. `dev`: folders whose scripts are tools, not
    the game (see DEFAULT_DEV). `progress(stage, done, total, current)` hears how far the reading is: "files", "meta"
    (ids), "refs", "settings"."""
    t0 = time.time()
    root = os.path.normpath(os.path.abspath(root))
    progress = progress or (lambda *_: None)
    rel_of = lambda p: os.path.relpath(p, root).replace("\\", "/")
    is_dev = _matcher(dev)
    listed, bad_names = [], []
    for item in _walk(root, set(ignore), bad_names):
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
        elif p + ".uid" in sidecar_of and os.path.isfile(p + ".uid"):
            try:
                with open(p + ".uid", encoding="utf-8", errors="replace") as f:
                    found = re.search(r"uid://[a-z0-9]+", f.read(200))
            except OSError:
                found = None
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
        if ext in (".tres", ".res", ".scn") and rtype == "PackedScene":
            kind = "scene"
        elif ext == ".tres":
            kind = _kind_of_resource(rtype)
        elif ext in (".res", ".scn"):
            kind = _kind_of_resource(rtype) if rtype else "asset"
        elif ext in KIND_BY_EXT:
            kind = KIND_BY_EXT[ext]
        (outside if ignored else assets)[asset_id] = rel if ignored else {"path": rel, "kind": kind}

    # References: strings in scenes, resources, scripts and .import files, resolved by path, else by uid. A script's
    # folder + name joins and bare names are looked up in this index (no folder x name product is built).
    refs, uses, named = {}, {}, {}
    unreadable = [{"path": _shown(b), "reason": "the name is not valid UTF-8: Godot cannot open it, not read"}
                  for b in bad_names]
    by_base = {}
    for q in id_of:
        by_base.setdefault(q.rsplit("/", 1)[-1], []).append(q)
    report = _reporter(progress, len(sources))
    for done, (p, rel, is_import) in enumerate(sources, 1):
        report("refs", done, rel)
        parsed = _read(p)
        own = id_of.get(rel)
        paths = set(parsed["paths"]) | {rel_of(a) for a in parsed.get("abs_paths", ())
                                        if a == root or a.startswith(root + os.sep)}
        paths |= {posixpath.normpath(posixpath.join(posixpath.dirname(rel), q)) for q in parsed.get("rel_paths", ())}
        found = {id_of[q] for q in paths if q in id_of} | {id_by_uid[u] for u in parsed["uids"] if u in id_by_uid}
        script_dir = os.path.dirname(rel)
        if parsed["names"] and not is_dev(script_dir):
            dirs, joinable = set(parsed["dirs"]), set(parsed.get("join_names", ()))
            for n in parsed["names"]:
                hits = [q for q in by_base.get(n.rsplit("/", 1)[-1], ()) if q == n or q.endswith("/" + n)]
                joined = [q for q in hits if n in joinable and q[:len(q) - len(n)] in dirs]
                found |= {id_of[q] for q in joined}
                if not joined:                    # named, not loaded as far as the text shows: by_name
                    for q in hits:
                        if id_of[q] != own:
                            named.setdefault(id_of[q], set()).add(rel)
        if parsed.get("unreadable"):
            unreadable.append({"path": rel if not is_import else rel + ".import", "reason": parsed["unreadable"]})
        found.discard(own)
        for g in found:
            refs.setdefault(g, []).append(rel)
        if found:
            uses[rel] = sorted(set(uses.get(rel, [])) | found)
    for g in refs:
        refs[g] = sorted(set(refs[g]))
    named = {g: sorted(v) for g, v in named.items()}

    # project.godot: the main scene, the autoloads, the icon: everything it names is used.
    progress("settings", 0, 1, "project.godot")
    build_scenes, settings_refs = [], {}
    settings = os.path.join(root, "project.godot")
    try:
        if not os.path.isfile(settings):
            raise OSError("not a file")
        with open(settings, encoding="utf-8", errors="replace") as f:
            text = f.read(MAX_FILE)
    except OSError:
        text = ""
    if text:
        named_here = {id_of[q] for q in (_clean_res(r) for r in QUOTED_RES.findall(text)) if q in id_of}
        named_here |= {id_by_uid[u] for u in QUOTED_UID.findall(text) if u in id_by_uid}
        for g in named_here:
            settings_refs[g] = ["project.godot"]
        main = MAIN_SCENE.search(text)
        if main:
            value = main.group(1)
            target = id_of.get(_clean_res(value)) if value.startswith("res://") else id_by_uid.get(value)
            if target:
                build_scenes.append(target)
    progress("settings", 1, 1, "project.godot")

    # A scene another scene instances is a prefab (the main scene never is).
    for g, a in assets.items():
        if a["path"].endswith(".tscn") and g not in build_scenes and any(r.endswith(".tscn") for r in refs.get(g, ())):
            a["kind"] = "prefab"
    named_only = sum(1 for g in named if g not in refs and g not in settings_refs and g not in build_scenes)
    for key in [k for k in _MEM if k.startswith(root + os.sep) and not os.path.exists(k)]:
        del _MEM[key]
    out = {"scanned": time.time(), "assets_root": root, "assets": assets, "refs": refs, "uses": uses,
           "build_scenes": build_scenes, "force_text": True, "settings_refs": settings_refs, "outside": outside,
           "named": named, "dev_dirs": list(dev or ()),
           "unreadable": sorted(unreadable, key=lambda u: u["path"])}
    log(f"godot dump: {len(assets)} assets, {len(sources)} reference files, {len(refs)} referenced ids, "
        f"{named_only} named only by a script, {len(unreadable)} files not readable, {time.time() - t0:.1f}s")
    return out


def write(root, out_path, ignore=DEFAULT_IGNORE, log=print, progress=None, dev=DEFAULT_DEV):
    data = build(root, ignore, log, progress, dev)
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
    ignore, dev = list(DEFAULT_IGNORE), list(DEFAULT_DEV)
    for flag, into in (("--dev", dev), ("--ignore", ignore)):
        if flag in argv:
            i = argv.index(flag)
            rest = argv[i + 1:]
            stop = next((k for k, x in enumerate(rest) if x.startswith("--")), len(rest))
            into += rest[:stop]
            argv = argv[:i] + rest[stop:]
    write(argv[0], argv[1], ignore, dev=dev)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
