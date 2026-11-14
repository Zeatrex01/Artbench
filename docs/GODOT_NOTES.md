# Godot: notes from the first real run (2026-11-14)

The first time Artbench ran on a real Godot project: a Godot 4.7 game, about 550 files, run headless in project mode
(`python -m artbench setup <game>`, then `call overview / unused / checks / refresh`). Below: what it got right, what
it missed and why, what branch `godot-refs` changes, and what is still open. Every number below was measured on the
same game commit with Python 3.11, 3.13 and 3.14.

## What worked
- Setup, the dump and every call ran with no change; the dump took under a second.
- Kinds from extensions and `.tres` headers were right: 81 textures, 61 materials, 26 prefabs, 6 fonts, 4 models,
  4 scenes, 3 shaders.
- The 4 models were exactly the game's 4 downloaded glTF props.
- `.gdignore` folders and hidden folders were skipped, as Godot does.
- Nothing was written into the game; all records stayed in `projects/<id>/`.

## What it missed (before `godot-refs`)
65 files were reported "unreferenced". 30 of them are in use, and 1 more is named by a game script:

| Cause | Files | Example |
|---|---|---|
| Binary resources (`.res`) were never read. A mesh's materials are named only inside its `.res`. | 8 materials | `wall_plate_face.tres`, named by `wall_plate_*.res` |
| A script builds the path: a folder constant plus a file name. | 4 fonts | `FONT_DIR := "res://assets/fonts/"`, then `"Inter-Regular.otf"` |
| A `.gltf` names its textures by relative `uri`, not by `res://`. | 18 textures | `textures/metal_trash_can_diff_1k.jpg` |
| A game script names the file by its bare name only (a lookup key). | 1 material | `pool_band_mosaic.tres`, a key of `FLOOR_SOUND` |

It also did not see:
- **31 engine-built meshes** (`.res`, kind `asset`, so hidden). On this game they are most of what the player sees.
- **46 engine-built textures** (`ImageTexture` saved as `.res`).

The other 34 really are named nowhere by the game: 14 old scanned textures, one font, 17 map images under `docs/`,
and two exit-sign materials that only the game's own tool scripts name. Godot imports the map images because the
game has no `.gdignore` in `docs/`. That is the game's problem, not Artbench's.

**Texture check.** `uncompressed` warned on every texture with the bare message "compression is off". In Godot,
`compress/mode=0` plus `detect_3d/compress_to=1` is the importer's default. It means "lossless until the editor sees
the texture used in 3D". The warning is right, but its text should say this.

## What branch `godot-refs` changes
- **`godot_dump._read_binary`** reads `.res` and `.scn` files the way Godot's `ResourceLoaderBinary::open` does:
  - The class, the file's own uid and each external resource (its path and its uid) come from the header. Godot
    stores those uids as raw int64 numbers, not as `uid://` text; they are turned into Godot's text form
    (`ResourceUID::id_to_text`, base 34). Checked against Godot 4.7 itself: the text matched
    `ResourceLoader.get_resource_uid()` for three files saved by the editor. (This game's 77 binaries were saved by
    tool scripts and carry no uids, so here the paths do all the work.)
  - A path saved relative to the file (`FLAG_RELATIVE_PATHS`) is resolved from the file's folder.
  - Header strings are read as Godot reads them: a signed 32-bit length, then UTF-8. A negative length is a broken
    file (Godot 4.7 crashes on one), so the file is listed as unreadable.
  - The internal-resource table is skipped, not read for paths. It holds the path the file was saved under, so a
    file that was renamed or moved still names its old self there, and Godot does not load it. (Before: a renamed
    `box_plain_2.res` made `box_plain.res` "used".)
  - Strings in the body are read with their length prefix, so a path with a space or a non-ASCII letter comes out
    whole (`res://sub dir/mät é.tres`).
  - Compressed files (`RSCC`) are opened per block: Deflate and Gzip through `zlib`, Zstd through `compression.zstd`
    (Python 3.14+). Godot compresses a binary resource only when it is saved with `ResourceSaver.FLAG_COMPRESS`, and
    then with Zstd, its default compression mode. Saved without the flag, the file is plain `RSRC`. This game has 45
    Zstd and 32 plain binaries.
  - A `.res` gets its kind from its header class: `ArrayMesh` is a mesh, `ImageTexture` is a texture, `PackedScene`
    is a scene (as `.tres` too). The class lists also gained `TorusMesh`, `TextMesh`, `PlaceholderMesh`,
    `CurveTexture`, `Texture2DArray`, the cubemap and 3D textures, audio streams and font resources.
- **No file can stop the scan.** Every reader is wrapped. A file that cannot be read is listed in the dump's
  `unreadable` with its reason, `overview` counts it (`unreadable_resources`), `unused` lists it, and the page shows
  a warning with the count above the catalog and the Unused list (the files and reasons fold out). The reasons:
  - `corrupt: ...` (truncated, block size 0, a count larger than the file, a negative string length, a block that
    does not unpack, not JSON, JSON nested too deep, a glTF that is not an object, a uri that is not a string),
  - `compressed with Zstd: needs Python 3.14 or newer to read (this is 3.11)`,
  - `compressed with FastLZ` or `Brotli`, which Artbench cannot read,
  - `too large to read` (over 64 MB on disk, or over 256 MB unpacked),
  - `not a regular file` (a named pipe, socket or device with a resource extension: before, a pipe blocked the scan
    forever),
  - `the name is not valid UTF-8` (before, such a name stopped `refresh` and `unused`).

  Before Python 3.14 a damaged Zstd file shows the Zstd reason: it cannot be unpacked to tell. The `.gltf` reader the
  catalog uses (`files._gltf_uris`) no longer stops every call on a deeply nested file either.
- **`.gltf`**: `images[].uri` and `buffers[].uri` are resolved from the file's own folder and made relative to the
  scanned project folder (not to the nearest inner `project.godot`).
- **Scripts** (`.gd`, `.cs`):
  - A folder + name join is a reference when all of these hold: the script quotes a `res://…/` folder (or `res://`
    itself), and joins it onto something (the literal, or the `const` / `var` holding it, is followed by `+` or
    `.path_join`); the script quotes a file name that is not a dictionary key; and folder + name is a file of the
    project. In this game that is `FONT_DIR + ...` with the font names as dictionary values. Each name is looked up
    in the project's file index, so a script with many folders and names stays quick (1500 x 1500: 2.35 s and 2.25
    million paths in memory before, 0.01 s now).
  - Any other quoted file name, with or without a subfolder (a dictionary key, a compared name, a folder that is
    never joined), is weaker: the file gets usage `by_name`, "named by a game script, not loaded". `unused` lists it
    apart from the unreferenced files, and the page labels it "Name only".
  - Scripts in tool, probe, dev and test folders do neither: their bare names and folder joins do not count. Their
    full `res://` paths still do. The folders are `godot_dump.DEFAULT_DEV`
    (`tools, tool, probes, probe, dev, debug, test, tests, scratch`); config key `engine_dev_dirs` replaces the list.
- **`checks`**: the `uncompressed` text names `detect_3d` when the import file has it on, and says "lossless" for
  `compress/mode=0` and "VRAM uncompressed" for mode 3.

### Measured on the same game (the same commit, before and after)
| | before | after, Python 3.14 | after, Python 3.11 and 3.13 |
|---|---|---|---|
| listed (shown kinds) | 185 | 262 | 217 |
| meshes listed | 0 | 31 | 3 (the uncompressed ones) |
| used / by name / unreferenced | 120 / 0 / 65 | 218 / 1 / 43 | 175 / 1 / 41 |
| unreadable files | not reported | 0 | 45 (all Zstd) |

The 43 on 3.14 are:
- **The same 34 as above.**
- **6 meshes** a script picks by a format string: `"door_leaf_%dx%d" % [...]`, the troffer sizes. These are correctly
  unreferenced as far as text can tell; the existing "built at run time, check before deleting" note covers them.
- **2 engine-built trim textures** and **1 old lamp mesh** (`uv_lamp.res`, replaced by `camcorder.res`; only its
  build tool names it) that nothing in the game loads. These are new, real finds.

On 3.11 and 3.13 the 41 are the same 34, the trim textures and the lamp mesh, and 4 materials that only Zstd `.res`
files name (`bin_rust`, `column_join_shadow`, `sign_plate_grey`, `wall_plate_face`).

## Still open
- **Before Python 3.14** (3.13 has no `compression.zstd` either): Zstd `.res` files stay unreadable, and the 4
  materials that only they name stay "unreferenced". The overview counts them and `unused` names each one with the
  reason. Two options:
  - Say in the overview that 3.14 is needed.
  - Accept an optional `zstandard` module.

  The stdlib-only rule is kept either way.
- **Format strings.** Paths built with `%` or `str()` are not followed. A third usage state, "named by pattern", could
  hold files whose name fits a quoted pattern such as `"door_leaf_%dx%d"`.
- **Joins are read from text, not run.** A script that joins a folder and also quotes an unrelated file name that
  is not a dictionary key still makes folder + that name "used". The game has no such case.
- **Dev folders are matched by name.** A game script kept in a folder called `tools` or `debug` loses its joins and
  bare names until `engine_dev_dirs` is changed.
- **Use is not followed from the main scene.** A file referenced only by a dead file still counts as used:
  `uv_lamp_metal.tres` is named only by the dead `uv_lamp.res`.
- **`.glb`** files are not read for external texture uris (the JSON chunk inside the binary).
- **No tests.** The repo has no test folder. A small fixture project (one `.res` of each compression mode, one
  `.gltf`, one script with a folder constant, the damaged files above) would pin all of this down.
- **Not tried:** art mode against a Godot engine root, a `.scn` file, a `.cs` project.
