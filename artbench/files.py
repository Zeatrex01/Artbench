"""Files on disk, for both sides: content hashes (SHA-256) with their cache in the tool folder, and the folder walk
every scan uses. Infrastructure: nothing here knows about models, states or engines."""
import hashlib
import json
import os
import time
import posixpath
import unicodedata
import urllib.parse

from . import config, store

HASH_CACHE_PATH = os.path.join(config.TOOL_ROOT, ".hash_cache.json")
_hash_cache = None
_hash_cache_dirty = False


# --- content hashes ---------------------------------------------------------------------------------------------

RACY_NS = 2 * 10**9          # a file changed this close to its hashing may change again within the same clock tick


def _change_ns(path, st):
    """When the file last changed: st_ctime (on Windows the creation time; NTFS's ChangeTime needs a file handle per
    file, which cost more than a second per thousand files on the Windows CI run, so it is not read)."""
    return st.st_ctime_ns


def sha(path):
    """SHA-256 of a file, cached per path with its size, nanosecond mtime and change time: a same-size rewrite gets a
    new hash, and so does one that restores the old mtime, except on Windows (st_ctime is the creation time there; a
    tool has to restore the exact old mtime on purpose for that to happen). An entry hashed while the file was fresh
    (changed within RACY_NS of the hashing) is never trusted, since a second write in the same clock tick would leave
    every stamp the same. One entry per path, so the cache never grows with versions."""
    global _hash_cache, _hash_cache_dirty
    if _hash_cache is None:
        try:
            with open(HASH_CACHE_PATH, encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            loaded = {}
        _hash_cache = {k: v for k, v in loaded.items() if isinstance(v, list) and len(v) == 5} if isinstance(loaded, dict) else {}
    st = os.stat(path)
    stamp = [st.st_size, st.st_mtime_ns, _change_ns(path, st)]
    hit = _hash_cache.get(path)
    if hit and hit[:3] == stamp and stamp[2] is not None and max(stamp[1], stamp[2]) < hit[3] - RACY_NS:
        return hit[4]
    hashed_at = time.time_ns()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    if not (hit and hit[:3] == stamp and hit[4] == digest):
        _hash_cache_dirty = True             # a fresh file hashed again to the same answer is no reason to write
    _hash_cache[path] = stamp + [hashed_at, digest]
    return digest


def sha_bytes(data):
    """SHA-256 of in-memory bytes (names a cache file by content, e.g. in tests)."""
    return hashlib.sha256(data).hexdigest()


_pruned = False


def save_cache():
    """Writes the hash cache atomically from a copy (other threads, thumbnails and snapshots, may hash meanwhile),
    and only when something was hashed since the last save: a quiet look writes nothing. The first save of a run
    also drops the paths that no longer exist, so the cache stays the size of what is on disk."""
    global _hash_cache_dirty, _pruned
    if _hash_cache is not None and _hash_cache_dirty:
        _hash_cache_dirty = False
        if not _pruned:
            _pruned = True
            for path in [p for p in list(_hash_cache) if not os.path.exists(p)]:
                _hash_cache.pop(path, None)
        store._write_json(HASH_CACHE_PATH, dict(_hash_cache), compact=True)


def name_key(name):
    """A file name as it is compared across sources: lower case and composed Unicode, so "Café.png" from a Windows
    disk and the decomposed form a Mac may store match."""
    return unicodedata.normalize("NFC", name).lower()


# --- folder walk ---------------------------------------------------------------------------------------------------

def walk(root, ignore):
    """Files under root, skipping ignored folder names and Unity-hidden folders (name ending with ~)."""
    lowered = {i.lower() for i in ignore}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.endswith("~") and x.lower() not in lowered]
        for f in files:
            yield os.path.join(d, f)


# --- glTF references -----------------------------------------------------------------------------------------------

GLTF_MAX_BYTES = 64 << 20                   # a .gltf larger than this is not read for its references


_gltf_memo = {}                              # .gltf path -> ((size, mtime_ns), what its JSON names)


def _gltf_uris(path):
    """{"buffers": [uri], "images": [uri]} as the .gltf writes them, read once per change of the file; empty for an
    unreadable or oversized one."""
    try:
        st = os.stat(path)
    except OSError:
        return {"buffers": [], "images": []}
    stamp = (st.st_size, st.st_mtime_ns)
    hit = _gltf_memo.get(path)
    if hit and hit[0] == stamp:
        return hit[1]
    uris = {"buffers": [], "images": []}
    try:
        if st.st_size <= GLTF_MAX_BYTES:
            with open(path, encoding="utf-8-sig") as f:
                doc = json.load(f)
            for key in uris:
                entries = doc.get(key) if isinstance(doc, dict) else None
                for e in entries if isinstance(entries, list) else []:
                    uri = e.get("uri") if isinstance(e, dict) else None
                    if isinstance(uri, str) and not uri.startswith("data:"):
                        uris[key].append(uri)
    except (OSError, ValueError):
        pass
    _gltf_memo[path] = (stamp, uris)
    return uris


def gltf_references(path, model_extensions=()):
    """{"buffers", "images", "unresolved"}: the files a .gltf names that sit beside it, by their names on disk (the
    exact name first, else the same name in another case), and the URIs that cannot travel with it: a file in
    another folder, a missing file, a model file. Embedded data: URIs need nothing. A .gltf without its .bin is a
    broken model in any engine, so what it names travels with it, and what cannot is said out loud."""
    folder = os.path.dirname(path)
    try:
        listing = [n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))]
    except OSError:
        listing = []
    exact, by_lower = set(listing), {}
    for n in listing:
        by_lower.setdefault(n.lower(), n)
    models = tuple(e.lower() for e in model_extensions)
    out = {"buffers": [], "images": [], "unresolved": []}
    for key, uris in _gltf_uris(path).items():
        for uri in uris:
            wanted = posixpath.normpath(urllib.parse.unquote(uri))     # "./Hull.bin" is Hull.bin
            name = None
            if not any(c in wanted for c in "/\\:") and wanted not in (".", ".."):
                name = wanted if wanted in exact else by_lower.get(wanted.lower())
            if name and (name.lower().endswith(models) or name == os.path.basename(path)):
                name = None                                           # a model is never another model's buffer
            if not name:
                if uri not in out["unresolved"]:
                    out["unresolved"].append(uri)
            elif name not in out["buffers"] and name not in out["images"]:
                out[key].append(name)
    return out
