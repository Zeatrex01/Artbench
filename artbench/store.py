"""Per-project persisted files, all in the project's data folder (the art root in art mode): notes (inventory.json), tasks (tasks.json), the sync base
(sync_base.json: the last state both sides agreed on, per model) and the history log. Every change to project files,
notes or tasks goes through `log` so the history stays complete. JSON writes are atomic (temp file + replace) and
writers hold the project lock (`locked`): an operating-system lock on a file in the art root, shared by the HTTP
server, the MCP process, the command line and anything else that writes to the same project. The OS releases it
when a process dies, so a crash never leaves the project locked and nothing has to guess whether a lock is stale."""
import contextlib
import json
import os
import threading
import time

try:
    import fcntl
except ImportError:              # Windows
    fcntl = None
    import msvcrt

TASKS_FILE = "tasks.json"
SYNC_BASE_FILE = "sync_base.json"
LOCK_FILE = ".artbench.lock"
DEFAULT_LOCK_TIMEOUT = 10.0
_guards = {}                     # lock path -> RLock: one thread of this process at a time
_guards_lock = threading.Lock()
_held = {}                       # lock path -> [fd, depth] of the thread holding it (re-entrant use)


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data, compact=False):
    """Atomic: the file is either the old content or the complete new content, never half-written."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 2}))
            f.flush()
            os.fsync(f.fileno())
        replace_with_retry(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def replace_with_retry(src, dst, attempts=20, pause=0.05):
    """os.replace that waits out a reader holding `dst` open (Windows raises PermissionError while another process,
    OneDrive or an indexer has the file open)."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(pause)


def data_dir(cfg):
    """The folder a project's own files live in: `data_dir` of a loaded config; a hand-made config that only names
    an art root (scripts, older callers) keeps working."""
    return cfg.get("data_dir") or cfg["art_root"]


def locked(cfg, timeout=None):
    """Holds the project lock while writing. Re-entrant in the holding thread; other threads of this process and
    other processes wait up to `timeout` seconds (default DEFAULT_LOCK_TIMEOUT), then TimeoutError is raised."""
    return locked_path(os.path.join(data_dir(cfg), LOCK_FILE), timeout)


@contextlib.contextmanager
def locked_path(path, timeout=None):
    """The same lock on any lock file (the live report cache uses one beside it)."""
    deadline = time.monotonic() + (DEFAULT_LOCK_TIMEOUT if timeout is None else timeout)
    with _guards_lock:
        guard = _guards.setdefault(path, threading.RLock())
    if not guard.acquire(timeout=max(0.0, deadline - time.monotonic())):
        raise TimeoutError("project is busy")
    try:
        if path in _held:                    # this thread holds it already
            _held[path][1] += 1
            try:
                yield
            finally:
                _held[path][1] -= 1
            return
        fd = _acquire(path, deadline)
        _held[path] = [fd, 1]
        try:
            yield
        finally:
            del _held[path]
            _release(fd)
    finally:
        guard.release()


def _acquire(path, deadline):
    """Opens the lock file and takes the OS lock on it, retrying until `deadline` (time.monotonic())."""
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_RDWR)
        except PermissionError:              # Windows: a scanner or indexer has the file open for a moment
            fd = None
        if fd is not None:
            if _try_lock(fd):
                try:                         # who holds it, for a person looking at the file
                    os.ftruncate(fd, 0)
                    os.write(fd, f"{os.getpid()} {time.time():.0f}".encode())
                except OSError:
                    pass
                return fd
            os.close(fd)
        if time.monotonic() >= deadline:
            raise TimeoutError("project is busy")
        time.sleep(0.05)


def _try_lock(fd):
    """The OS lock without waiting; False while another process holds it."""
    try:
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _release(fd):
    """Releases the OS lock. The file itself stays: deleting a lock file others may have open would let two
    processes lock two different files."""
    try:
        if fcntl:
            fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def notes(cfg):
    """{"items": {item id: {note, source, engine_path}}}."""
    data = _read_json(cfg["inventory_path"], {"items": {}})
    data.setdefault("items", {})
    return data


def save_notes(cfg, data):
    _write_json(cfg["inventory_path"], data)


def tasks(cfg):
    return _read_json(os.path.join(data_dir(cfg), TASKS_FILE), {"tasks": []}).get("tasks", [])


def save_tasks(cfg, task_list):
    _write_json(os.path.join(data_dir(cfg), TASKS_FILE), {"tasks": task_list})


def sync_base(cfg):
    """{item id: {"art": sha, "engine": sha, "time": ...}}: the last content both sides agreed on."""
    data = _read_json(os.path.join(data_dir(cfg), SYNC_BASE_FILE), {})
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items()                  # a hand-edited entry never breaks the scan
            if isinstance(v, dict) and isinstance(v.get("art"), str) and isinstance(v.get("engine"), str)}


def save_sync_base(cfg, data):
    _write_json(os.path.join(data_dir(cfg), SYNC_BASE_FILE), data)


def log(cfg, verb, *fields):
    """One history line: timestamp, verb, fields (tab-separated)."""
    line = "\t".join([time.strftime("%Y-%m-%d %H:%M:%S"), verb, *[str(f) for f in fields]])
    with open(cfg["history_path"], "a", encoding="utf-8") as f:
        f.write(line + "\n")


def history(cfg, last=200):
    """The last `last` log lines, newest first."""
    if not os.path.exists(cfg["history_path"]):
        return []
    with open(cfg["history_path"], encoding="utf-8") as f:
        lines = f.read().splitlines()
    return lines[-last:][::-1]
