"""Builds the portable Artbench: a folder with its own Python (nothing to install), zipped. On Windows python.org's
embeddable zip and Artbench.bat; on a Mac python-build-standalone's relocatable Python (pinned by address and SHA-256,
trimmed of what Artbench never uses) and Artbench.command. Double-clicking the launcher opens Artbench in a window of
its own; settings are written inside the folder, so it travels whole. A build tool, not part of the package; both are
built on any system (the Mac one needs no Mac).

    python tools/build_portable.py                          # Windows: downloads the embeddable Python once
    python tools/build_portable.py --python-zip embed.zip   # an embeddable zip you already have
    python tools/build_portable.py --target mac-arm64       # a Mac with Apple silicon (M1 and later)
    python tools/build_portable.py --target mac-x64         # a Mac with an Intel chip
"""
import argparse
import glob
import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PYTHON_VERSION = "3.12.10"
from artbench import __version__  # noqa: E402

OUT = os.path.join(ROOT, "dist", f"Artbench-{__version__}-windows-x64.zip")
TOP = "Artbench"
FILES = ["README_TR.md", "THIRD_PARTY_NOTICES.md", "ArtbenchSetup.bat"]
# For the people who download the build: the licence, the credit and a short start guide, as .txt in Windows line
# ends so Notepad shows them right.
USER_FILES = {"LICENSE.txt": "LICENSE", "NOTICE.txt": "NOTICE", "README.txt": os.path.join("tools", "portable", "README.txt")}
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", ".*")

LAUNCHERS = {
    # No console: pythonw, started detached. Closing the window stops Artbench.
    "Artbench.bat": '@echo off\ncd /d "%~dp0"\nstart "" "%~dp0python\\pythonw.exe" -m artbench --app\n',
    "CreateShortcut.bat": '@echo off\ncd /d "%~dp0"\n"%~dp0python\\python.exe" -m artbench shortcut\npause\n',
}


# python-build-standalone (Astral): relocatable CPython builds; install_only is the plain install tree under python/.
PBS_TAG = "20250409"
MAC_PYTHON = {"arm64": ("aarch64-apple-darwin", "2d6477ecd10191675b7e7979e4b9e811fef36833ef3a7f3aa445eec305ce59a2"),
              "x64": ("x86_64-apple-darwin", "d0d51fa22c0e99b58de1b1b4baeca467d6fd0a1424c7509ea280c0796306c481")}
MAC_CHIPS = {"arm64": ("Apple silicon", "a Mac with Apple silicon (M1 and later)"),
             "x64": ("Intel", "a Mac with an Intel chip")}
# Parts of the Python Artbench never uses (Tk: the folder dialog is macOS's own; pip, tests, headers, manuals).
MAC_TRIM = ["python/include", "python/share", "python/lib/pkgconfig", "python/lib/python3.12/test",
            "python/lib/python3.12/idlelib", "python/lib/python3.12/tkinter", "python/lib/python3.12/turtledemo",
            "python/lib/python3.12/ensurepip", "python/lib/python3.12/site-packages/pip",
            "python/lib/python3.12/lib-dynload/_tkinter*", "python/lib/tcl*", "python/lib/tk*", "python/lib/itcl*",
            "python/lib/thread*", "python/lib/libtcl*", "python/lib/libtk*", "python/bin/pip*", "python/bin/idle*",
            "python/bin/2to3*", "python/bin/pydoc*"]
MAC_LAUNCHERS = {
    # The folder came from the internet: macOS marks every file in it and would stop the Python inside, so the launcher
    # clears the mark on its own folder (the person allowed the launcher itself with right-click > Open).
    "Artbench.command": '#!/bin/bash\ncd "$(dirname "$0")" || exit 1\nxattr -dr com.apple.quarantine . 2>/dev/null\n'
                        "exec ./python/bin/python3.12 -m artbench --app\n",
    "CreateShortcut.command": '#!/bin/bash\ncd "$(dirname "$0")" || exit 1\nxattr -dr com.apple.quarantine . 2>/dev/null\n'
                              './python/bin/python3.12 -m artbench shortcut\nread -r -p "Press Return to close."\n',
}


def mac_out(arch):
    return os.path.join(ROOT, "dist", f"Artbench-{__version__}-macos-{arch}.zip")


def mac_url(arch):
    triple = MAC_PYTHON[arch][0]
    return (f"https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_TAG}/"
            f"cpython-{PYTHON_VERSION}+{PBS_TAG}-{triple}-install_only.tar.gz")


def _fetch(url, path):
    with urllib.request.urlopen(url, timeout=300) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)


def download_mac(arch, cache_dir, fetch=_fetch):
    """The Mac Python for `arch`, downloaded once into `cache_dir` and checked against its pinned SHA-256 (ValueError,
    and nothing kept, when it differs)."""
    os.makedirs(cache_dir, exist_ok=True)
    url, expected = mac_url(arch), MAC_PYTHON[arch][1]
    path = os.path.join(cache_dir, url.rsplit("/", 1)[1])
    if not os.path.isfile(path):
        fetch(url, path + ".part")
        with open(path + ".part", "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
        if got != expected:
            os.remove(path + ".part")
            raise ValueError(f"{url} has SHA-256 {got}, not the pinned {expected}")
        os.replace(path + ".part", path)
    return path


def embed_url(version):
    return f"https://www.python.org/ftp/python/{version}/python-{version}-embed-amd64.zip"


def download(version, cache_dir):
    """The embeddable zip for `version`, downloaded once into `cache_dir`."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"python-{version}-embed-amd64.zip")
    if not os.path.isfile(path):
        with urllib.request.urlopen(embed_url(version), timeout=120) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(path + ".part", path)
    return path


def _add_parent_to_pth(python_dir):
    """The embeddable Python reads its path from python3XX._pth only; ".." puts Artbench/ (artbench's folder) on it."""
    pths = [n for n in os.listdir(python_dir) if n.endswith("._pth")]
    if len(pths) != 1:
        raise ValueError("not an embeddable Python zip: it has no python3XX._pth")
    path = os.path.join(python_dir, pths[0])
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if ".." not in lines:
        lines.insert(lines.index(".") + 1 if "." in lines else len(lines), "..")
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")


def _check_imports(folder):
    """The package imports with the standard library alone: no site, no PYTHONPATH (the embeddable Python's world)."""
    code = ("import sys; sys.path.insert(0, '.'); "
            "import artbench.server, artbench.mcp_server, artbench.cli, artbench.app_window")
    done = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", code], cwd=folder, capture_output=True, text=True,
                          timeout=120)
    if done.returncode != 0:
        raise RuntimeError("the package does not import on the standard library alone:\n" + done.stderr)


def _package(top, files, user_files, newline, words=None):
    """Artbench itself, the Blender add-on (and its zip), and the files for the people who download it."""
    from artbench import cli
    shutil.copytree(os.path.join(ROOT, "artbench"), os.path.join(top, "artbench"), ignore=SKIP)
    shutil.copytree(os.path.join(ROOT, "blender_addon"), os.path.join(top, "blender_addon"), ignore=SKIP)
    cli.main(["addon", os.path.join(top, "blender_addon", "artbench_bridge.zip")], out=io.StringIO())
    for name in files:
        shutil.copy2(os.path.join(ROOT, name), os.path.join(top, name))
    for name, source in user_files.items():
        with open(os.path.join(ROOT, source), encoding="utf-8") as f:
            text = f.read().replace("{version}", __version__)
        for key, value in (words or {}).items():
            text = text.replace("{" + key + "}", value)
        with open(os.path.join(top, name), "w", encoding="utf-8", newline=newline) as f:
            f.write(text)


def _zip(tmp, top, out_zip):
    """Zips Artbench/ with each file's mode (a program stays runnable once unzipped) and links kept as links."""
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as z:   # pre-1980 times: 1980
        for d, dirs, names in os.walk(top):
            dirs.sort()
            for name in sorted(names + [x for x in dirs if os.path.islink(os.path.join(d, x))]):
                full = os.path.join(d, name)
                arc = os.path.relpath(full, tmp).replace(os.sep, "/")
                if os.path.islink(full):
                    info = zipfile.ZipInfo(arc)
                    info.external_attr = (stat.S_IFLNK | 0o755) << 16
                    z.writestr(info, os.readlink(full))
                else:
                    z.write(full, arc)


def build(out_zip, python_zip, log=sys.stdout):
    """Writes the portable zip for Windows (one top folder, Artbench/) and returns its path."""
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, TOP)
        python_dir = os.path.join(top, "python")
        os.makedirs(python_dir)
        with zipfile.ZipFile(python_zip) as z:
            z.extractall(python_dir)
        _add_parent_to_pth(python_dir)
        _package(top, FILES, USER_FILES, "\r\n")
        for name, text in LAUNCHERS.items():
            with open(os.path.join(top, name), "w", encoding="ascii", newline="\r\n") as f:
                f.write(text)
        _check_imports(top)
        _zip(tmp, top, out_zip)
    log.write(f"Wrote {out_zip} ({os.path.getsize(out_zip) // 1024} KB)\n"
              "Unzip it anywhere (not inside a game project), then double-click Artbench\\Artbench.bat.\n")
    return out_zip


def build_mac(out_zip, python_tar, arch, log=sys.stdout):
    """Writes the portable zip for a Mac (`arch` arm64 | x64) from python-build-standalone's install_only archive."""
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, TOP)
        os.makedirs(top)
        with tarfile.open(python_tar) as t:
            t.extractall(top, filter="tar")              # python/...: modes and links as the archive has them
        for pattern in MAC_TRIM:
            for path in glob.glob(os.path.join(top, *pattern.split("/"))):
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        chip, chip_long = MAC_CHIPS[arch]
        _package(top, [n for n in FILES if not n.endswith(".bat")],
                 {**{k: v for k, v in USER_FILES.items() if k != "README.txt"},
                  "README.txt": os.path.join("tools", "portable", "README-mac.txt")}, "\n", {"chip": chip, "chip_long": chip_long})
        for name, text in MAC_LAUNCHERS.items():
            path = os.path.join(top, name)
            with open(path, "w", encoding="ascii", newline="\n") as f:
                f.write(text)
            os.chmod(path, 0o755)
        _check_imports(top)
        _zip(tmp, top, out_zip)
    log.write(f"Wrote {out_zip} ({os.path.getsize(out_zip) // 1024} KB), for {chip_long}\n"
              "Unzip it anywhere (not inside a game project), then double-click Artbench/Artbench.command.\n")
    return out_zip


def main(argv=None):
    p = argparse.ArgumentParser(prog="python tools/build_portable.py")
    p.add_argument("--target", choices=["windows", "mac-arm64", "mac-x64"], default="windows")
    p.add_argument("--python-zip", help="Windows: an embeddable Python zip you already have (else it is downloaded)")
    p.add_argument("--python-version", default=PYTHON_VERSION, help="Windows only; the Mac Python is pinned")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    cache = os.path.join(ROOT, "dist", "cache")
    if a.target.startswith("mac-"):
        arch = a.target[len("mac-"):]
        build_mac(a.out or mac_out(arch), download_mac(arch, cache), arch)
        return 0
    python_zip = a.python_zip or download(a.python_version, cache)
    build(a.out or OUT, python_zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
