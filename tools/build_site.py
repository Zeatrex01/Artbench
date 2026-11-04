"""Builds the download page for GitHub Pages: site/ with the release to download filled in, plus the pictures the
README uses (docs/images) and the app's icon. A build tool, not part of the package.

    python tools/build_site.py [out_dir] [--tag v0.1.0]     # default out: dist/site, default tag: v<__version__>

The Pages workflow passes the newest published release's tag, so the button always fetches a zip that exists."""
import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from artbench import __version__  # noqa: E402

REPO = "https://github.com/Zeatrex01/Artbench"
TAG = re.compile(r"^v(\d+\.\d+\.\d+(?:[a-z0-9.-]*)?)$")


def build(out_dir, tag=None):
    """Writes the page into out_dir and returns its index.html path."""
    tag = tag or f"v{__version__}"
    m = TAG.match(tag)
    if not m:
        raise ValueError(f"not a version tag: {tag} (expected v<version>, e.g. v0.1.0)")
    version = m.group(1)
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(os.path.join(ROOT, "site"), out_dir)
    shutil.copytree(os.path.join(ROOT, "docs", "images"), os.path.join(out_dir, "images"))
    shutil.copy2(os.path.join(ROOT, "artbench", "web", "img", "favicon.svg"), os.path.join(out_dir, "favicon.svg"))
    open(os.path.join(out_dir, ".nojekyll"), "w").close()               # serve the files as they are
    index = os.path.join(out_dir, "index.html")
    with open(index, encoding="utf-8") as f:
        html = f.read()
    for key, value in {"VERSION": version, "TAG": tag, "REPO": REPO,
                       "ZIP_URL": f"{REPO}/releases/download/{tag}/Artbench-{version}-windows-x64.zip",
                       "ADDON_URL": f"{REPO}/releases/download/{tag}/artbench_bridge.zip"}.items():
        html = html.replace("{{" + key + "}}", value)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    return index


def main(argv=None):
    p = argparse.ArgumentParser(prog="python tools/build_site.py")
    p.add_argument("out", nargs="?", default=os.path.join(ROOT, "dist", "site"))
    p.add_argument("--tag", default=None, help="the release whose zip the button downloads (default v<__version__>)")
    a = p.parse_args(argv)
    print("Wrote", build(a.out, a.tag))
    return 0


if __name__ == "__main__":
    sys.exit(main())
