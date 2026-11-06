"""Local web server for the inventory page: http://127.0.0.1:8765. Reads the projects, serves the page and a small
JSON API; the page polls /api/state and the server rescans when it is asked (the scan is cheap)."""
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import app_window, config, github_link, mcp_link, ops, workspace

page = ops.page                         # the page's own routes (not operations)

LAST_REQUEST = [time.monotonic()]       # when the last request came (the app window's quiet stop)

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
_lock = threading.Lock()
API_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024 * 1024    # refused before reading: the project id is inside the body
DRAIN_SECONDS = 2                       # how long a refused body is read and dropped
STATUS = {"bad_request": 400, "outside_root": 400, "not_found": 404, "needs_force": 409, "warnings": 409, "conflict": 409,
          "wrong_mode": 409,
          "busy": 423, "unavailable": 503, "internal": 500}
STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2",
                ".webmanifest": "application/manifest+json"}


def static_file(url_path):
    """(absolute file path, content type) for a page asset under web/, or None when outside it or unknown."""
    rel = "index.html" if url_path in ("", "/") else url_path.lstrip("/")
    full = os.path.normpath(os.path.join(WEB, rel))
    if not full.startswith(os.path.normpath(WEB) + os.sep) or not os.path.isfile(full):
        return None
    ctype = STATIC_TYPES.get(os.path.splitext(full)[1].lower())
    return (full, ctype) if ctype else None


class _Body(dict):
    """A page route's JSON body: a missing field is the caller's mistake (400), not a server error."""
    def __missing__(self, key):
        raise ValueError(f"missing field: {key}")


def _is_v1(path):
    return path == "/api/v1" or path.startswith("/api/v1/")



class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):           # quiet
        pass

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), code)

    def _send(self, body, code):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _foreign(self):
        """True for a request another web site made through the owner's browser (or a DNS-rebound name): only the
        server's own address may call it. Local programs (Unity, curl, CLIs) send no Origin and the right Host."""
        port = self.server.server_address[1]
        own = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if (self.headers.get("Host") or "").lower() not in own:
            return True
        origin = self.headers.get("Origin")
        return origin is not None and origin.lower() not in {"http://" + h for h in own}

    def _v1(self, path, args=None, error=None, read_only=False):
        """/api/v1: the versioned operation contract. GET /api/v1 describes it; /api/v1/<operation> runs one."""
        name = path[len("/api/v1"):].strip("/")
        if not name:
            return self._json({"api": "artbench", "version": API_VERSION, "engine_report_schema": ops.page.ENGINE_REPORT_SCHEMA,
                               "operations": ops.describe()})
        try:
            if error:
                raise ops.OpError("bad_request", error)
            op = ops.OPS.get(name)
            if op is not None and read_only:
                if op.write:
                    raise ops.OpError("bad_request", f"{name} changes files: use POST")
                args = ops.coerce(op, args)
            with _lock:
                result = ops.call(name, args)
            try:
                body = json.dumps({"ok": True, "result": result}, ensure_ascii=False).encode("utf-8")
            except (TypeError, ValueError) as e:
                raise ops.OpError("internal", f"the result could not be encoded as JSON: {e}") from e
            self._send(body, 200)
        except ops.OpError as e:
            self._json({"ok": False, "error": {"code": e.code, "message": e.message, "detail": e.detail}}, STATUS.get(e.code, 500))

    def do_GET(self):
        LAST_REQUEST[0] = time.monotonic()
        if self._foreign():
            return self._refuse(403, "forbidden")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if _is_v1(u.path):
            return self._v1(u.path, {k: v[-1] for k, v in q.items()}, read_only=True)
        try:
            if not u.path.startswith("/api/"):
                hit = static_file(u.path)
                if not hit:
                    return self._json({"error": "not found"}, 404)
                with open(hit[0], "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", hit[1])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/api/mcp":
                self._json(mcp_link.mcp_status())
            elif u.path == "/api/alive":
                self._json({"ok": True, "app": "artbench", "version": config.VERSION, "author": config.AUTHOR})
            elif u.path == "/api/projects":
                self._json(page.projects())
            elif u.path == "/api/projects/github":
                self._json(github_link.github_status(page.project(q["project"][0])))
            elif u.path == "/api/pulse":
                self._json(page.pulse(page.project(q["project"][0])))
            elif u.path == "/api/state":
                with _lock:
                    self._json(page.state(page.project(q["project"][0])))
            elif u.path == "/api/changes":
                self._json(page.recent_changes(page.project(q["project"][0]), int(q.get("limit", ["300"])[0])))
            elif u.path == "/api/send/plan":
                with _lock:
                    self._json(page.send_plan(page.project(q["project"][0]), q["id"][0]))
            elif u.path == "/api/meta/snapshot":
                # Metadata snapshot of a model file; 202 while Blender works, 404 when it cannot.
                state, snap = page.meta_snapshot(page.project(q["project"][0]), q.get("path", [None])[0])
                self._json({"state": state, "snapshot": snap}, 200 if state == "ready" else 202 if state == "pending" else 404)
            elif u.path == "/api/meta/diff":
                with _lock:
                    result = page.meta_diff(page.project(q["project"][0]), q["id"][0])
                self._json(result, 202 if result["state"] == "pending" else 200)
            elif u.path == "/api/pull/plan":
                with _lock:
                    self._json(page.pull_plan(page.project(q["project"][0]), q["id"][0]))
            elif u.path == "/api/refresh":
                with _lock:
                    self._json(page.refresh(page.project(q["project"][0])))
            elif u.path == "/api/graph":
                with _lock:
                    self._json(page.reference_graph(page.project(q["project"][0])))
            elif u.path == "/api/tasks":
                self._json(page.task_list(page.project(q["project"][0]), archived=q.get("archived", ["0"])[0] == "1"))
            elif u.path == "/api/thumb":
                # A preview (model render, texture image); 202 while Blender renders it, 404 if it cannot.
                state, png, ctype = page.thumb(page.project(q["project"][0]), q.get("path", [None])[0])
                if state == "ready":
                    with open(png, "rb") as f:
                        body = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "max-age=86400")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self._json({"state": state}, 202 if state == "pending" else 404)
            elif u.path == "/api/projects/progress":   # read while a connect holds the lock: no lock here
                self._json(workspace.connect_progress())
            elif u.path == "/api/projects/check":
                self._json(workspace.check_engine(q.get("engine_root", [""])[0]))
            elif u.path == "/api/history":
                self._json(page.history(page.project(q["project"][0])))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001  (shown on the page)
            self._error(e)

    def _refuse(self, status, message):
        """A request refused before any route runs; /api/v1 callers get their envelope."""
        if _is_v1(urlparse(self.path).path):
            code = "not_found" if status == 404 else "bad_request"
            return self._json({"ok": False, "error": {"code": code, "message": message, "detail": None}}, status)
        return self._json({"error": message}, status)

    def _drain(self, length):
        """Read and drop the unread body after a refusal (bounded in time), so a client still sending it reads the
        answer instead of a connection reset; a client that lies about the length costs at most DRAIN_SECONDS."""
        deadline = time.monotonic() + DRAIN_SECONDS
        try:
            self.connection.settimeout(DRAIN_SECONDS)
            while length > 0 and time.monotonic() < deadline:
                chunk = self.rfile.read1(min(length, 1 << 20))
                if not chunk:
                    break
                length -= len(chunk)
        except OSError:
            pass

    def do_POST(self):
        LAST_REQUEST[0] = time.monotonic()
        if self._foreign():
            return self._refuse(403, "forbidden")
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            return self._refuse(415, "send JSON with Content-Type: application/json")
        u = urlparse(self.path)
        lengths = [v.strip() for v in self.headers.get_all("Content-Length") or []]
        if self.headers.get("Transfer-Encoding") or not lengths:
            self.close_connection = True     # a body we will not read must not be parsed as the next request
            return self._refuse(411, "send Content-Length; chunked bodies are not supported")
        header = lengths[0]
        if len(set(lengths)) > 1 or not (header.isascii() and header.isdecimal()):
            self.close_connection = True
            return self._refuse(400, "Content-Length must be one non-negative number")
        length = int(header)
        if length > MAX_REQUEST_BYTES:
            self.close_connection = True
            self._refuse(413, f"request too large ({length} bytes, limit {MAX_REQUEST_BYTES})")
            return self._drain(length)
        raw = self.rfile.read(length) or b"{}"
        if _is_v1(u.path):
            try:
                args = json.loads(raw)
            except ValueError:
                return self._v1(u.path, error="body is not valid JSON")
            return self._v1(u.path, args)
        try:
            body = json.loads(raw)
        except ValueError:
            return self._json({"error": "body is not valid JSON"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "body must be a JSON object"}, 400)
        body = _Body(body)
        try:
            if u.path.startswith("/api/projects/") or u.path == "/api/pick_folder":
                return self._workspace(u.path, body)
            if u.path == "/api/mcp/register":         # machine-wide; Claude Code may take a while: no lock
                if body.get("tool") != "claude":
                    return self._json({"error": "only Claude Code is added from here; copy the line for the others"}, 400)
                return self._json(mcp_link.register_claude())
            with _lock:
                cfg = page.project(body["project"])
                if u.path == "/api/move":
                    self._json({"ok": True, "path": page.move(cfg, body["id"], body["state"])})
                elif u.path == "/api/meta":
                    page.set_meta(cfg, body["id"], body)
                    self._json({"ok": True})
                elif u.path == "/api/reveal":
                    page.reveal(body["path"])
                    self._json({"ok": True})
                elif u.path == "/api/open":
                    page.open_path(body["path"])
                    self._json({"ok": True})
                elif u.path == "/api/send":
                    self._json(page.send(cfg, body["id"], bool(body.get("accept_warnings")), bool(body.get("force")), body.get("files"),
                                         body.get("expect")))
                elif u.path == "/api/pull":
                    self._json(page.pull(cfg, body["id"], bool(body.get("force")), body.get("files"), body.get("expect")))
                elif u.path == "/api/changes/seen":
                    self._json(page.mark_seen(cfg))
                elif u.path == "/api/tasks":
                    self._json(page.task(cfg, body))
                else:
                    self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            self._error(e)

    def _error(self, exc):
        """The page's routes answer {error: message} with the same status the /api/v1 codes use (409 for a transfer
        that needs force or met a change, 404 for an unknown project or item, ...)."""
        err = ops.to_error(exc)
        self._json({"error": err.message}, STATUS.get(err.code, 500))

    def _workspace(self, path, body):
        """Project registry routes: they have no project context yet."""
        if path == "/api/pick_folder":        # native dialog: must not hold the lock while the user browses
            self._json({"path": app_window.pick_folder(body.get("title", "Choose a folder"), body.get("initial"))})
            return
        with _lock:
            if path == "/api/projects/connect":
                cfg = workspace.connect(body["name"], body["engine_root"], body["art_parent"], body.get("art_name"),
                                        body.get("categories"), body.get("create", True))
                self._json({"ok": True, "id": cfg["id"], "config_path": cfg["config_path"], "art_root": cfg["art_root"]})
            elif path == "/api/projects/connect_project":
                cfg = workspace.connect_project(body["engine_path"], body.get("name"))
                self._json({"ok": True, "id": cfg["id"], "config_path": cfg["config_path"], "mode": cfg["mode"]})
            elif path == "/api/projects/link":
                cfg = workspace.link(body["path"])
                self._json({"ok": True, "id": cfg["id"], "config_path": cfg["config_path"], "art_root": cfg["art_root"]})
            elif path == "/api/projects/detach":
                self._json({"ok": workspace.detach(body["id"])})
            elif path == "/api/projects/hide_folder":
                self._json({"ok": True, "hidden": workspace.hide_folder(body["project"], body["folder"], bool(body.get("hidden", True)))})
            elif path == "/api/projects/github":
                self._json({"ok": True, **github_link.set_github_account(body["project"], body.get("account") or "")})
            else:
                self._json({"error": "not found"}, 404)


def _port(argv):
    if "--port" in argv:
        i = argv.index("--port")
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            return int(argv[i + 1])
        raise SystemExit("--port needs a number")
    return config.PORT


def main(argv=None):
    """Serve the page. --no-browser skips opening a tab (restarts, scripts); --app opens the page in a window of its
    own and stops when it closes (app_window); --port N serves on another port."""
    argv = sys.argv[1:] if argv is None else argv
    port = _port(argv)
    url = f"http://127.0.0.1:{port}/"
    app = "--app" in argv
    profile = os.path.join(config.TOOL_ROOT, ".cache", "app-window")
    if app:
        app_window.quiet_output(os.path.join(config.TOOL_ROOT, ".cache", "artbench.log"))
        if app_window.answering(url):        # an Artbench already serves: one more window, nothing else
            app_window.open_window(url, profile)
            return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Artbench:", url, "(close the window to stop)" if app else "(Ctrl+C to stop)")
    if app:
        LAST_REQUEST[0] = time.monotonic()
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            reason = app_window.run(url, lambda: LAST_REQUEST[0], profile)
            print("Artbench stopped:", "the window closed" if reason == "closed" else "no request for a while")
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
        return
    if "--no-browser" not in argv:
        threading.Timer(0.6, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
