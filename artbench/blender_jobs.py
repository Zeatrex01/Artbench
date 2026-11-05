"""One background Blender worker for the whole tool: thumbnails and metadata snapshots are jobs on a priority queue
(snapshots first, so an open card never waits behind a page of renders; within a priority the newest request first,
so what the person looks at now, or the project they just switched to, comes before older requests), each producing
one file in the content-hash cache under Artbench/.cache/<kind>/, so a given file version is processed once.
Blender is kept open between jobs (starting it costs seconds, a job a fraction of one), started without the person's
own add-ons and preferences; a Blender that cannot be kept open is started once per job instead. Outputs are written
to a temp path and renamed into place, because the HTTP server and the MCP process share the cache. A job whose
output never appears is remembered as failed for this process; the page asks again until the file exists."""
import itertools
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid

from . import config, files, store

CACHE_DIR = os.path.join(config.TOOL_ROOT, ".cache")
DEFAULT_BLENDER = [r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
                   r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
                   r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"]
PRIORITY_META = 0
PRIORITY_THUMB = 5
PRIORITY_STATS = 8            # catalog statistics: after the previews someone is looking at
IDLE_SECONDS = 30            # the worker thread exits after this long without a job
JOB_TIMEOUT = 120
MAX_JOBS_PER_RUNNER = 200    # a kept-open Blender is restarted after this many jobs, so memory never piles up
BACKGROUND_ARGS = ["-b", "--factory-startup"]     # no window; none of the person's add-ons or preferences
# The kept-open Blender: one JSON job per line on stdin, each run as Blender runs a script (`-- src out args`), each
# answered "ARTBENCH-JOB <id> done" on stdout (Blender prints its own lines too). An empty line or the end of input ends it.
RUNNER_EXPR = (
    "import json, runpy, sys, traceback\n"
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if not line:\n"
    "        break\n"
    "    job = json.loads(line)\n"
    "    sys.argv = ['blender', '--', job['src'], job['out'], *job['args']]\n"
    "    try:\n"
    "        runpy.run_path(job['script'], run_name='__main__')\n"
    "    except SystemExit:\n"
    "        pass\n"
    "    except BaseException:\n"
    "        traceback.print_exc()\n"
    "    print('ARTBENCH-JOB %s done' % job['id'], flush=True)\n"
)
_queue = queue.PriorityQueue()
_seq = itertools.count()
_pending = set()
_failed = set()
_lock = threading.Lock()
_worker = None
_runners = {}                # Blender executable -> the kept-open _Runner (used by the worker thread only)
_no_runner = set()           # executables that could not be kept open: one Blender per job for them


def blender(cfg):
    """The Blender executable for this project: config `blender`, else the first known install, else blender on
    PATH. None when absent."""
    for p in [cfg.get("blender")] + DEFAULT_BLENDER:
        if p and os.path.exists(p):
            return p
    return shutil.which("blender")                    # Linux, macOS (a link), or a Windows install on PATH


def cache_path_for_hash(kind, sha, ext):
    return os.path.join(CACHE_DIR, kind, f"{sha[:16]}.{ext}")


def cache_path(kind, path, ext):
    """A model's cache file, named by its content: for a .gltf that is the .gltf and the buffers it names, so a change
    to the geometry alone (the .bin) is a new snapshot and a new preview."""
    key = files.sha(path)
    if path.lower().endswith(".gltf"):
        buffers = files.gltf_references(path)["buffers"]
        if buffers:
            folder = os.path.dirname(path)
            key = files.sha_bytes(" ".join([key] + [files.sha(os.path.join(folder, b)) for b in buffers]).encode())
    return cache_path_for_hash(kind, key, ext)


def request(cfg, script, src, out, args=(), priority=PRIORITY_THUMB):
    """"ready" when `out` exists; "none" without Blender or source; "failed" when a run produced nothing;
    otherwise the job is queued once and "pending" is returned."""
    if not src or not os.path.isfile(src):
        return "none"
    if os.path.exists(out):
        return "ready"
    with _lock:
        if out in _failed:
            return "failed"
        if out not in _pending:
            if not blender(cfg):
                return "none"
            _pending.add(out)
            _queue.put((priority, -next(_seq), cfg, script, src, out, tuple(args)))     # newest first
            _start()
    return "pending"


def is_pending(out):
    """Whether a job for `out` waits or runs."""
    with _lock:
        return out in _pending


def run_now(cfg, script, src, out, args=(), timeout=JOB_TIMEOUT):
    """Runs the job on this thread (the send plan needs the answer now). True when `out` exists afterwards."""
    if os.path.exists(out):
        return True
    exe = blender(cfg)
    if not exe or not os.path.isfile(src):
        return False
    _execute(exe, script, src, out, args, timeout)
    return os.path.exists(out)


def reset():
    """Forget pending and failed jobs and start a fresh queue (tests). A worker still waiting on the old queue
    finds it empty and exits after its idle timeout."""
    global _queue, _worker
    with _lock:
        _pending.clear()
        _failed.clear()
        _queue = queue.PriorityQueue()
        _worker = None
        _close_runners()
        _no_runner.clear()


def _command(exe, script, src, out, args):
    return [exe, *BACKGROUND_ARGS, "--python", script, "--", src, out, *args]


def _runner_command(exe):
    return [exe, *BACKGROUND_ARGS, "--python-expr", RUNNER_EXPR]


class _Runner:
    """One Blender kept open for many jobs (RUNNER_EXPR). run() returns "done", "dead" (it exited) or "timeout"."""

    def __init__(self, exe):
        self.jobs = 0
        self.proc = subprocess.Popen(_runner_command(exe), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for raw in self.proc.stdout:
                self.lines.put(raw.decode("utf-8", "replace").strip())
        except (OSError, ValueError):
            pass
        self.lines.put(None)

    def alive(self):
        return self.proc.poll() is None

    def run(self, script, src, out, args, timeout):
        job_id = uuid.uuid4().hex
        line = json.dumps({"id": job_id, "script": script, "src": src, "out": out, "args": list(args)}) + "\n"
        try:
            self.proc.stdin.write(line.encode("ascii"))               # json escapes every non-ASCII path character
            self.proc.stdin.flush()
        except (OSError, ValueError):
            return "dead"
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return "timeout"
            try:
                got = self.lines.get(timeout=left)
            except queue.Empty:
                continue
            if got is None:
                return "dead"
            if got == f"ARTBENCH-JOB {job_id} done":
                self.jobs += 1
                return "done"

    def close(self, kill=False):
        try:
            if not kill:
                self.proc.stdin.write(b"\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=5)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if self.proc.poll() is None:
            self.proc.kill()
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


def _close_runners():
    for r in list(_runners.values()):
        r.close()
    _runners.clear()


def _run_job(exe, script, src, out, args):
    """Runs one job in the kept-open Blender for exe (started when needed, restarted after MAX_JOBS_PER_RUNNER jobs or
    a crash). A Blender that dies before finishing its first job cannot be kept open: from then on it is started
    once per job (_execute). A job that times out or crashes the kept-open Blender has failed."""
    if exe not in _no_runner:
        r = _runners.get(exe)
        if r is not None and (not r.alive() or r.jobs >= MAX_JOBS_PER_RUNNER):
            r.close()
            r = _runners.pop(exe, None) and None
        if r is None:
            try:
                r = _runners[exe] = _Runner(exe)
            except OSError:
                _no_runner.add(exe)
                r = None
        if r is not None:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            tmp = _temp_path(out)
            outcome = r.run(script, src, tmp, args, JOB_TIMEOUT)
            if outcome == "done":
                _finish(tmp, out)
                return
            _runners.pop(exe, None)
            r.close(kill=True)
            _remove(tmp)
            if outcome == "dead" and r.jobs == 0:
                _no_runner.add(exe)
            else:
                return
    _execute(exe, script, src, out, args, JOB_TIMEOUT)


def _finish(tmp, out):
    try:
        if os.path.exists(tmp) and not os.path.exists(out):      # another writer may have finished first
            store.replace_with_retry(tmp, out)
    except OSError:
        pass
    finally:
        _remove(tmp)


def _remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _temp_path(out):
    """A temp name unique to this process and thread that keeps the output's extension: Blender's still render
    appends the format extension when the path lacks one, and several writers may target the same output."""
    root, ext = os.path.splitext(out)
    return f"{root}.{os.getpid()}-{threading.get_ident()}.tmp{ext}"


def _execute(exe, script, src, out, args, timeout):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = _temp_path(out)
    try:
        subprocess.run(_command(exe, script, src, tmp, args), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        pass
    _finish(tmp, out)


def _start():
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_run, daemon=True)
        _worker.start()


def _run(idle=IDLE_SECONDS):
    global _worker
    while True:
        try:
            _priority, _n, cfg, script, src, out, args = _queue.get(timeout=idle)
        except queue.Empty:
            with _lock:                       # request() queues under the same lock: no job can slip in unseen
                if _queue.empty():
                    if _worker is threading.current_thread():
                        _worker = None        # the next request starts a fresh worker
                        _close_runners()      # an idle tool keeps no Blender running
                    return
            continue
        try:
            exe = blender(cfg)
            if exe and not os.path.exists(out):                   # run_now may have produced it meanwhile
                _run_job(exe, script, src, out, args)
        finally:
            with _lock:
                _pending.discard(out)
                if not os.path.exists(out):
                    _failed.add(out)
