"""Machine checks for running Artbench on a real machine (the Windows trial): each check is independent, reports
ok / warn / fail / skip with a plain detail, and never stops the others. Nothing is written into the engine project;
the temp files written to the art folder and the temp folder are removed again. On a project that has none yet, the
run creates the tool's two standard files in the art folder: the lock file `.artbench.lock` and the dump
`engine_index.json` (both kept, as every Artbench run keeps them)."""
import hashlib
import json
import re
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from . import blender_jobs, config, engines, files, github_link, live, mcp_link, store

PROBE_TIMEOUT = 15                   # seconds the lock probe process may take to answer
REACQUIRE_TIMEOUT = 2                # seconds to take the lock back after the probe died
LOCK_PROBE = ("import sys, time\n"
              "sys.path.insert(0, sys.argv[2])\n"
              "from artbench import store\n"
              "try:\n"
              "    held = store.locked_path(sys.argv[1], timeout=1)\n"
              "    held.__enter__()\n"
              "    print('held', flush=True)\n"
              "except TimeoutError:\n"
              "    print('busy', flush=True)\n"
              "time.sleep(60)\n")


def run(cfg, port=None):
    """{"ok": no check failed, "machine": {...}, "checks": [{"id", "status", "detail"}]}."""
    checks = []
    if config.is_project_mode(cfg):
        for check in (_engine_root, _dump, _force_text, _data_writable, _lock, _long_paths, _onedrive, _addressables):
            checks.append(_safely(check.__name__.lstrip("_"), check, cfg))
        checks += [{"id": name, "status": "skip", "detail": "project mode"} for name in ("art_root_writable", "hash", "blender")]
    else:
        for check in (_engine_root, _dump, _art_root_writable, _lock, _hash, _long_paths, _onedrive, _blender):
            checks.append(_safely(check.__name__.lstrip("_"), check, cfg))
    if port is None:
        port = config.PORT
    checks.append(_safely("github_account", _github_account, cfg))
    checks.append(_safely("mcp", _mcp, cfg))
    checks.append(_safely("server", _server, cfg, port))
    return {"ok": all(c["status"] != "fail" for c in checks),
            "machine": {"os": platform.platform(), "python": sys.version.split()[0], "art_root": cfg.get("art_root"),
                        "engine_root": cfg.get("engine_root"), "tool_root": config.TOOL_ROOT},
            "checks": checks}


def _safely(name, check, *args):
    try:
        status, detail = check(*args)
    except Exception as e:  # noqa: BLE001  (a broken check is a failed check, never a failed run)
        status, detail = "fail", f"{type(e).__name__}: {e}"
    return {"id": name, "status": status, "detail": detail}


def _github_account(cfg):
    st = github_link.github_status(cfg)
    if not st["account"]:
        return "skip", "no GitHub account set for this project"
    if st["active"] is None:
        return "warn", f"the GitHub CLI has no github.com account set; this project pushes as {st['account']}: gh auth login"
    if not st["matches"]:
        return "warn", f"the GitHub CLI is set to {st['active']}; this project pushes as {st['account']}: {st['switch']}"
    return "ok", f"the GitHub CLI is set to {st['account']}"


def _mcp(cfg):
    """Whether an AI tool starts this Artbench's MCP server (machine-wide, not per project)."""
    tools = mcp_link.mcp_status()["tools"]
    here = [t["name"] for t in tools if t["state"] == "here"]
    if here:
        return "ok", f"{', '.join(here)} can use Artbench"
    elsewhere = [t["name"] for t in tools if t["state"] == "elsewhere"]
    if elsewhere:
        return "warn", (f"{', '.join(elsewhere)} starts another Artbench folder (moved or an old copy): "
                        "Projects > AI connection updates it")
    return "warn", "no AI tool has Artbench yet: Projects > AI connection adds it to Claude Code"


def _engine_root(cfg):
    adapter = engines.of(cfg)
    root = cfg.get("engine_root")
    if not root:
        return "fail", "no engine_root in the project config"
    if not os.path.isdir(root):
        return "fail", f"engine folder not found: {root}"
    content = adapter.content_root(cfg)
    if not content or not os.path.isdir(content):
        return "fail", f"{adapter.name} content folder not found above {root}"
    return "ok", f"{adapter.name} project at {adapter.project_root(cfg)}"


def _dump(cfg):
    if engines.unreachable(cfg):
        return "skip", "engine folder unreachable"
    start = time.monotonic()
    dump = engines.dump(cfg, force=True)
    if not dump:
        return "fail", "the engine dump could not be built"
    refs = sum(len(v) for v in dump["refs"].values())
    return "ok", f"{len(dump['assets'])} assets, {refs} references, {time.monotonic() - start:.1f} s"


def _art_root_writable(cfg):
    path = os.path.join(store.data_dir(cfg), f".artbench-doctor-{os.getpid()}.json")
    try:
        store._write_json(path, {"doctor": time.time()})
        with open(path, encoding="utf-8") as f:
            f.read()
    finally:
        if os.path.exists(path):
            os.remove(path)
    return "ok", "atomic write and replace work in the " + ("data folder" if config.is_project_mode(cfg) else "art folder")


def _data_writable(cfg):
    """Project mode: the same probe, in the project's data folder."""
    return _art_root_writable(cfg)


def _force_text(cfg):
    """References are read from text-serialized assets: without Force Text every usage is unknown."""
    dump = engines.dump(cfg)
    value = (dump or {}).get("force_text")
    if value is True:
        return "ok", "assets are serialized as text: references can be read"
    if value is False:
        return "fail", ("usage cannot be read: set Project Settings > Editor > Asset Serialization to Force Text "
                        "(every usage shows as unknown until then)")
    return "warn", "ProjectSettings/EditorSettings.asset not found: cannot tell whether the project is Force Text"


ASSET_BUNDLE_RE = re.compile(r"^\s*assetBundleName:[ \t]*\S", re.M)


def _addressables(cfg):
    """Assets loaded through Addressables or AssetBundles are found by their own records, which Artbench does not read:
    they may show as unreferenced."""
    root = engines.of(cfg).content_root(cfg)
    if os.path.isdir(os.path.join(root, "AddressableAssetsData")):
        return "warn", "Addressables found: assets loaded through them may show as unreferenced"
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if not x.startswith(".") and not x.endswith("~")]
        for f in files:
            if f.endswith(".meta"):
                with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                    if ASSET_BUNDLE_RE.search(fh.read(1 << 16)):
                        return "warn", "AssetBundles found: assets loaded through them may show as unreferenced"
    return "ok", "no Addressables or AssetBundles"


def _lock(cfg):
    """A second process takes the project lock; this process must be refused; after the holder is killed the lock
    must be free at once (the OS lock: msvcrt on Windows, fcntl elsewhere)."""
    lock = os.path.join(store.data_dir(cfg), store.LOCK_FILE)
    child = subprocess.Popen([sys.executable, "-c", LOCK_PROBE, lock, config.TOOL_ROOT], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=config.TOOL_ROOT)
    try:
        answer = _first_line(child, PROBE_TIMEOUT)
        if answer is None:
            return "fail", f"the probe process did not answer within {PROBE_TIMEOUT} s"
        if answer == "busy":
            return "warn", "project is busy (another Artbench process or this server is writing); run the check again"
        if answer != "held":
            child.kill()
            reason = (child.communicate(timeout=5)[1] or "").strip().splitlines()
            return "fail", f"the probe process did not start: {reason[-1] if reason else answer or 'no output'}"
        try:
            with store.locked_path(lock, timeout=0.3):
                return "fail", "two processes held the project lock at once"
        except TimeoutError:
            pass
    finally:
        child.kill()
        child.wait()
        child.stdout.close()
        child.stderr.close()
    start = time.monotonic()
    try:
        with store.locked_path(lock, timeout=REACQUIRE_TIMEOUT):
            pass
    except TimeoutError:
        return "warn", "project is busy: another Artbench process took the lock right after the check; run the check again"
    return "ok", f"exclusive between processes; freed {time.monotonic() - start:.2f} s after the holder died"


def _first_line(child, timeout):
    """The probe's first output line, or None when it says nothing in time (a pipe read has no timeout of its own,
    on Windows neither, so a thread reads it)."""
    line = []
    reader = threading.Thread(target=lambda: line.append(child.stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    return line[0].strip() if line else None


def _hash(cfg):
    """The cached hash of one model must equal a fresh read of the file, and the file's stamp must be stable (a
    timestamp the OS reports differently each time would rehash everything; a stale cache would hide changes)."""
    sample = next((os.path.join(d, f) for state in cfg["state_dirs"].values() if os.path.isdir(state)
                   for d, _, names in os.walk(state) for f in names
                   if f.lower().endswith(tuple(cfg["model_extensions"]))), None)
    if not sample:
        return "skip", "no model in the art folder yet"
    stamps = [(st.st_size, st.st_mtime_ns, st.st_ctime_ns) for st in (os.stat(sample), os.stat(sample))]
    if stamps[0] != stamps[1]:
        return "fail", f"{os.path.basename(sample)}: the file's size or times changed between two reads"
    fresh = hashlib.sha256()
    with open(sample, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            fresh.update(chunk)
    if files.sha(sample) != fresh.hexdigest():
        return "fail", f"{os.path.basename(sample)}: the hash cache disagrees with the file (stale cache)"
    return "ok", f"{os.path.basename(sample)} hashed, cache consistent"


def _long_paths(cfg):
    if os.name != "nt":
        return "skip", "only Windows limits paths to 260 characters"
    root = tempfile.mkdtemp(prefix="artbench-doctor-")
    try:
        deep = os.path.join(root, *(["d" * 40] * 7))
        os.makedirs(deep)
        with open(os.path.join(deep, "probe.txt"), "w") as f:
            f.write("x")
        return "ok", "paths over 260 characters work"
    except OSError as e:
        return "warn", f"long paths are not enabled ({e.strerror}); deep folders may fail"
    finally:
        import shutil
        shutil.rmtree(root, ignore_errors=True)


def _onedrive(cfg):
    synced = [p for p in (cfg.get("art_root"), cfg.get("engine_root"), cfg.get("data_dir"), config.TOOL_ROOT)
              if p and "onedrive" in p.lower()]
    if synced:
        return "warn", "inside OneDrive: the sync client may hold files open; pause syncing while sending"
    return "ok", "no sync folder in the paths"


def _blender(cfg):
    exe = blender_jobs.blender(cfg)
    return ("ok", exe) if exe else ("warn", "Blender not found: previews and the metadata diff are off")


def _server(cfg, port):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1", headers={"Host": f"127.0.0.1:{port}"})
    try:
        with urllib.request.urlopen(req, timeout=1) as r:
            answer = json.load(r)
    except urllib.error.HTTPError as e:
        return "fail", f"port {port} answers HTTP {e.code}: another program may use it"
    except ValueError:
        answer = None
    except OSError:
        return "skip", f"the page server is not running on port {port}"
    if not isinstance(answer, dict) or answer.get("api") != "artbench":
        return "fail", f"port {port} answers, but not as Artbench: another program may use it"
    if answer.get("engine_report_schema") != live.SCHEMA:
        return "warn", f"an older Artbench answers on port {port}; restart it (and every agent CLI's MCP server)"
    return "ok", f"the page server answers on port {port}"
