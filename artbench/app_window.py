"""The page in a window of its own: a Chromium browser's app mode (no address bar, its own taskbar entry), with a
profile of its own so the window is its own process and remembers its size. The server stops when that window
closes; when the browser handed the window to a process already running, or no app browser exists, it stops after a
quiet spell instead. Also the log file for a run without a console (pythonw), the Windows desktop shortcut and
the native folder picker.
Process plumbing for the server's own start, so the transports may import it (ARCHITECTURE.md, Layer rules)."""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

from .errors import Unavailable

HANDOFF_SECONDS = 5          # a launched browser that exits sooner handed the window to a running process
IDLE_SECONDS = 300           # then the server stops after this long without a request (the page asks once a minute)
POLL_SECONDS = 5
WINDOW_SIZE = "1440,900"
SHORTCUT_NAME = "Artbench.lnk"

_WINDOWS = [                 # (environment variable, path under it), first found wins: Edge, then Chrome, then Chromium
    ("ProgramFiles(x86)", ("Microsoft", "Edge", "Application", "msedge.exe")),
    ("ProgramFiles", ("Microsoft", "Edge", "Application", "msedge.exe")),
    ("LOCALAPPDATA", ("Microsoft", "Edge", "Application", "msedge.exe")),
    ("ProgramFiles", ("Google", "Chrome", "Application", "chrome.exe")),
    ("ProgramFiles(x86)", ("Google", "Chrome", "Application", "chrome.exe")),
    ("LOCALAPPDATA", ("Google", "Chrome", "Application", "chrome.exe")),
    ("LOCALAPPDATA", ("Chromium", "Application", "chrome.exe")),
]
_MAC = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium"]
_NAMES = ["microsoft-edge", "microsoft-edge-stable", "google-chrome", "google-chrome-stable", "chromium",
          "chromium-browser"]


def find_browser(env=None, windows=None, isfile=os.path.isfile, which=shutil.which):
    """The browser that opens the window: ARTBENCH_BROWSER (a path or a name on PATH), then Edge, Chrome, Chromium.
    None when there is none."""
    env = os.environ if env is None else env
    windows = (os.name == "nt") if windows is None else windows
    chosen = env.get("ARTBENCH_BROWSER")
    if chosen:
        if isfile(chosen):
            return chosen
        found = which(chosen)
        if found:
            return found
    if windows:
        for var, parts in _WINDOWS:
            if env.get(var):
                path = os.path.join(env[var], *parts)
                if isfile(path):
                    return path
        return None
    for path in _MAC:
        if isfile(path):
            return path
    for name in _NAMES:
        found = which(name)
        if found:
            return found
    return None


def window_command(browser, url, profile, env=None):
    """The browser's command line; ARTBENCH_BROWSER_ARGS adds switches (space separated, e.g. --no-sandbox in a test
    container that runs as root)."""
    extra = ((os.environ if env is None else env).get("ARTBENCH_BROWSER_ARGS") or "").split()
    return [browser, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            f"--window-size={WINDOW_SIZE}", *extra]


def answering(url, timeout=1.0):
    """True when an Artbench already serves `url` (its /api/alive answers)."""
    try:
        with urllib.request.urlopen(url + "api/alive", timeout=timeout) as r:
            return json.loads(r.read()).get("app") == "artbench"
    except (OSError, ValueError):
        return False


def open_window(url, profile, find=None, popen=None, open_tab=None):
    """Opens one window without waiting for it; a normal tab when there is no app browser."""
    popen, open_tab = popen or subprocess.Popen, open_tab or webbrowser.open
    browser = (find or find_browser)()
    if browser:
        try:
            return popen(window_command(browser, url, profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
    open_tab(url)
    return None


def run(url, last_request, profile, find=None, popen=None, open_tab=None, clock=time.monotonic,
        sleep=time.sleep, handoff_s=HANDOFF_SECONDS, idle_s=IDLE_SECONDS, poll_s=POLL_SECONDS):
    """Opens the window and returns when the server should stop: "closed" (the window's process ended) or "idle"
    (no request for `idle_s` after a hand-off, a failed start or a plain tab). `last_request()` is the monotonic time
    of the server's last request."""
    popen, open_tab = popen or subprocess.Popen, open_tab or webbrowser.open
    browser = (find or find_browser)()
    proc = None
    if browser:
        try:
            started = clock()
            proc = popen(window_command(browser, url, profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            proc = None
    if proc is not None:
        proc.wait()
        if clock() - started >= handoff_s:
            return "closed"
    else:
        open_tab(url)
    while clock() - last_request() < idle_s:
        sleep(poll_s)
    return "idle"


def quiet_output(log_path):
    """Without a console (pythonw: no stdout / stderr) output goes to `log_path`; the open file, or None when a
    console is there."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    f = open(log_path, "a", encoding="utf-8", buffering=1)
    f.write(f"--- Artbench {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f
    return f


def windowless_python(python_exe):
    """pythonw.exe beside python.exe when it is there (no console window), else the same Python."""
    folder, name = os.path.split(python_exe)
    if name.lower() == "python.exe":
        w = os.path.join(folder, "pythonw.exe")
        if os.path.isfile(w):
            return w
    return python_exe


def _ps(text):
    return "'" + text.replace("'", "''") + "'"


def shortcut_script(target, arguments, workdir, icon):
    """PowerShell that writes Artbench.lnk on the user's real desktop (OneDrive or not) and prints its path."""
    lines = [
        "$desk = [Environment]::GetFolderPath('Desktop')",
        f"$path = Join-Path $desk {_ps(SHORTCUT_NAME)}",
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($path)",
        f"$s.TargetPath = {_ps(target)}",
        f"$s.Arguments = {_ps(arguments)}",
        f"$s.WorkingDirectory = {_ps(workdir)}",
        "$s.Description = 'Artbench'",
    ]
    if icon:
        lines.append(f"$s.IconLocation = {_ps(icon)}")
    lines += ["$s.Save()", "Write-Output $path"]
    return "; ".join(lines)


def _mac_launcher(tool_root, python_exe, home):
    """~/Desktop/Artbench.command: a double-click opens the app window from Terminal's launcher."""
    path = os.path.join(home, "Desktop", "Artbench.command")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f'#!/bin/bash\ncd "{tool_root}" || exit 1\nexec "{python_exe}" -m artbench --app\n')
    os.chmod(path, 0o755)
    return path


def create_shortcut(tool_root, python_exe, windows=None, run=subprocess.run, platform=None, home=None):
    """Writes the desktop shortcut that opens the app window; its path. Windows: a .lnk; a Mac: Artbench.command on
    the desktop; elsewhere `Unavailable`."""
    windows = (os.name == "nt") if windows is None else windows
    if not windows and (sys.platform if platform is None else platform) == "darwin":
        return _mac_launcher(tool_root, python_exe, home or os.path.expanduser("~"))
    if not windows:
        raise Unavailable("the desktop shortcut is made on Windows and macOS; elsewhere run: python -m artbench --app")
    icon = os.path.join(tool_root, "artbench", "web", "img", "artbench.ico")
    script = shortcut_script(windowless_python(python_exe), "-m artbench --app", tool_root, icon)
    done = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
               capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise Unavailable(f"the shortcut was not written: {(done.stderr or done.stdout).strip()}")
    return (done.stdout or "").strip().splitlines()[-1] if (done.stdout or "").strip() else os.path.join("Desktop", SHORTCUT_NAME)


# --- the native folder picker ------------------------------------------------------------------------------------

def _tk():
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


def _pick_folder_powershell(title, initial, run):
    """Windows' own folder dialog through PowerShell (the embeddable Python of the portable folder has no tkinter).
    Output is UTF-8 so non-ASCII folder names come back intact."""
    q = lambda s: "'" + str(s).replace("'", "''") + "'"
    script = "; ".join([
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
        "Add-Type -AssemblyName System.Windows.Forms",
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog",
        f"$d.Description = {q(title)}",
        "$d.ShowNewFolderButton = $false",
        *([f"$d.SelectedPath = {q(initial)}"] if initial else []),
        "$top = New-Object System.Windows.Forms.Form -Property @{TopMost = $true}",
        "if ($d.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }",
    ])
    done = run(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
               capture_output=True, timeout=3600)
    chosen = (done.stdout or b"").decode("utf-8", "replace").strip()
    return os.path.normpath(chosen) if done.returncode == 0 and chosen else None


def _pick_folder_osascript(title, initial, run):
    """macOS's own folder dialog through AppleScript: always there, and safe from the server's threads (Tk may open
    a window only on the main thread on a Mac). Cancel exits non-zero."""
    q = lambda s: '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
    script = f"POSIX path of (choose folder with prompt {q(title)}"
    if initial and os.path.isdir(initial):
        script += f" default location (POSIX file {q(initial)})"
    script += ")"
    done = run(["osascript", "-e", script], capture_output=True, timeout=3600)
    chosen = (done.stdout or b"").decode("utf-8", "replace").strip()
    return os.path.normpath(chosen) if done.returncode == 0 and chosen else None


def pick_folder(title="Choose a folder", initial=None, windows=None, run=None, use_tk=None, platform=None):
    """Native folder dialog on the machine running the server (local tool). None when cancelled. Finder's on a Mac;
    tkinter when the Python has it; else PowerShell's dialog on Windows."""
    if (sys.platform if platform is None else platform) == "darwin":
        return _pick_folder_osascript(title, initial, run or subprocess.run)
    use_tk = _tk() if use_tk is None else use_tk
    if not use_tk:
        if (os.name == "nt") if windows is None else windows:
            return _pick_folder_powershell(title, initial, run or subprocess.run)
        return None
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        chosen = filedialog.askdirectory(title=title, initialdir=initial or os.path.expanduser("~"), mustexist=True)
    finally:
        root.destroy()
    return os.path.normpath(chosen) if chosen else None
