# Godot: notes from the first real run (2026-11-14)

The first time Artbench ran on a real Godot project: a Godot 4.7 game, about 550 files, run headless in project mode
(`python -m artbench setup <game>`, then `call overview / unused / checks / refresh`). Below: what it got right, what
it missed and why, what branch `godot-refs` changes, and what is still open.

## What worked
- Setup, the dump and every call ran with no change; the dump took under a second.
- Kinds from extensions and `.tres` headers were right: 81 textures, 61 materials, 26 prefabs, 6 fonts, 4 models,
  4 scenes, 3 shaders.
- The 4 models were exactly the game's 4 downloaded glTF props.
- `.gdignore` folders and hidden folders were skipped, as Godot does.
- Nothing was written into the game; all records stayed in `projects/<id>/`.

## What it missed (before `godot-refs`)
65 files were reported "unreferenced". Checked one by one, 33 of them were in use:

| Cause | Files | Example |
|---|---|---|
| Binary resources (`.res`) were never read. A mesh's materials are named only inside its `.res`. | 11 materials | `wall_plate_face.tres`, named by `wall_plate_*.res` |
| A script builds the path: a folder constant plus a file name. | 4 fonts | `FONT_DIR := "res://assets/fonts/"`, then `"Inter-Regular.otf"` |
| A `.gltf` names its textures by relative `uri`, not by `res://`. | 18 textures | `textures/metal_trash_can_diff_1k.jpg` |

It also did not see:
- **31 engine-built meshes** (`.res`, kind `asset`, so hidden). On this game they are most of what the player sees.
- **46 engine-built textures** (`ImageTexture` saved as `.res`).

The other 32 really are named nowhere: old scanned textures, one font, and 17 map images under `docs/`. Godot imports
those map images because the game has no `.gdignore` in `docs/`. That last point is the game's problem, not Artbench's.

**Texture check.** `uncompressed` warned on every texture with the bare message "compression is off". In Godot,
`compress/mode=0` plus `detect_3d/compress_to=1` is the importer's default. It means "lossless until the editor sees
the texture used in 3D". The warning is right, but its text should say this.

## What branch `godot-refs` changes
- **`godot_dump._read_binary`** reads `.res` and `.scn` files:
  - It takes the class from the header and the `res://` and `uid://` strings from the body (the external resources).
  - Compressed files (`RSCC`) are opened per block: Deflate and Gzip through `zlib`, Zstd through `compression.zstd`
    (Python 3.14+). Godot writes `.res` files as Zstd by default.
  - A file this Python cannot open is listed in the dump's `unreadable`, and the overview counts it in
    `unreadable_resources`. Before, these were missed with no warning.
  - A `.res` gets its kind from its header class: `ArrayMesh` is a mesh, `ImageTexture` is a texture, `PackedScene`
    is a scene (`RESOURCE_KIND` gained a texture row).
- **`godot_dump._gltf_uris`**: a `.gltf` file's `images[].uri` and `buffers[].uri` are resolved from the file's own
  folder and count as references.
- **Scripts** (`.gd`, `.cs`): each quoted `res://…/` folder in a file is joined with each quoted file name in the same
  file. A joined path counts only if the file exists.
  - A bare file name that matches exactly one file in the project counts as well.
  - Example: `pool_band_mosaic.tres`, which a script names as a lookup key.
- **`checks`**: the `uncompressed` text names `detect_3d` when the import file has it on (`engines/godot.py` now reads
  `detect_3d/compress_to`).

### Measured on the same game (the same commit, before and after)
| | before | after, Python 3.14 | after, Python 3.11 |
|---|---|---|---|
| listed (shown kinds) | 185 | 262 | 217 |
| meshes listed | 0 | 31 | 3 (the uncompressed ones) |
| used / unreferenced | 120 / 65 | 222 / 40 | 183 / 34 |
| unreadable compressed resources | not reported | 0 | 45 |

The 40 on 3.14 are:
- **The same 32 as above.**
- **6 meshes** a script picks by a format string: `"door_leaf_%dx%d" % [...]`, the troffer sizes. These are correctly
  unreferenced as far as text can tell; the existing "built at run time, check before deleting" note covers them.
- **2 engine-built trim textures** that nothing loads. These are new, real finds.

## Still open
- **Python 3.11.** Zstd `.res` files stay unreadable, and the materials that only they name stay "unreferenced". Two
  options:
  - Say in the overview that 3.14 is needed (the count is already there).
  - Accept an optional `zstandard` module.

  The stdlib-only rule is kept either way.
- **Format strings.** Paths built with `%` or `str()` are not followed. A third usage state, "named by pattern", could
  hold files whose name fits a quoted pattern such as `"door_leaf_%dx%d"`.
- **No tests.** The repo has no test folder. A small fixture project (one `.res` of each compression mode, one
  `.gltf`, one script with a folder constant) would pin all of this down.
- **Not tried:** the page server, art mode against a Godot engine root, a `.scn` file, a `.cs` project.
