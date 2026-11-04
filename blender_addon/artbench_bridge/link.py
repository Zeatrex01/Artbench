"""The link to the Artbench server on this machine. Every few seconds it tells Artbench which .blend is open; Artbench answers
with the project that file belongs to, the file's id there and the models made from it. Nothing else in the add-on
needs this to work: notes are kept in the .blend whether Artbench answers or not.

Network calls run on a background thread so a slow or missing server never stalls Blender, and they never go through
a proxy: Artbench runs on this machine, and a proxy set for the whole system (common on studio machines) would otherwise
swallow them."""
import json
import os
import threading
import time
import urllib.error
import urllib.request

import bpy

INTERVAL = 5.0                       # seconds between reports; Artbench calls Blender closed after 15 s of silence
TIMEOUT = 2.0                        # seconds one request may take
DEFAULT_URL = "http://127.0.0.1:8765"
STATE = {"connected": None, "project": None, "asset": None, "models": [], "error": None, "busy": False,
         "checked": None, "version": 0}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))    # never through a proxy: the server is local
_drawn = {"version": -1}


class ArtbenchError(Exception):
    """Artbench could not be reached, or it refused the call; the message says which, in plain words."""


def server_url():
    """ARTBENCH_URL when set (scripts, a server on another port), else the add-on preference, else the default."""
    if os.environ.get("ARTBENCH_URL"):
        return os.environ["ARTBENCH_URL"].rstrip("/")
    try:
        return bpy.context.preferences.addons[__package__].preferences.url.strip().rstrip("/") or DEFAULT_URL
    except (AttributeError, KeyError):
        return DEFAULT_URL


def call(url, operation, args):
    """One Artbench operation over /api/v1; its result, or ArtbenchError with a readable reason."""
    req = urllib.request.Request(f"{url}/api/v1/{operation}", json.dumps(args).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    try:
        with _OPENER.open(req, timeout=TIMEOUT) as r:
            answer = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message") or e.reason
        except (ValueError, AttributeError):
            msg = e.reason
        raise ArtbenchError(f"Artbench refused it: {msg}") from None
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        why = "nothing is listening there" if isinstance(reason, ConnectionRefusedError) else str(reason)
        raise ArtbenchError(f"No answer from {url} ({why})") from None
    except (OSError, ValueError) as e:
        raise ArtbenchError(f"No answer from {url} ({e})") from None
    if not answer.get("ok"):
        raise ArtbenchError(f"Artbench refused it: {(answer.get('error') or {}).get('message', answer)}")
    return answer.get("result")


def payload(closing=False):
    """What one report carries (read on the main thread: bpy is not safe to touch from others)."""
    return {"file": bpy.data.filepath or "", "blender": bpy.app.version_string, "pid": os.getpid(), "closing": closing}


def _changed(**fields):
    STATE.update(fields)
    STATE["version"] += 1


def send_report(url, body):
    """Reports the open file; returns Artbench's answer and updates STATE. Raises ArtbenchError when Artbench is not there."""
    try:
        result = call(url, "blender_report", body) or {}
    except ArtbenchError as e:
        _changed(connected=False, project=None, asset=None, models=[], error=str(e), checked=time.time())
        raise
    _changed(connected=True, project=result.get("project"), asset=result.get("asset"), models=result.get("models") or [],
             error=None, checked=time.time())
    return result


def refresh_now(url=None, body=None):
    """One report, on the calling thread (tests and the Test connection button)."""
    url = url or server_url()
    return send_report(url, body if body is not None else payload())


def _in_background(work):
    def run():
        try:
            work()
        except Exception:  # noqa: BLE001  (STATE carries the reason; Blender carries on)
            pass
        finally:
            STATE["busy"] = False
    STATE["busy"] = True
    threading.Thread(target=run, daemon=True).start()


def redraw():
    """Panels draw only when something asks them to: after a change from the background thread, ask."""
    if _drawn["version"] == STATE["version"]:
        return
    _drawn["version"] = STATE["version"]
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type in ("VIEW_3D", "PREFERENCES"):
                area.tag_redraw()


def tick():
    url, body = server_url(), payload()
    if not STATE["busy"]:
        _in_background(lambda: refresh_now(url, body))
    redraw()
    return 0.5 if STATE["busy"] else INTERVAL


def on_exit():
    try:
        call(server_url(), "blender_report", payload(closing=True))
    except Exception:  # noqa: BLE001  (Blender is quitting; Artbench will see the silence anyway)
        pass


def status_lines():
    """[(icon, text, alert)] the panel and the preferences show for the link: plain words, the reason when it fails."""
    if STATE["connected"] is None:
        return [("TIME", "Looking for Artbench…", False)]
    if not STATE["connected"]:
        return [("ERROR", "Not connected to Artbench", True), ("BLANK1", STATE["error"] or "", True),
                ("INFO", "Is Artbench open? Check the address in the add-on preferences.", False),
                ("BLANK1", "Notes work without it; they are kept in the .blend.", False)]
    lines = [("CHECKMARK", "Connected to Artbench", False)]
    if STATE["project"]:
        lines.append(("FILE_FOLDER", f"Project: {STATE['project']}", False))
        lines.append(("FILE_BLEND", STATE["asset"] or os.path.basename(bpy.data.filepath), False))
    elif bpy.data.filepath:
        lines += [("QUESTION", "This file is in no Artbench project", False),
                  ("BLANK1", "Save it in your art folder (Blend/) to track it.", False)]
    else:
        lines.append(("QUESTION", "Save the file to link it to a project", False))
    return lines
