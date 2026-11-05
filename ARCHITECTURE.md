# Artbench — architecture

A local art bridge between a game project (a git clone the artist does not manage) and a separate art workspace:

```
Game Project (git clone)  <->  Artbench  <->  Art Workspace (FBX / Blend / Textures)
```

Artbench reads both sides, shows what each model is, where the engine uses it and how the two copies compare, and
moves files between them under one rule: **no file is silently overwritten on either side.** Each model keeps the
last content both sides agreed on; a side that differs has new work, both differing is a `conflict`, and a transfer
that would overwrite new work needs an explicit force and archives the old copy. Git stays the project's tool:
Artbench never touches `.git`, never imitates version control (no diff, branch or merge on binaries), and tracks
hashes and metadata instead of file history. Every move and note is logged, old files go to the archive, nothing is
ever deleted by the tool.

Runs from the desktop (`Artbench/`), never inside a game repository. Python 3 standard library only; the engine
side is read from the project's text-serialized files, so no engine, no plug-in and no third-party tool is needed.

## Layers

```
web/index.html      page (vanilla JS), talks only to the HTTP API
server.py           HTTP: the page's /api/* routes (-> ops.page) and the versioned /api/v1 contract (-> ops); no logic;
                    --app opens the page in its own window and stops with it (-> app_window), --port N
mcp_server.py       MCP for AI CLIs (stdio JSON-RPC): tools generated from the ops registry
cli.py              command line: python -m artbench call <operation> / ops / addon (-> ops); setup (-> workspace, ops);
                    shortcut (-> app_window)
--------------------------------------------------------------------------------------------
ops/                operations layer, a package by subject: common (OpError, Op, schemas, lookups), assets, work,
                    transfer, machine (the operations), registry (definitions in contract order, call, coerce,
                    errors), page (what the page's own /api/* routes need; not operations, no MCP tool)
errors.py           typed errors the modules raise (NotFound, NeedsForce, WarningsNotAccepted, OutsideRoot, ...)
--------------------------------------------------------------------------------------------
actions.py          mutations on files (move between state folders, archive and restore, reveal, open) writes history
deploy.py           send entry point: art -> engine (fingerprint warnings, .meta kept); delegates the transfer to package.py
package.py          asset package transfers: per-file send/pull plan (model + engine-ready textures), engine layout
                    targets, team-safe default selection, textures first / model last, per-file outcome      writes history
sync.py             two-way sync: status from the recorded base, pull (engine -> art), force rule, archive paths  writes history
changes.py          change feed: snapshot diff of tracked files on both sides -> changes.log; one asset's timeline
tasks.py            task list CRUD                                                   writes history
marks.py            favourite stars, "revision coming" flags with a note and tags, per asset id (marks.json)  writes history
export.py           game-project models with their textures into a folder of one's own, one folder per model,
                    plan then copy, nothing overwritten                                                writes history
checks.py           advisory checks over the catalog: duplicates (same content in several places, by size then hash)
                    and the project's standards (texture size, power of two, Read/Write, compression, naming,
                    triangle budget); the rules live in the project config's `standards`              writes history
asset_meta.py       metadata snapshots (via blender_jobs) and the structural diff, summary lines, Unity warnings, card payload
thumbs.py           preview renders (via blender_jobs)
graph.py            analysis: reference graph over the engine dump
scenes.py           analysis: scene inventory (what each scene uses), from the dump or a fresh live report
live.py             engine bridge reports (scene contents, asset events): validated against the report contract v1,
                    kept in the tool cache under an OS lock
image_info.py       texture width, height and format from the file header (infrastructure)
blender_link.py     the Blender add-on's presence: its last report (file, version, pid, time) in
                    projects/blender_session.json; open = a report in the last 15 s that is not a close; and the
                    notes the add-on sent, per .blend, in the project's blender_notes.json
doctor.py           machine checks (engine folder, dump, art folder writable, lock across processes, hashing, long
                    paths, OneDrive, Blender, page server): ok / warn / fail / skip, writes nothing into the engine
layout.py           analysis: engine-side layout rules -> issues
scan.py             analysis: desktop art folder + engine dump -> inventory state (project mode: the catalog instead)
catalog.py          analysis (project mode): every engine asset of the catalog kinds with usage (the adapter decides
                    used / unreferenced / by_name / unknown), used_by, uses, size; query filters and pages
--------------------------------------------------------------------------------------------
engines/            engine adapters: base.py (the interface), unity.py (Unity; wraps unity_dump.py), chosen by
                    config `engine` through engines.of(cfg); every caller uses engines.dump / unreachable
unity_dump.py       Unity Assets folder -> asset dump (guid, path, kind, referrers); used only by engines/unity.py
blender_jobs.py     one background Blender worker: priority queue (snapshots before thumbnails, newest request first
                    within a priority), content-hash cache under Artbench/.cache/<kind>/, atomic outputs; Blender is
                    kept open between jobs (RUNNER_EXPR: one JSON job per stdin line; restarted after 200 jobs, a crash
                    or a timeout) and started with --factory-startup (none of the person's add-ons); a Blender that
                    cannot be kept open runs once per job; model_meta.py / thumb_render.py run inside Blender
store.py            per-project persisted files: notes (inventory.json), tasks.json, sync_base.json, history log;
                    atomic JSON writes, the project lock (.artbench.lock) every writer holds, locked_path for any lock file
workspace.py        connecting projects: engine check, art folder link/create from template, registry, hiding a folder
github_link.py      the GitHub account a project pushes as, compared with the account gh is set to (read-only)
mcp_link.py         the AI connection: which AI tools start Artbench's MCP server (read-only), adding it to Claude Code
app_window.py       the page as a desktop app: a Chromium browser's app mode with its own profile, the server's stop
                    when the window closes (or after a quiet spell), the log without a console, the desktop launcher
                    (Windows .lnk, macOS .command), the native folder picker (Finder's on a Mac, tkinter, else
                    PowerShell on Windows)
files.py            files on disk for both sides: content hash (SHA-256) and its cache, the folder walk, the files a
                    .gltf names (gltf_references)
config.py           project configuration: art_inventory.json + DEFAULTS -> resolved paths; the page server's PORT
```

## Layer rules

These hold on the real import graph: an import inside a function counts like one at the top. Importing `engines.base` from outside also counts as importing
`engines`, whose `__init__.py` runs first.

1. **Every module has a layer.** The layers, from the bottom up:
   - leaf: `errors`
   - infrastructure: `engines/`, `unity_dump`, `blender_jobs`, `store`, `workspace`, `config`, `files`, `image_info`,
     `app_window`, `github_link`, `mcp_link`
   - domain: the mutation and analysis modules
   - operations: `ops`
   - transports: `server`, `mcp_server`, `cli`, `__main__`

   `model_meta` and `thumb_render` run inside Blender and import nothing from the package. A new module gets a layer and
   a line in the Layers list above.
2. **Imports go only to the same layer or a lower one.**
3. **Transports import only `ops`, `config`, `errors`, the setup modules (`workspace`, `github_link`, `mcp_link`)
   and `app_window`, and each other** (`__main__` starts `cli` or `server`). Connecting a project, the GitHub
   account and the AI connection are setup, not program operations; `app_window` is the server's own start (its
   window and when it stops) and the native folder dialog, not domain logic.
4. **Only `engines/unity.py` imports `unity_dump`.**
5. **No import cycles.**
6. **No local hides an imported module.** A function that binds a name the module imports as a module
   (`files = [...]` in a module that calls `files.sha`) fails the test. Inside that function the local would win.

7. **No module outgrows one subject:** at most 450 lines. One that grows past it is split by
   subject, the way `workspace` was (the GitHub account and the AI connection into their own modules, the folder
   picker into `app_window`).

Today there is no breach: the transports reach everything through `ops`, the transfer cluster has no cycle
(sync <- actions <- package <- deploy), and `ops` is a package by subject.

## Connecting a game project on its own (project mode)

`python -m artbench setup <folder inside the Unity project> [--name N] [--mcp claude]` (or `ArtbenchSetup.bat`,
or the page's Connect dialog, **Game project only**, `POST /api/projects/connect_project {engine_path, name?}`) runs
`workspace.connect_project`: it finds the project root, inventories its whole `Assets/`, and writes
`projects/<id>/art_inventory.json` under the Artbench install (`config.DATA_ROOT`, ignored by git) with `mode:
"project"`, `engine_root` = the Assets folder, and `engine_ignore_dump` = the default ignore list without
`StreamingAssets`. Every file Artbench keeps for the project (dump, change log, seen mark, tasks, lock, history) lives
in that folder; nothing is written into the engine project. The id is the project folder's name, `<name>-project`
when an art-mode project (or a registry entry that cannot be read) holds that id, then `-2`, `-3` for further clones
of the same mode; an art-mode connect beside a project-mode id takes `<name>-art` the same way. Connecting the same
project root again keeps the existing config (edited keys such as `layout_rules` or `engine_ignore_dump` stay) and
refreshes its paths. The command prints the MCP registration lines for Claude Code, Gemini CLI and Codex with this
install's paths; `--mcp claude` runs `claude mcp add` unless an `artbench` server is already listed (each `claude` call
gives up after `cli.CLAUDE_TIMEOUT`, 60 s, with a message: a first run can stop at a login prompt).
`ArtbenchSetup.bat <folder> [args...]` forwards every argument after the folder to `setup`.

## Connecting a project (GitHub-style, two-way bridge)

1. **Game project first.** The user picks a folder inside the engine project (`/api/pick_folder` opens a native
   dialog on the local machine). `workspace.check_engine` finds the engine project root (Unity: the ancestor with
   `Assets` + `ProjectSettings`) and proposes the engine art root (the picked folder when it is under Assets).
2. **Art folder second.** The user names it and picks a parent folder. `workspace.connect` links the folder when it
   exists or creates it from the template, writes `art_inventory.json` and a README inside it, and registers the
   config in `projects.json`. An existing art folder with a config is added with `workspace.link`.
3. From then on the page shows that project; the engine dump and all tracking files live in the art folder, so the
   folder can be moved or shared as a whole. `workspace.detach` only removes the registry entry.

Nothing about a machine is hard-coded: the registry is the only machine-local file, and a project config may use
relative paths for the art folder and absolute ones for the engine root.

Template of a new art folder: `FBX/<Category>/`, `Outbox/`, `Stock/`, `_Archive/`, `Blend/<Category>/`,
`Textures/`, `README.md`, `art_inventory.json`. An art folder made before the template may keep its config beside
the `INGAME/` art root, with the archive one level up; the config format covers both.

Rules between layers:
- `server.py` never touches files or decides anything; it maps a route to a function and serialises the result.
- Analyses (`scan`, `graph`, `layout`) are pure functions of (config, disk, dump) and never write project files
  (`files.save_cache` may update the tool's own hash cache under `Artbench/`).
- Only `actions.py` and `tasks.py` change project files, and both go through `store.log`. `marks.py` keeps the
  person's own records in the data folder and `export.py` writes only into the folder the person chose (never the
  game project or the art folder); both log too.
- Engine knowledge lives in the engine adapter (see below). Another engine means another adapter with the same dump
  shape; no other module hard-codes `Assets/` or `.meta`.
- The page depends on the API schemas below, not on module internals.

## Engine adapter (`artbench/engines/`)

`engines.of(cfg)` returns the adapter named by config `engine` (default `"unity"`); a name Artbench does not support
raises `errors.Unavailable` ("engine not supported: <name>", HTTP 503 / `unavailable`). `workspace.check_engine` asks
every adapter's `detect` when a project is connected. The interface (`engines/base.py`) carries only what the code
uses, shaped so Godot fits without breaking it:

| Method / attribute | Unity (`engines/unity.py`) | Godot (planned, shape check) |
|---|---|---|
| `name` | `"unity"` | `"godot"` |
| `prefix` | `"Assets/"` | `"res://"` |
| `id_kind` | `"guid"` | `"uid"` |
| `detect(path)` -> {`project_root`, `content_root`} or None | ancestor with `Assets/` + `ProjectSettings/` | folder with `project.godot` |
| `content_root(cfg)` | the `Assets` folder (`engine_assets_root` or found above `engine_root`) | the project root |
| `project_root(cfg)` | the parent of `Assets` (what a bridge reports as `project_path`) | the project root |
| `normalize_engine_path(value)` | strict, for bridge reports: `Assets/...`, either slash, ValueError on `..`, `//` or another root | `res://...` |
| `is_engine_path(value)` | starts with the prefix | |
| `to_engine_path(cfg, abs)` / `from_engine_path(cfg, value)` | absolute path <-> `Assets/...`; `from` resolves what a caller joined (`//`, `.`, `..`) and refuses a path leaving `Assets/` | absolute path <-> `res://...` |
| `sidecars(path)` | `[path + ".meta"]` (kept on send) | `[path + ".import"]` |
| `import_settings(path)` | read only, from the asset's `.meta` (first value of each key, the default platform): texture `{importer, max_size, compressed, mipmaps, readable}`, model `{importer, readable}`; `{}` when unknown | the `.import` file |
| `build_dump(cfg, force)` | `unity_dump` + the dump cache, rebuilt when older than `engines.base.DUMP_MAX_AGE` (60 s), forced, or older than the stale stamp (`dump_stale_since`) | planned |
| `lookup(dump)` | helpers: path -> guid, path -> referrers | planned |
| `layout_defaults` | Unity's folder rules (`engines/unity.py`), used when a project has no `layout_rules` | planned |
| `kind_of(path)` | asset kind by extension (`unity_dump.KIND_BY_EXT`), else `"other"` | planned |
| `dump_ignore(project_mode=False)` | `unity_dump.DEFAULT_IGNORE`; project mode keeps `StreamingAssets` (loaded by name, listed) | planned |
| `mark_dump_stale(cfg, when)` / `dump_stale_since(cfg)` | base class: `engine_index_stale.json` `{since}` beside the dump in the data folder, so every process sees it | (base) |

`engines.dump` and `engines.unreachable` are the calls every module uses for the engine side.
`engines.content_root` names the content root for a caller that needs only that. `layout.check` takes the adapter's
`layout_defaults` when a project has no `layout_rules`. `ops` (asset ids), `actions` (engine paths), `live` (report
paths) and `scenes` (the prefix) ask the adapter instead of assuming Unity.

## Data flow

```
art_inventory.json  -> config.load      -> cfg
cfg.engine_root     -> engines.of(cfg).build_dump -> dump {assets{guid:{path,kind}}, refs{guid:[referrer paths]}}
cfg.art_root + dump -> scan.scan        -> state {items, engine_only, placeholders, blends, unsorted, layout_issues}
dump                -> graph.build      -> {nodes, edges}
```

`engine_index.json` (the dump) is written next to the art root so the artist can inspect it; it is rebuilt when
older than `engines.base.DUMP_MAX_AGE` or when the page asks (`/api/refresh`).

## Folder contract (art root, e.g. `INGAME/`)

| Folder | Meaning | Config key |
|---|---|---|
| `FBX/<Category>/<Set>/` | in the game (state `ingame`) | `states.ingame` |
| `Outbox/<Category>/` | finished, waiting to be sent to the engine (`outbox`) | `states.outbox` |
| `Stock/<Category>/` | ready models not in the game (`stock`) | `states.stock` |
| `../_Archive/<date>/` | replaced files (`archive`) | `states.archive` |
| `Blend/<Category>/` | Blender sources | `blend_root` |
| `Textures/<Set>/` | shared texture sets (not models; skipped by the model scan) | `textures_root` |

A model's own textures sit beside it and travel with it when it is the last model in its folder.

## Schemas

**Config** (`art_inventory.json`, merged over `config.DEFAULTS`): `id`, `name`, `engine` (the adapter, default
`unity`, case and surrounding spaces ignored; an unsupported name makes every engine operation answer `unavailable`
naming the supported ones), `engine_root`,
`art_root`, `states`, `blend_root`, `textures_root`, `categories`, `model_extensions`, `texture_extensions`,
`blend_extensions`, `ignore`, `engine_ignore`, optional `engine_assets_root`, `engine_ignore_dump`,
`layout_rules`, `layout_enabled`, `layout_ignore`, `blender`, `github_account` (optional: the GitHub account this project pushes as; set from the Projects screen or `setup --github`, each change a `GITHUB` history line), `engine_targets` (category -> engine folder for first sends), `previews` (visible | off: model previews by background Blender; images always show) and `model_stats` (background: every unmeasured model is queued at each scan | on_open, the default: only the model whose card opens, ahead of previews | off: none; a cached measurement always shows), both set from the project card on the Projects screen through `performance_settings` (PAGE_ONLY, a PERFORMANCE history line), `standards` (the checks' rules over `checks.DEFAULTS`; each change a `STANDARDS` history line), `export_presets`, `character`,
`bridge_fresh_seconds` (how long a live scene report counts, default 600), `report_limits` (over
`live.DEFAULT_LIMITS` {`scenes`: 200, `nodes`: 200000, `uses`: 1000000} per engine report; any other key or a
value that is not a whole number of 0 or more is a config error, `unavailable`),
`package_extensions` (texture formats that travel with a model to the engine; default `.png .tga .jpg .jpeg`; other
`texture_extensions` such as `.psd .exr` stay on the art side as sources), `engine_layout` (`per_model`: a new model
goes to `<engine_targets[category]>/<ModelName>/` with its textures beside it, written by Connect for new projects;
`follow` (default, for projects whose team moves files): new textures go where this model's textures already are,
the folder holding most of them), `engine_texture_targets` (category -> engine folder, used by `follow` only when the
model has no texture in the engine yet; without it such a texture is reported `no_target` and not sent).
`config.load` adds resolved absolute paths: `art_root`, `engine_root`, `state_dirs`, `blend_dir`, `config_path`,
`inventory_path`, `history_path`.

**Scan state** (`scan.scan()`, `/api/state`): `project`, `name`, `art_root`, `engine_root`, `scanned`, `engine_scanned`,
`engine_unreachable` (the configured engine folder cannot be read: every sync is null, not `missing_in_engine`, and
send/pull refuse with `unavailable` so nothing is created at a stale path), `items`, `engine_only`, `placeholders`,
`blends`, `unsorted`, `layout_issues`, `states`, `categories`, `mode` (`art`). A project-mode project (config `mode:
"project"`, no art folder; config and files in `projects/<id>/`, see "Connecting a game project on its own") gives
`mode: "project"`, `art_root: null`, `catalog`, `placeholders`, `layout_issues`, `engine_unreachable` and the
art-folder keys empty.

**Catalog** (`catalog.build`, project mode `scan.scan()["catalog"]`): `{assets: [{id ("engine:<path under Assets>"),
name, kind, path ("Assets/..."), folder, size, usage (used | unreferenced | by_name | unknown), used_by: [{path,
kind, name}], uses: [...], in_build (scenes: true / false; else null)}], counts: {kinds: {kind: n}, usage: {usage:
n}, hidden}, force_text}`, sorted by kind then path. Kinds come from config `catalog_kinds` (default: model, texture,
material, prefab, scene, animator, clip, shader, audio, font, atlas, mesh); the rest only count in `hidden`. The dump
behind it also carries `uses` (what each file references, model import remaps included), `build_scenes`,
`force_text`, `settings_refs` ({guid: [ProjectSettings files naming it]}, e.g. player icons, always-included shaders:
those assets are `used`, and `used_by` lists the file with kind `settings`) and `outside` ({guid: path} of assets in
folders of `engine_ignore_dump`: those folders add their references without their assets, and a catalog asset's
`uses` lists them with `ignored: true`; an entry without a slash is a folder name matched anywhere, one with a slash is a path from the Assets folder, `Assets/Art/Old`, that folder only). Catalog entries carry, for models, `stats` ({tris, verts, objects, materials, textures, bones, animations} from the cached model snapshot, None while background Blender measures it at `PRIORITY_STATS`, after the previews) and, for textures, `image` ({width, height, format} read by `image_info.py` from the file's header: PNG, JPEG, TGA, PSD, BMP; else None). The project-mode state carries `hidden_folders` (the `engine_ignore_dump` list). Previews (`/api/thumb`): a PNG or JPEG up to 2 MB is its own preview; other image formats and larger images are scaled by background Blender; only files inside the project's art folder or engine project get one. The dump's file cache (`.unity_dump_cache.json`) is written only when a file
was read. **The page's poll** (`/api/state`, `/api/refresh`) gets light catalog rows: `used_by_count` and
`uses_count` instead of the two lists (`catalog.light`); the asset card asks `/api/v1/asset` for them. In project mode
the poll's answer also carries `since_seen` (the change entries after the last Mark as seen).

**Item** (a desktop model, `scan.scan()["items"][i]`):
`id` (path relative to art root, `/`-separated; the key for notes and tasks), `name`, `state`, `category`,
`folder`, `path`, `size`, `mtime`, `textures` (file names beside it), `note`, `source`,
`engine_path` (matching engine file or null), `engine_mtime`, `engine_size` (of that file, or null), `synced_at`
(time of the recorded sync base for this item, or null), `sync` (`same` | `desktop_newer` | `engine_newer` | `conflict` |
`missing_in_engine` | null), `basis` (`base` when the recorded sync base decided `sync`, `mtime` when no base was
known and modification times had to, null without an engine copy), `usage` (`used` | `unused` | null), `used_by` ([{path, kind, name}]),
optional `ambiguous` ([candidate engine paths]), `package`, `blend`.

**Package** (`item.package`): `files` [{`id`, `role` (`model` | `texture` | `buffer`: a `.gltf`'s `.bin`, see below), `name`, `path`, `engine_path`, `sync`,
`basis`, optional `ambiguous`}] (the model first), `state` (the worst file state: `conflict` > `desktop_newer` >
`engine_newer` > `missing_in_engine` > `same`; the page's lists, counters and filters use it), `sources` (texture
files beside the model that are not engine-ready, e.g. `.psd`; never sent). A texture belongs to a model when it sits
in the model's folder and its stem starts with the model stem followed by `_ - .` or a space (case-insensitive); with
several models in one folder the longest matching stem wins; models sharing a stem (`Crate.fbx`, `Crate.glb`)
leave the files to the first in `model_extensions` order. A file that two models claim (two `.gltf`s naming it, or
a `.gltf` naming another model's texture) is listed in both packages with `shared` (the other models' ids), and a
state move of either model is refused (`conflict`) until each has its own copy. Its engine copy is found by file name (the team may move
it anywhere), or by its own note `engine_path`; a copy beside the model's engine copy wins, and a name that does not
carry the model's stem (`Albedo.png`) is matched only there. Several candidates set `ambiguous`. Textures are compared only for `ingame` and `outbox` models.
A `.gltf` also carries the files it names beside itself (`files.gltf_references`, read once per change of the file):
every `buffers[].uri` as a `buffer` file and every `images[].uri` as a `texture` (whatever its extension: the model
needs it), URI-decoded and normalised (`./Hull.bin` is `Hull.bin`), by the name on disk (the exact name first, else
the same name in another case). These files carry `beside`: their engine copy is the same-name file beside the
model's engine copy and a new one goes there, whatever the layout, because the `.gltf`'s relative URIs look there.
Embedded `data:` URIs need nothing. A URI that names a file in another folder, a missing file or a model file is
listed in `package.unresolved`; the send plan turns each into a warning that must be accepted (`accept_warnings`),
and the card shows them. Pull of a `.gltf` also brings the files the engine copy names that the desktop does not have
yet (`sync: not_on_desktop`). The change feed tracks `.bin` files, and Blender snapshots and previews of a `.gltf`
are cached by the `.gltf` and its buffers together, so a change to the geometry alone is seen.

**Blend binding** (`item.blend`): `{id, path, bound}` or null. `bound: true` when the model's note has `blend` (an id
under the art root, set from the card); otherwise the `.blend` under `blend_root` with the same stem (`bound: false`).
`.blend` files are never sent to the engine.

**Engine-only entry** (`engine_only[i]`): `id` (`engine:<path relative to engine root>`), `name`, `engine_path`,
`category`, `state: "engine_only"`, `sync: "not_on_desktop"`, `usage`, `used_by`, `note`.

**Placeholder** (`placeholders[i]`): code-made mesh `.asset` under the engine root: `id`, `name`, `engine_path`,
`category`, `usage`, `used_by`, `note`.

**Layout issue** (`layout_issues[i]`): `path` (relative to engine root), `kind`, `folder`, `hint`, `engine_path`.

**Task** (`tasks.json`): `id`, `title`, `status` (`todo` | `doing` | `done`), `priority` (`high` | `normal` | `low`;
a task saved before priorities reads as `normal`; lists come in board order: status, then priority, then oldest),
`asset` (an item id, a project-mode catalog id `engine:<path>`, or null),
`note`, `created`, `updated`, `done` (timestamps or null).

**Notes from Blender** (`blender_notes.json` in the project's data folder, `{asset: entry}`): the copy of a .blend's
notes the add-on last sent. Entry: `asset` (the file's id), `name`, `file` (absolute path), `sent` (timestamp),
`notes` [{`text` (at most 4000 characters), `kind` (`todo` | `note`), `done`, `priority` (`high` | `normal` | `low`),
`object` (an object name or null)}], at most 500 notes. A send replaces the file's entry; an empty list removes it.
The notes themselves live in the .blend (`scene.artbench_notes`); Artbench never opens a .blend to read them.

**Snapshot** (`.cache/meta/<sha16>.v1.json`, written by `model_meta.py`, `version: 1` = `asset_meta.SNAPSHOT_VERSION`;
bump both when the shape changes, old cache files then simply go unused): `objects` [{`name`, `type`, `verts`, `polys`,
`tris`}], `object_names`, `materials`, `textures` (image names in material node trees), `bones` (count), `bone_names`,
`actions` [{`name`, `start`, `end`}], `action_names`, `bbox` {`min`, `max`} or null, `totals` {`verts`, `polys`, `tris`}.
`asset_meta.names(snap, key)` also reads the earliest fingerprint shape (`objects`/`actions` as name lists).

**Diff** (`asset_meta.diff(before, after)`): `geometry` {`verts`, `polys`, `tris` ([before, after]), `objects_added`,
`objects_removed`, `objects_changed` [{`name`, `verts`}]}, `materials` {`added`, `removed`}, `textures` {`added`,
`removed`}, `skeleton` {`bones` [a, b], `added`, `removed`}, `animations` {`added`, `removed`, `range_changed`
[{`name`, `before`, `after`}]}, `bbox` {`before`, `after`, `changed`}, `empty`. `summary(diff)` renders it as lines
("Vertices: 12,430 → 14,882", "Added material: Metal_Dark", ...); `warnings(before, after)` renders the send-plan
warnings (missing/new objects, material slots, animation takes; bone count).

**Compare** (`/api/meta/diff`, `artbench_metadata_diff`): `state` (`ready` | `pending` | `failed` | `none` = no Blender),
`sync`, `basis`, `send` {`before` (engine snapshot), `after` (art snapshot), `diff`, `summary`, `warnings`} or null,
`after` (art snapshot, only when there is no engine copy), `conflict` {`art` {`diff`, `summary`}, `engine` {...}} or
null (only in `conflict` and only when the last agreed content's snapshot is cached), `affected` (= item `used_by`),
`size` {`art`, `engine`}. `none` means no Blender or no such file. Snapshots are requested only by the card/compare
calls, `/api/meta/snapshot` and its MCP twin, the send plan (synchronously) and after a send/pull for the agreed
content; never by a scan.

**Graph** (`/api/graph`, `.asset` kinds `data` and `mesh` excluded): `nodes` [{`id` (path relative to Assets), `name`, `kind`, `inside` (under engine root),
`category`, `in`, `out`, optional `desktop_id` (matching desktop item), optional `engine_id` (the `engine:<path>` id used by engine-only and placeholder entries)}], `edges` [{`from`, `to`}] (referrer -> referenced), `root`.

**Sync base** (`sync_base.json`): `{item id: {art: sha256, engine: sha256, time}}`, the last content both sides
agreed on. Written after every send and pull, when a scan sees both copies identical (opportunistically, skipped if
another process holds the lock), and carried along when a model moves between state folders. Status rule
(`sync.status`): equal hashes -> `same`; with a base, only art differs -> `desktop_newer`, only engine differs ->
`engine_newer`, both -> `conflict`; without a base the newer mtime decides and `basis` is `mtime`.

**Force rule** (send and pull): the transfer needs `force` whenever the side it overwrites differs from its base hash
(`force_reason: "changed"`) or no base is known (`force_reason: "no_base"`); identical copies never need it. Without
force it raises; with force the old copy is archived (`_Archive/<date>/engine/<rel>` for send, `_Archive/<date>/art/<rel>`
for pull; a second archive of the same file on the same day gets a `.HHMMSS` suffix, nothing in the archive is ever
overwritten) and the history line ends with `FORCED`. A send that creates a new engine file needs no force. Send and
pull refuse a source or target outside the art root / engine root, and write the target through a temp file beside it
(`<name>.artbench.tmp` + rename), so a failed write never leaves a half-written model.

**Project lock** (`.artbench.lock` in the art root): every writer of project data (move, meta, tasks, send, pull, base
record) holds it. It is an operating-system lock on that file (`fcntl.flock`, `msvcrt.locking` on Windows), so the
OS frees it the moment a holder dies and no staleness guess is needed; the file itself stays in place. Re-entrant in
the holding thread; other threads of the same process and other processes wait up to 10 s (default), then get
`TimeoutError` ("project is busy"). `store.locked(cfg)` is `store.locked_path(<art root>/.artbench.lock)`;
`locked_path(path, timeout)` locks any file the same way (the live report cache uses it). The change feed snapshot and the tool's own caches
are written without it (atomic replace only; a quiet look rewrites nothing). JSON files are written to a temp file and
replaced atomically, with a short retry when another process holds the file open.

**Package plan** (`plan_send` / `plan_pull` in `package.py`, reached through `deploy.plan` and `sync.plan_pull`): the
top-level fields describe the model as before; `files` [{`id`, `role`, `source`, `target`, `action` (send: `send` |
`skip` | `no_target`; pull: `pull` | `skip`), `sync`, `basis`, `force_reason`, `overwrites`, `backup`, `team_changed`
(send: the engine copy is newer: changed since the last sync, or by date when there is no sync record),
`art_changed` (pull: the same for the art copy), `ambiguous`, `default` (ticked in the confirmation)}]. Files the
other side changed and ambiguous textures are never in the default selection; pull never picks a file whose art copy
is newer. Send/pull take an optional `files` (ids; an empty list is refused as `bad_request`): without it the default selection goes, plus the model when
`force` is set (the single-model force of the bridge core); a protected texture moves only when named in `files`.
A selected file that needs force still needs `force`. `requires_force` is true when a default file or the model would
need it. Each file also carries `target_sha` (the hash of the file it would overwrite, null when absent) and
`source_sha`: the transfer re-checks `target_sha` under the project lock and does not write a file whose target
changed or appeared after the plan (`conflict`, outcome `failed`, nothing after it runs). Send/pull also take
`expect` ({file id: target_sha} or {file id: {target, source}} from the plan the caller confirmed): when a selected
file differs from it the call is refused before anything is written, so a `force` given for one state never applies
to a newer one (the page sends it from its confirmation). Ids in `files` that are not in the package are refused. A send from Outbox is refused in the plan, before anything is written, when a destination of the package
move is taken. Transfer order: textures first, the model last; the first failure stops the run, files already written
stay written (each with its history line and sync base), the rest are `not_run`. The result adds `results` [{`id`,
`role`, `outcome` (`sent` | `skipped` | `failed` | `not_run`), `target`, `backup`, `error`}] and `refresh_error`
(null, or why rebuilding the dump / change feed after the written files failed; the transfer itself stands). A send
from the Outbox reports a failed package move as `move_error` (the engine files stand); sending again, with the
engine copy identical and no file of the package still to send, retries the move (the page's Send does it without a
confirmation and shows a failed move as a message). When nothing needs moving the
call succeeds with nothing written. A send from Outbox moves the whole package (model, textures, notes, sync bases)
to `<in game>/<category>/<ModelName>/`.

**History log** (`inventory_history.log`): one line per event, `YYYY-MM-DD HH:MM:SS<TAB>VERB<TAB>fields...`.
Verbs: `MOVE`, `META`, `TASK ADD|TODO|DOING|DONE|DELETE`, `CONNECT`, `SEND` (id, target, backup, warnings, FORCED|""),
`PULL` (id, source, backup, FORCED|""). A package transfer writes one `SEND`/`PULL` line per file (id = that file's
art id; warnings only on the model line); a package move writes one `MOVE` line per file (textures first, the model
last), each right after that file moved, and carries its note and sync base.

**Change feed** (`changes.log`, snapshot in `snapshot.json`): `time<TAB>ADDED|CHANGED|REMOVED|BASELINE<TAB>art|engine<TAB>path`.
Project mode: the snapshot is `{asset id (guid): {path, hash, size}}` over the catalog's kinds (`hash` covers the file
and its `.meta`, so a changed import setting is CHANGED), lines carry `Assets/` paths, and a moved asset is `time<TAB>MOVED<TAB>engine<TAB>new path<TAB>old path`; nothing is logged while the engine
project cannot be read. `seen.json` `{seen, lines}` marks how many log lines the person has seen (Mark as seen);
`since_seen` is every later line except the baseline.
While the engine folder is unreachable the engine side keeps its last snapshot (no mass REMOVED / ADDED).
`/api/state` runs `changes.update` before scanning, so the feed grows while the page is open. A look runs under the
project lock (the page server and an agent's MCP process may look at once); a look that cannot get the lock within
`changes.LOOK_LOCK_TIMEOUT` (2 s) is skipped, and the next one catches up.

## HTTP API (127.0.0.1:8765)

| Method, path | Query / body | Returns |
|---|---|---|
| GET `/` | | the page |
| GET `/api/projects` | | [{id, name, error, config_path, mode, github_account}] |
| GET `/api/projects/github` | `project` | {account, active, matches, switch, git_user} (see GitHub account below) |
| POST `/api/projects/hide_folder` | {project, folder ("Assets/..."), hidden (default true)} | {ok, hidden: the project's `engine_ignore_dump`}; adds or removes the entry, rebuilds the dump, a HIDE or SHOW history line |
| POST `/api/projects/github` | {project, account ("" clears)} | {ok, account, active, matches, switch, git_user}; 400 for a name GitHub would not accept |
| GET `/api/projects/check` | `engine_root` | {ok, engine, project_root, assets_root, engine_root, message} |
| GET `/api/projects/progress` | | the running (or last) connect's record, `workspace.connect_progress()`: {state: idle / running / done / error, stage, stages: [{id, done, total}], current (the file being read), name, project, message, started, elapsed}; stages `check`, then the engine's `files`, `meta`, `refs`, `settings` (`unity_dump.build(progress=)` through `build_dump(cfg, force, progress)`); read without the server's lock, so the page polls it while the connect holds it |
| POST `/api/projects/connect` | {name, engine_root, art_parent, art_name?, categories?, create?} | {ok, id, config_path, art_root}; reads the engine project once (its progress in `/api/projects/progress`, like `connect_project` and `link`) so the first open is quick |
| POST `/api/projects/link` | {path (art folder or its config)} | {ok, id, config_path, art_root} |
| POST `/api/projects/detach` | {id} | {ok} |
| POST `/api/pick_folder` | {title?, initial?} | {path or null} |
| GET `/api/alive` | | {ok: true, app: "artbench", version, author} (`config.VERSION`, `config.AUTHOR`, from the package's `__version__`, `__author__`; the page signs its sidebar and the Projects screen's About card with them); the page asks once a minute, even hidden, so an app window's server knows it is open; `--app` uses it to find an Artbench already serving |
| GET `/api/mcp` | | {tools: [{tool: claude\|gemini\|codex, name, installed, state: here\|elsewhere\|missing\|unknown, config}], lines: {claude, gemini, codex}} |
| POST `/api/mcp/register` | {tool: "claude"} | {result: registered\|updated\|already\|no_claude\|timeout\|failed, message}; 400 for another tool |
| GET `/api/state` | `project` | scan state (schemas above); project mode: light catalog rows and `since_seen` |
| GET `/api/refresh` | `project` | same, after forcing a dump rebuild |
| GET `/api/history` | `project` | last 200 log lines, newest first |
| GET `/api/graph` | `project` | graph |
| GET `/api/tasks` | `project` | [task] |
| GET `/api/thumb` | `project`, `path` | PNG; 202 `{state:"pending"}`; 404 `{state:"failed"|"none"}` |
| GET `/api/meta/snapshot` | `project`, `path` | `{state, snapshot}`; 202 while pending; 404 failed/none |
| GET `/api/meta/diff` | `project`, `id` | Compare (schema above); HTTP 202 while `state` is pending |
| GET `/api/changes` | `project`, `limit` | change feed entries [{time, change, side, path, from?}], newest first |
| POST `/api/changes/seen` | `project` | Mark as seen → `{seen, lines}` |
| GET `/api/send/plan` | `project`, `id` | {source, target, overwrites, backup, warnings, sync, basis, requires_force, force_reason, files} |
| POST `/api/send` | {project, id, accept_warnings?, force?, files?} | {ok, target, backup, warnings, moved_to, forced, results} |
| GET `/api/pull/plan` | `project`, `id` | {source, target, overwrites, backup, sync, basis, requires_force, force_reason, files} |
| POST `/api/pull` | {project, id, force?, files?} | {ok, target, backup, forced, sync, results} |
| POST `/api/move` | {project, id, state} | {ok, path} |
| POST `/api/meta` | {project, id, note?, source?, engine_path?, blend?} | {ok} |
| POST `/api/reveal` | {project, path} | {ok} |
| POST `/api/open` | {project, path} | {ok} |
| POST `/api/projects/connect_project` | {engine_path, name?} | {ok, id, config_path, mode} |
| POST `/api/tasks` | {project, op: add / update / delete, task fields} | task / {ok} |

Errors are `{error: "<message>"}` with the status of the matching `/api/v1` code (409 for a transfer that needs force
or met a change, 404 for an unknown project or item, 423 busy, ...); the page shows the message.

Every request body is capped at `server.MAX_REQUEST_BYTES` (64 MiB, a constant: the project id is inside the body):
a larger `Content-Length` is refused with 413 before the body is parsed: the answer is sent first, then whatever the
client still sends is read and dropped for up to `server.DRAIN_SECONDS` (2 s) so it reads the 413 instead of a
connection reset, and the connection is closed. A `Content-Length` that is not one plain number (or two that
differ) is 400; a POST without `Content-Length`, or with `Transfer-Encoding` (chunked), is 411. These refusals, the origin guard (403) and the content-type check (415)
answer in the `/api/v1` envelope on `/api/v1` paths (`bad_request`, or `not_found` for 404) and as `{error}` elsewhere.
A page route's body must be a JSON object (400 otherwise) and a missing field answers 400 `missing field: <name>`.

### `/api/v1` — the contract for programs (Unity bridge, scripts)

`GET /api/v1` → `{api: "artbench", version: 1, engine_report_schema: 1, operations: [{name, description, params (JSON
schema), write}]}`.
`POST /api/v1/<operation>` with a JSON object of arguments, or `GET /api/v1/<operation>?arg=value` for operations
with `write: false` → `{ok: true, result}` or `{ok: false, error: {code, message, detail}}`. Codes and HTTP status:
`bad_request` 400, `outside_root` 400, `not_found` 404, `needs_force` 409, `warnings` 409, `conflict` 409,
`wrong_mode` 409, `busy` 423, `unavailable` 503, `internal` 500. The code comes from the exception's type (`errors.py`), never from words in
its message. String arguments are converted by the schema (integer, boolean, comma-separated array) whichever
transport they came through. Every request must carry `Host: 127.0.0.1:<port>` or `localhost:<port>` and, when it
has an `Origin`, the server's own; every POST must be `Content-Type: application/json` (403 / 415 otherwise), so
other web sites open in the user's browser cannot call the API. Adding an operation or an optional argument/field keeps v1; renaming,
removing or changing a meaning goes to `/api/v2` with v1 kept until callers moved. The operations are those of
`ops.OPS`: projects, overview, search, asset (by `id`, or `engine_path` under `Assets/`, or `guid`), unused,
placeholders, layout_issues, layout_settings, graph_neighbors, tasks (assets?: only the tasks tied to these asset ids), task_add, task_update, note, meta (note/source/engine_path/
blend; an engine_path must be an existing file inside the engine root with the item's own file name (case-insensitive,
as same-name copies are found), given as an
absolute path or under `Assets/`; the scan honours a note only when it passes the same rule (a hand-edited one
included), so an item can never be pointed at another file that a send would then overwrite), move, history, changes, refresh, send_plan, send, pull_plan, pull, metadata_snapshot, metadata_diff, preview,
scene_inventory, engine_status, engine_report, doctor, performance_settings (previews?, model_stats?; the page's), asset_history (id, offset, limit 20: `{total, entries: [{time, source: history | change, what, detail}]}`, newest first), checks (what standards | duplicates, rule?, offset, limit), checks_settings (set?), catalog (kind, usage, folder, search, detail, offset, limit 25 ≤
500 → `{total, offset, assets}`: brief rows, `detail: "full"` for the whole entries), tasks (status: todo, doing, done or
open; assets; limit 50 → rows without their empty fields), blender_status (no project: `{open, file, blender, pid, seconds_since_report, project, asset, models}`, project = the registered project whose art folder or engine folder holds the file, asset = the file's id there (its path under the art folder, or `engine:<path>` inside the game project), models = the desktop models made from it (bound to this .blend by name or by binding); `blender_link.file_info`, reused for 20 s), blender_report (the add-on's door, HTTP only like engine_report: {file, blender, pid, closing?}), blender_notes_send (the add-on's door too: {file, notes}; a file in no registered project is `bad_request` "this file is in no Artbench project"; → `{project, asset, count}`), blender_notes (project → the entries above, newest send first; read only, shown in the Tasks view's From Blender section), open_in_blender (project, id: a model opens in Blender's window, detached; a .blend as it is, FBX/OBJ/glTF imported into an empty scene by `blender_link.IMPORT_EXPR`; an art-folder model with a .blend source opens that .blend; `unavailable` without Blender, `bad_request` for a kind that is not a model).

**Blender add-on** (`blender_addon/artbench_bridge/`, Blender 4.2+ extension; `python -m artbench addon [out.zip]` writes the zip to install). Standard library and bpy only, never Artbench's own code. Three files: `notes.py` (notes in the .blend), `link.py` (the link to Artbench), `__init__.py` (connection panel, preferences, registration). **Notes** work with Artbench closed: a collection on the scene (`scene.artbench_notes`: text, kind to-do or note, done, priority, an object pointer, so renaming the object keeps the link; a Blender without the add-on keeps the data), changed only through undo-able operators (`artbench.note_add` with a dialog, `note_remove`, `note_goto` selects and frames the object), so Blender marks the file changed. Sidebar (tab Artbench) panel Notes: the list (checkbox for to-dos, priority colour, object), the selected note's fields, a pins toggle; right-click an object > Add note. In the 3D view a POST_PIXEL draw handler puts a pin and the first line of the most urgent open note beside each object that has one (+n for more), coloured by priority; done to-dos have none; the toggle and the viewport's overlays hide them. While Artbench answers and the file is in a project, **Send to Artbench** posts the notes to `blender_notes_send`. **Link**: a timer posts `/api/v1/blender_report` every 5 s from a background thread (2 s timeout) with the open .blend; quitting or disabling posts `closing`. Requests never go through a proxy (`ProxyHandler({})`): Artbench is on this machine, and a proxy set for the whole system made the add-on report "not connected" while Artbench ran. The address is `ARTBENCH_URL`, else the add-on preference, else `http://127.0.0.1:8765`. After each answer the timer asks the 3D view and the preferences to redraw. Panel Artbench link: the link in plain words (Looking for Artbench, Connected with project and file, or Not connected with the reason and where it looked), Open Artbench, Test connection / Try again, Connection settings. Version 0.3.0 (0.2's board-tasks panel is gone; the tasks it wrote stay on the board). Still to come: the scene, its changes, project export templates.

**Modes.** Every operation serves art mode; all except the art-folder ones also serve project mode. Art-folder
operations (note, meta, move, history, send_plan, send, pull_plan, pull, bring_in_plan, bring_in, metadata_snapshot,
metadata_diff, preview)
called for a project-mode project answer `wrong_mode`. In project mode `overview` → `{project, name, mode,
engine_root, kinds: {kind: n}, usage: {used|unreferenced|by_name|unknown: n}, hidden, placeholders,
placeholders_in_use, layout_issues, force_text, engine_unreachable, engine_scanned, changes_since_seen, folders: {folder:
n} (the 12 fullest), tasks: {todo, doing, done, high_open}}` (art mode's overview carries `tasks` too); `search` →
`[{id, kind, usage, used_by_count}]` (limit 20), the brief row every list answer uses: the id carries the path
(`engine:<path under Assets/>`) and `asset` has the rest; `asset` → the catalog entry with `used_by` / `uses` capped at 50 rows
plus `used_by_count` / `uses_count` and `tasks`; `unused` → `{unreferenced: [...], unreferenced_total, by_name:
[...], by_name_total, unknown: n}`, brief rows, paged by `offset` / `limit` (default 25, at most 500); `layout_issues` →
`{total, offset, issues}`, paged the same way, and empty while Layout is off; `layout_settings` (project, enabled?, allow_kind?, allow_folder?) → `{enabled, rules, proposed}`: Layout is off until turned on (`layout_enabled`; a project that wrote its own `layout_rules` is on). Turning it on writes rules learned from where the assets are now (`layout.learn`: per kind of model, texture, material, prefab, the two-level folders holding at least 15% of that kind and two of its assets; never the root) when the project has none; turning it off keeps them; allow_kind with allow_folder ('' is the root) adds that folder to the kind's rule. Each change is a LAYOUT history line. The state carries `layout` (the same `{enabled, rules, proposed}`) so the page shows the rules before and after; `graph_neighbors` takes the forms other tools return (`engine:Art/X.png`,
`Assets/Art/X.png`, `Art/X.png`, or a bare file name when only one file has it: two answer `bad_request`) and caps
`edges` at 200 with `edges_total` and `truncated`;
`projects` entries carry `mode`. The command line runs the same operations except `engine_report`, `blender_report` and `blender_notes_send`
(the bridges' doors: neither MCP nor the command line offers them)
(`python -m artbench call <operation> --project <id> --arg k=v --json-args '{...}' [--compact]`; exit 0 ok,
1 operation error printed as JSON, 2 usage error; `python -m artbench ops` lists them).

**Engine report v1** (`engine_report`, for bridges; not an MCP tool). One contract for every engine; the published
schema is `docs/contracts/engine_report.v1.schema.json` (JSON Schema 2020-12, informative: Artbench validates in code).
Body: `{project, report: {schema: 1,
bridge, engine, engine_version, project_path, time, scenes: [{path, loaded, dirty, nodes: [{id, parent, name, kind,
uses: [{id, path, kind}]}]}], events: [{type: imported|moved|deleted, path, from (moved only, required there), time}]}}`. A use's `id` is the
engine's own asset id (Unity guid, Godot uid) and every path is in the engine's own form (`Assets/...` for Unity,
`res://...` for Godot; the adapter's `prefix` and `normalize_engine_path` decide, either slash, no `..`).
`project_path` must name the adapter's project root (the folder holding `Assets/`), compared after normalising slashes
(and case on Windows). A use whose path is outside the content root (built-in resources, `Packages/`) is dropped and counted as
`skipped_uses`. A node lists only its own direct references (mesh, materials, sprites, fonts, the source prefab of
an instance); `kind` is an open string so UI nodes fit later. Limits per report (config `report_limits` over
`live.DEFAULT_LIMITS`: 200 scenes, 200 000 nodes, 1 000 000 uses): over one → `bad_request` naming the limit. Nothing
is stored when any part is invalid. Stored in `Artbench/.cache/live/<project id>.json` (atomic, compact, no
project lock, no history line, parsed once per change); every read-modify-write holds the OS lock
`.cache/live/<project id>.lock` (`store.locked_path`, 10 s), so two reports posted together, from any processes, are
both kept. Each named scene replaces its entry `{path, loaded, dirty, node_count, uses: [{id, path, kind, count}],
skipped_uses, time}` (uses merged by `id`, by path when the bridge sent none), stamped with the receive time
(freshness per scene, config `bridge_fresh_seconds`, default 600); events keep the last 200 and mark the engine dump
stale through the adapter (`mark_dump_stale`, written before the report is stored), so the next scan rebuilds it.
Events do not enter the change feed.
`engine_status` → `{bridge, last_report, scenes: [{path, time, fresh, loaded, skipped_uses}], events}`.

**Scene inventory** (`scene_inventory`, optional `scene`): `[{path, source: live|files, time, dirty, uses: [{path,
kind, count, desktop_id, file_id, engine_id, sync, placeholder}]}]`. Files source: the scene's references followed
only through prefabs (nested, variants) and materials until art leaves (model, mesh, texture, sprite), depth cap 8,
cycles end; scripts, data assets, animators, shaders and audio are neither listed nor followed. A live entry replaces it only when fresh, `loaded` and non-empty; its non-leaf uses are expanded through the
dump. `count` is the number of live nodes using the asset (null from files). A model shows its `package.state`, a
texture its own package-file sync with `file_id` and the owning model's `desktop_id`; engine-only and placeholder
entries carry `engine_id`; `placeholder` is true only for the scan's placeholders (code-made meshes under the engine
root). A live use sent by path only is matched to its id through the dump and merged with the same asset sent by
id. Fresh live-only scenes (not yet on disk) are listed too.

**GitHub account** (`github_link.github_status`): Artbench never runs git or gh. A project may name the account it pushes as (`github_account`); the account the GitHub CLI is set to is read from gh's own `hosts.yml` (the `user:` of its `github.com` block; `GH_CONFIG_DIR`, else `%AppData%\GitHub CLI` on Windows, else the XDG config folder), and the commit name from the `[user]` section of the game repository's `.git/config`. → `{account, active, matches (null when either is unknown; names compared without case), switch (`gh auth switch --hostname github.com --user <account>` when they differ, else null), git_user}`. `overview` carries it as `github` so an agent sees it before it pushes; the doctor check `github_account` is skip without an account, warn with the switch command when gh is set to another one (or to none), ok when they match; the page shows it under the project picker with a copy button.

**Doctor** (`doctor`, every door: HTTP, MCP `artbench_doctor`, command line, the page's Projects dialog "Check this
machine", whose results stay with the project they ran for) → `{ok, machine: {os, python, art_root, engine_root,
tool_root}, checks: [{id, status: ok|warn|fail|skip, detail}]}`; `ok` is false only when a check failed. Project mode
runs `engine_root`, `dump`, `force_text` (ok with Force Text, fail without, warn when EditorSettings is missing),
`data_writable` (the atomic-write probe in the data folder), `lock`, `long_paths`, `onedrive`, `addressables` (warn
when `Assets/AddressableAssetsData` or a `.meta` with an `assetBundleName` exists: assets loaded that way may read
unreferenced), `github_account`, `mcp` and `server`; `art_root_writable`, `hash` and `blender` are `skip` with detail "project mode". Checks, each
independent (one that raises is a failed check): `engine_root` (folder, adapter, content root), `dump` (forced
rebuild, counts, time), `art_root_writable` (atomic write of a temp file in the art root, removed), `lock` (a second
Python process, given the tool folder on its path, holds the project lock; this process must be refused; the holder
is killed; the lock must be free at once. The probe must answer within `doctor.PROBE_TIMEOUT` (15 s) and a probe that
dies reports its last error line; `warn` when the project is busy, before or right after the probe), `hash` (one
model: the cached hash must equal a fresh read and two stats must agree), `long_paths` (Windows only: a path over
260 characters under the temp folder, removed), `onedrive` (`warn` when the art, engine or tool path is in
OneDrive), `blender` (`warn` when missing), `server` (the page server on `config.PORT` answers `/api/v1`: `warn`
when it lacks `engine_report_schema`, an older Artbench that needs a restart; `fail` when something else answers;
`skip` when nothing runs). Nothing is written into the engine project. On a project that has none yet, the run
creates the two standard tool files in the art folder, `.artbench.lock` and `engine_index.json`, which every Artbench
run keeps.

## MCP server (for local AI agents)

`mcp_server.py` is a stdio MCP server (newline-delimited JSON-RPC, protocol 2024-11-05) exposing the same state to
Claude Code and other local agents, so an agent can answer "what is unused", "where is this model used", add tasks
and notes, or move a model between states; every write goes through the same modules and the same history log.
Tools are generated from `ops.OPS` (`artbench_<operation>`, every operation except the bridges' doors `engine_report`, `blender_report`, `blender_notes_send`), so the MCP
list and `/api/v1` never differ; `tools/list` is read at every call and holds the tools of the registered projects'
modes (only project-mode projects: no art-folder tools; nothing registered: every tool); errors come back as `isError` with `"<code>: <message>"` (a result JSON cannot
carry is `internal`; the server keeps answering). `artbench_overview` carries `engine_unreachable`. Metadata and preview
tools may answer `state: "pending"` while Blender works; call again. Any MCP-capable CLI registers the same stdio
command (`python -m artbench.mcp_server` with `PYTHONPATH=<Artbench>`): Claude Code
`claude mcp add --scope user artbench -e PYTHONPATH=<Artbench> -- python -m artbench.mcp_server`; Gemini CLI
`mcpServers.artbench` in `~/.gemini/settings.json`; Codex `[mcp_servers.artbench]` in `~/.codex/config.toml`
(README_TR has the exact snippets). Tools that cannot speak MCP use the command line above.

**Answers for an AI are lean**: Artbench stays open in the background for AI tools, so every character an agent
reads counts. The MCP server answers compact JSON; list answers carry brief rows and small pages
(25) with totals; `overview` is the map to start from (kinds, usage, the fullest folders, task counts), and an
agent asks `asset` for one entry in full. Tool texts are short (project mode's tools/list about 7 300 characters,
every tool about 12 000); the long explanations live here. Tests hold both budgets.

**AI connection** (`mcp_link.mcp_status`, `register_claude`; page: Projects screen, card "AI connection"). Reads,
never writes, the three tools' config files: Claude Code `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`)
`mcpServers.artbench`, Gemini CLI `~/.gemini/settings.json`, Codex `~/.codex/config.toml` (or `$CODEX_HOME`). An entry
is `here` when its PYTHONPATH is this Artbench folder or its command is inside it (the portable Python), `elsewhere`
otherwise (a moved folder, an old copy), `unknown` when the file cannot be read. Adding runs Claude Code's own
`claude mcp add --scope user` (60 s timeout); an entry that is `elsewhere` or `unknown` is removed first with
`claude mcp remove --scope user artbench`. Gemini CLI and Codex get the line to paste. `setup --mcp claude` uses the
same function. The doctor check `mcp` is ok when some tool's entry is `here`, warn otherwise.
The HTTP server and the MCP server are separate processes over the same files; every writer holds the project lock
and JSON writes are atomic, so they stay in step; the page re-reads every few seconds.

## Bringing an engine model into the art folder

`bring_in_plan` (project, id `engine:<path>`, category?) → `{source, engine_path ("Assets/..."), name, category (the
given one, else the first folder of the engine path that is a known category, any case, else null), categories,
target, id (null without a category), exists, textures: [{source, target, exists}]}` (the textures the model uses,
`catalog.textures_of`: through its materials and its own prefabs' materials, and the textures beside it named
after it). `bring_in` (project, id, category, textures?) copies the model (temp file + rename) to
`FBX/<category>/<model stem>/<file>`, and with `textures: true` those textures beside it, each recorded as agreed
like the model; without, they stay in the engine. Any target already there refuses the whole call. Under the
project lock it records the sync base (both sides the same), writes the item's notes `engine_path` (the exact
engine file, so a same-name file elsewhere never makes it ambiguous) and `imported: {from: "Assets/...", time}`,
and one history line `BRING IN <engine path> <art path>`; then the dump and change feed refresh. → `{ok, id, path,
source, engine_path, textures (how many came), refresh_error}`. Refused: an id that is not engine-only (not_found), a category that is not one
folder name (bad_request), a target that exists (conflict, nothing overwritten), an unreachable engine folder
(unavailable). Desktop items carry `imported` (null when not brought in); notes follow state moves, so the mark
does too. The page: the engine-only card's Bring into the art folder (a dialog with the category, a list with the
guess or a new name), the From Unity chip on tiles and cards, the source and time on the card.

## App window and the portable folder

`python -m artbench --app` (`app_window`): when an Artbench already answers `/api/alive` on the port, it only opens
one more window. Otherwise it serves in a thread and opens the page in a Chromium browser's app mode
(`--app=<url>`, `--user-data-dir=.cache/app-window`, so the window is its own browser process and keeps its size):
`ARTBENCH_BROWSER` (a path or a name on PATH), then Edge, Chrome, Chromium (the Windows install folders; elsewhere the
macOS apps, then names on PATH); `ARTBENCH_BROWSER_ARGS` adds switches. The server stops when that process ends. A
browser that exits within 5 s handed the window to a process already running; then, and when no app browser
exists (a normal tab opens), the server stops after 5 minutes without a request. Without a console (`pythonw`)
output goes to `.cache/artbench.log`. The page has a web manifest (`web/manifest.webmanifest`, PNG icons) so the
window carries Artbench's name and mark. `python -m artbench shortcut` writes `Artbench.lnk` on the real desktop
(PowerShell, WScript.Shell; `pythonw -m artbench --app`, icon `web/img/artbench.ico`); on a Mac it writes
`~/Desktop/Artbench.command` (cd to the tool, `<python> -m artbench --app`, executable); elsewhere it says so.

**macOS.** The source folder's `Artbench.command` (executable) finds Python 3.11+ (python3.13 … python3) and starts
`-m artbench --app`; without one it says where to get it. Reveal and Open go through `open -R` / `open` (Finder), on
Linux through `xdg-open`, on Windows through Explorer and `os.startfile` (`actions.opener`). Blender is looked for
in `/Applications`, `~/Applications` and Steam's Mac folder. The folder dialog is AppleScript's `choose folder`
(`osascript`): Tk may open a window only on the main thread there, and the server answers from threads. File names
are compared by `files.name_key` (composed Unicode, lower case), since a Mac may store an accented name decomposed.
`.github/workflows/mac.yml` runs the suite and starts the server on a macOS runner, by hand.
The Mac download (`tools/build_portable.py --target mac-arm64 | mac-x64`, built on any system): python-build-standalone's
relocatable CPython (install_only, the same version as Windows', pinned by release tag and SHA-256, downloaded once
into dist/cache), trimmed of Tk, pip, tests, headers and manuals, with Artbench, the add-on, LICENSE/NOTICE, a Mac
README.txt and `Artbench.command` / `CreateShortcut.command` (they clear macOS's download mark on their own folder,
then run `./python/bin/python3.12`). The zip keeps each file's mode and links. The release and the public CI build
each Mac zip on a Mac with that chip (macos-latest, macos-15-intel), start it and ask `/api/alive` before it counts.

`tools/build_portable.py` (a build tool, outside the package) writes `dist/Artbench-portable-win64.zip`: one folder
`Artbench/` with python.org's embeddable Python in `python/` (its `python3XX._pth` gets `..`, so `artbench`
imports), the package, `blender_addon/` with `artbench_bridge.zip`, `Artbench.bat` (`start` pythonw `--app`, no console),
`ArtbenchSetup.bat` (prefers the bundled Python), `CreateShortcut.bat`, README_TR, LICENSE, NOTICE. No tests, docs,
samples or machine-local files: settings are written inside the folder on first use and travel with it. The
build checks that the package imports with `-I -S` (the standard library alone). The embeddable Python has no
tkinter, so the folder picker uses PowerShell's FolderBrowserDialog on Windows (UTF-8 output). The Electron build
at the end of the roadmap would wrap the same server.

## Conventions

- No deletion of project files, ever. Moves go between state folders; replaced files go to `_Archive/<date>/`; an
  engine asset nothing uses may be archived (moved out of the game project) and restored, see Archive.
- Every file change and every note/task change is one line in the history log.
- Writers of project data hold the project lock (`store.locked`); JSON files are written atomically
  (`store._write_json`). Blender runs (fingerprint, thumbnails) never happen under the lock.
- File hashes (`files.sha`) are cached in `.hash_cache.json`, one entry per path: size, nanosecond mtime, st_ctime
  and when it was hashed. A same-size rewrite gets a new hash; an entry hashed within 2 s of the file's last change is
  never trusted (two writes in one clock tick leave every stamp the same; found by the Windows CI run, 2026-11-04).
  Known limit on Windows: st_ctime is the creation time there, so an in-place rewrite that keeps the size and restores
  the exact old mtime on purpose is not seen until the file changes again. Reading NTFS's ChangeTime instead needs a
  file handle per file and cost more than a second per thousand files on the CI run, so it is not done. The file is written atomically from a copy, only after something new was hashed.
- Paths built from a slash-separated relative part are normalized (`os.path.normpath`), so one file has one spelling
  on Windows (preview and statistics caches are keyed by the path). Tests point both caches into their temp
  folder.
- Caches (`.hash_cache.json`, `.unity_dump_cache.json`, `.cache/<kind>/` for Blender outputs) live under `Artbench/`,
  never in a project. The old `.thumbs/` folder is unused and can be deleted by hand.
- Names in code, files and docs are English; `README_TR.md` is the Turkish user guide.
- Page copy lives only in `web/js/i18n.js` (`t(key, vars)`): English is the default, Turkish is selectable from the
  sidebar footer and remembered per browser (`localStorage`). Modules never contain user-visible strings; label
  tables in `state.js` (views, kinds, states, sync, usage) resolve through `t()` when read. Dates and numbers use
  the current language's locale. Server error messages stay English; the page translates the ones an artist meets.
  Both dictionaries hold the same keys, and no Turkish appears outside the Turkish dictionary.
- One schema per concept, defined here and reused; the page never invents fields.

## Roadmap

Done: the sync core (sync base, conflicts, pull, the force rule, the project lock, atomic writes); model diffs through
background Blender; asset packages and `.blend` binding; the local API, the command line and MCP; project mode (a game
project on its own: catalog, usage, changes, tasks); infrastructure hardening (engine adapters, the machine check, the
engine report contract v1); the app window and the portable folder; bringing a Unity model into the art folder; the
Blender add-on (the link, and notes kept in the `.blend`).

Next, in this order:
1. A canvas for tasks and for comparing art side by side.
2. A Blender MCP that works with or without Artbench: the scene, its changes, export templates per project.
3. Godot (an adapter producing the dump shape, see Extension points).

**Marks and export** (what an everyday asset tool has). `mark` op (ids, favorite?, revision?, note?, tags_add?,
tags_remove?) and `marks` list (filter favorite | revision, tag?, revision first); overview counts them (with
`tags: {tag: n}`, most used first, only when any asset has one), catalog filters by `mark` and by `tag`, and its
brief rows carry `fav` / `revision` / `tags` only when set. A tag has one form: lower case, single spaces, 1 to 40
characters (`marks.tag_name`); an asset with no star, flag or tag left has no entry; the page state carries the map. `export_plan` / `export`
(ids `engine:...`, dest) are the page's and the command line's (`PAGE_ONLY`: no MCP tool, an AI has no folder of
the person's to fill): one folder per model (Crate, Crate_2), its textures from `catalog.textures_of`, .meta left
behind, a file already there kept, a folder inside the game project or the art folder refused, one EXPORT line.

**Caches stay the size of what exists.** The Unity file cache (`unity_dump.CACHE_PATH`, shared by all projects)
drops, at every scan, the entries under the scanned Assets folder the scan did not look at (deleted, renamed, now
ignored) and the entries of any folder that no longer exists. The hash cache (`files.HASH_CACHE_PATH`) drops the
paths that no longer exist at the first save of a run. Rendered previews (`.cache/thumbs`) are trimmed to
`blender_jobs.PREVIEW_CACHE_LIMIT` (512 MB) when the Blender worker goes idle, the least recently used first (a
served preview's mtime notes its use, at most once a day); they are rebuilt on demand. Model measurements
(`.cache/meta`) are never trimmed: a change's before/after needs the old content's. A project on an unplugged drive
loses its cache entries and is read in full on its next scan; nothing else is lost.

**Archive** (`actions.archive_plan` / `archive` / `archived` / `restore`; the page's and the command line's,
`PAGE_ONLY`: moving files out of the game project is the person's click, never an AI's). An engine asset goes only
when nothing uses it (no `used_by`, project settings included) and it is not a scene in the build; one loaded by name
(Resources) goes with a warning. The file and its sidecars (.meta) move under the same path into
`<archive>/<date>/engine/<path under Assets>` (`sync.archive_path`: a second one on a day gets a time suffix):
`<archive>` is the art folder's archive, or `_Archive` in the project's data folder for a game project on its own,
never inside the game project. `archived.json` in the data folder records each `{id, path, time, files: {engine
path: archived file}}`, the latest first. Restore moves them back (the same .meta, so the GUID and the references
return) unless the place is taken again, which keeps it archived. One ARCHIVE / RESTORE line each; the dump is
marked stale so the catalog follows. The page: Archive… on the pick bar and the card, and an Archive view (More)
with Restore.

**Catalog search and CSV** (the page; an AI has the catalog op's own filters). Plain words match the name or
path; `kind:`, `usage:` (unused = unreferenced), `tag:`, `folder:`, `name:`, `is:` (fav, revision, unused, tagged,
build), `px:`, `tris:` and `size:` (>, <, >=, <=, =, with k, kb, m, mb, gb) narrow; a leading `-` turns a part
around; an unknown key is a plain word (`catalog.js` `queryTest`). CSV downloads the list as filtered and sorted:
id, name, kind, folder, path, usage, used_by, size_bytes, width, height, tris, favorite, revision, note, tags; UTF-8
with a BOM, a cell starting with = + - @ gets an apostrophe so a spreadsheet does not run it.

**One asset's history** (`changes.timeline(cfg, keys, paths)`): the history lines with a field that is one of the
asset's ids or a path ending in its path (so MARK, TASK, META, MOVE, BRING IN, SEND lines all count), and the change
feed's entries for its file (art and engine side; the baseline is left out), newest first. The `asset_history` op
gives it paged; the card shows it under History, collapsed to one line until opened.

**Checks** (advisory, nothing is changed). `checks` (what=standards, the default) answers `{total, counts per rule,
issues: [{id, rule, detail, level}]}`, paged, `rule` narrowing; what=duplicates answers `{total, wasted, groups:
[{sha, size, wasted, assets: [{id, path, kind, usage, used_by_count}]}]}`, the most wasted bytes first. Duplicates
take models, textures, audio and materials, grouped by size first so only likely copies are hashed (the tool's hash
cache). Standards: a texture whose imported size (the smaller of its side and the importer's max size) is over
`texture_max` (4096), a side that is not a power of two, Read/Write on, compression off, a name without its kind's
prefix (`naming`, off; T_, M_, PF_, SM_), a model over `tris_max` (off; Blender's count, so project mode only).
`checks_settings` (set: any of the rules; 0 turns a limit off) reads or writes them. The page's Checks view shows
both with a rules card; the page clears what it loaded when the files change.

Next on the bridge: pick models and pull them into one .blend, with or without textures, through
the Blender add-on, the place and file to save chosen by the person; exports from that .blend back the same way.
Particles (a VFX kind for .vfx and prefabs holding a ParticleSystem, with what they use) after that.

Later: issue-style tasks with images, the Unity editor bridge (live scene contents, particle previews), team mode, and
a portable Electron build. The core stays Python standard library.

### Kept ideas (not scheduled)

1. **Drag-and-drop upload.** `POST /api/upload` (multipart, size-capped) into `Outbox/<Category>/` or
   `FBX/<Category>/<Set>/`; the category is asked when it cannot be inferred.
2. **Health checks (lint).** `lint.py`: naming rules per kind, textures beside a model that nothing references,
   non-power-of-two textures, Blender files with missing textures, unapplied scale in FBX. Results in the scan state
   as `issues`, a counter in the sidebar.
3. **Contact sheet.** `sheet.py`: the thumbnails of a set composed into one PNG (grid, labels) for sharing.
4. **Collections** (decided 2026-10-23). `collections.py`: "what is inside" for anything that references art. Scenes
   are the built-in collection; project-specific ones come from the config:
   `"collections": [{"name": "Levels", "match": ["<glob>", ...], "type": "<ScriptableObject class>"?}]`. References
   are followed two steps (level -> prefab -> model/material/texture). Data assets appear only as collection titles,
   never as graph nodes. One page view with a group per collection; MCP tool `artbench_collection`.

Parked ideas (not on the roadmap): team mode below, UI assets, and running the Blender-side scripts through the pip
`bpy` module on machines without a Blender install (the test launcher shows it works).

## Parked: team mode (pull, push, review)

The host's Artbench is the origin, like a git remote; other artists run their own Artbench and connect to it.

- **Pull.** The remote exposes its library read-only (FBX, Blend, Textures, Stock, with thumbnails and the
  engine usage it knows). An artist picks files or whole sets and pulls them into a folder they chose, under the
  same relative layout (`FBX/<Category>/<Set>/...`), so both sides track the same ids. `remote.json` in the
  local art folder records the remote, each pulled file's hash and time. Pulling again updates in place; when the
  local copy was changed since the pull, the tool says so instead of overwriting. The remote logs every pull
  (who, what, when) so the host can watch activity.
- **Push.** An artist's finished work goes up as a submission: `Inbox/<artist>/<submission-id>/` on the host's
  side with `submission.json` (artist, title, note, target category/set, status open | approved | rejected,
  comment). Submissions stay there whatever the verdict; nothing is deleted.
- **Check on arrival.** Every submitted model is opened by background Blender (the same path as the thumbnail
  render) and the result is stored in `submission.json`: opens or not, mesh / material / bone counts, size,
  missing textures, unapplied scale, naming rule violations. The card shows a green "opens" or a red "does not
  open" line with the details; the reviewer can send it back with a note from the same card.
- **Review and merge (host only).** Inbox view with cards, server-rendered thumbnails, diff against the current
  copy (same / newer / new file), where the current copy is used. Approve moves the files into `Outbox/` or
  `FBX/<Category>/<Set>/` (old copy to `_Archive/<date>/`), reject returns a comment. History lines `PULL`,
  `SUBMIT`, `CHECK`, `APPROVE`, `REJECT`.
- **Security.** `--host 0.0.0.0 --token <shared secret>` enables remote access; without a token the server stays
  on 127.0.0.1. Remote callers get read-only listing + download + submission upload only: no moves, notes, tasks,
  deletes or folder picking; paths are validated against the art root (no traversal); upload size is capped.
  A viewer types a name once (stored per browser) and it is written into every log line.
- **Modules.** `remote.py` (client side: connect, list, pull, push), `submissions.py` (host side: inbox CRUD and
  review), new routes under `/api/remote/*` and `/api/inbox/*`, MCP tools `artbench_inbox`, `artbench_review`.

## Extension points

- Another engine: a new adapter module producing the dump shape; `engines.dump` picks it by `cfg["engine"]`.
- The Blender add-on (`blender_addon/artbench_bridge/`): standard library and bpy only, it talks to `/api/v1`; new
  abilities (scene, export templates) are new operations there, never Artbench code inside the add-on.
- More analyses: a module with `build(cfg, dump, ...)` or `check(cfg, dump)` and one GET route.
