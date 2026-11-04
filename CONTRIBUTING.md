# Contributing

Thanks for looking. Artbench is small on purpose; these rules keep it that way.

- **Python 3.11+, standard library only.** The page is plain HTML, CSS and JavaScript modules; no build step.
- **Every behaviour change is tested before it lands.** The maintainer runs the full test suite on each change.
- **Architecture first.** Read [`ARCHITECTURE.md`](ARCHITECTURE.md): layers, schemas, the HTTP API, the MCP tools.
  Keep to its layer rules; a module stays under 450 lines.
- **The page speaks English by default**, with Turkish beside it: its words come from `artbench/web/js/i18n.js`, not
  from text written into the code.
- **Nothing is ever overwritten or deleted silently** in a user's project: moves only, replaced files to
  `_Archive/<date>/`, every change a history line.
- **Nothing machine-specific in code**: paths come from `art_inventory.json` and `projects.json`.

Contributions are taken under the same licence as Artbench (Apache-2.0 with the Commons Clause; the Blender add-on
Apache-2.0 alone).

Bugs and ideas: open an issue with what you did, what you expected and what happened (and the engine and OS).

## Releasing

1. Set the version in `artbench/__init__.py` (`__version__`).
2. Push a tag with that version: `git tag v0.1.0 && git push origin v0.1.0`. A 0.x
   version is published as a pre-release.
3. The `release` workflow builds the Windows download on Windows, starts it with its own Python, and only when it
   answers creates the GitHub Release with `Artbench-<version>-windows-x64.zip` and the Blender add-on attached.
4. The `pages` workflow then rebuilds the download page (`site/`) so its button fetches the new zip.

To build by hand: double-click `Build.bat` (Windows), or `python tools/build_portable.py`; the zip lands in `dist/`.
