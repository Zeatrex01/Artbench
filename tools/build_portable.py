"""Builds the portable Artbench for Windows: a folder with its own Python (python.org's embeddable zip, nothing to
install), zipped. Double-clicking Artbench.bat opens Artbench in a window of its own; settings are written inside the
folder, so it travels whole. A build tool, not part of the package.

    python tools/build_portable.py                        # downloads the embeddable Python once, writes dist/...zip
    python tools/build_portable.py --python-zip embed.zip # an embeddable zip you already have
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
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


def build(out_zip, python_zip, log=sys.stdout):
    """Writes the portable zip (one top folder, Artbench/) and returns its path."""
    from artbench import cli
    with tempfile.TemporaryDirectory() as tmp:
        top = os.path.join(tmp, TOP)
        python_dir = os.path.join(top, "python")
        os.makedirs(python_dir)
        with zipfile.ZipFile(python_zip) as z:
            z.extractall(python_dir)
        _add_parent_to_pth(python_dir)
        shutil.copytree(os.path.join(ROOT, "artbench"), os.path.join(top, "artbench"), ignore=SKIP)
        shutil.copytree(os.path.join(ROOT, "blender_addon"), os.path.join(top, "blender_addon"), ignore=SKIP)
        cli.main(["addon", os.path.join(top, "blender_addon", "artbench_bridge.zip")], out=io.StringIO())
        for name in FILES:
            shutil.copy2(os.path.join(ROOT, name), os.path.join(top, name))
        for name, source in USER_FILES.items():
            with open(os.path.join(ROOT, source), encoding="utf-8") as f:
                text = f.read().replace("{version}", __version__)
            with open(os.path.join(top, name), "w", encoding="utf-8", newline="\r\n") as f:
                f.write(text)
        for name, text in LAUNCHERS.items():
            with open(os.path.join(top, name), "w", encoding="ascii", newline="\r\n") as f:
                f.write(text)
        _check_imports(top)
        os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for d, dirs, names in os.walk(top):
                dirs.sort()
                for name in sorted(names):
                    full = os.path.join(d, name)
                    z.write(full, os.path.relpath(full, tmp).replace(os.sep, "/"))
    log.write(f"Wrote {out_zip} ({os.path.getsize(out_zip) // 1024} KB)\n"
              "Unzip it anywhere (not inside a game project), then double-click Artbench\\Artbench.bat.\n")
    return out_zip


def main(argv=None):
    p = argparse.ArgumentParser(prog="python tools/build_portable.py")
    p.add_argument("--python-zip", help="an embeddable Python zip you already have (else it is downloaded)")
    p.add_argument("--python-version", default=PYTHON_VERSION)
    p.add_argument("--out", default=OUT)
    a = p.parse_args(argv)
    python_zip = a.python_zip or download(a.python_version, os.path.join(ROOT, "dist", "cache"))
    build(a.out, python_zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
