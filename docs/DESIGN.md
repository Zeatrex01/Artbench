# Artbench page design

Brand: **Artbench**, with the Trestle mark: a board on an A-frame trestle (the A of Art) with a pencil resting on it, one colour (the A at
62 %), in
`js/icons.js` (`MARK`) and `img/favicon.svg`. Tone ("Workshop"): dark, dense and quiet like the DCC tools open beside it (Blender, Unity); graphite greys, 1 px
lines, small corners, no gradients, glows or coloured cards. Amber marks the selection and little else; status colours
are muted and always paired with a shape (filled dot: in use, hollow ring: nothing uses it). No default HTML
looks: every control, chip and card follows the tokens below. Page copy in English by default with Turkish selectable
(all of it in `js/i18n.js`), identifiers in English.

## Files (`artbench/web/`)

```
index.html          shell: sidebar, main (topbar + view), inspector, projects screen, toasts, modal
css/tokens.css      colours, type, spacing, radii, shadows (the only place values live)
css/app.css         components and views, built on the tokens
js/app.js           boot, polling, routing between views
js/api.js           fetch wrappers (/api/*), errors -> toast
js/ui.js            helpers: esc, icon(), toast(), modal(), formatters, local storage
js/icons.js         inline SVG set (Lucide, ISC: THIRD_PARTY_NOTICES.md) and the Trestle mark
js/launch.js        the opening: plays once per browser session, skipped by any key or click
img/favicon.svg     the Trestle mark on a dark tile, amber
js/thumbs.js        lazy thumbnail loader (200 / 202 retry / 404 placeholder), shared cache
js/state.js         S (data, filters, selection), derived helpers (setOf, counts, filtered)
js/sidebar.js       brand, project pill, nav, tree, filter pills, stamps
js/library.js       stat tiles, grouped grid / list, cards
js/inspector.js     detail panel: hero, paths, actions, state bar, send, used-by, textures, source, tasks, note
js/tasks.js         kanban view + shared task buttons
js/graph.js         canvas force graph with thumbnails in model nodes
js/views.js         engine-only, placeholders, layout, blends, changes, history, unsorted
js/projects.js      the projects hub: connect (Game project only, default, or game project + art folder) with its
                    progress, link, detach;
                    the AI connection card; the machine check
js/catalog.js       project mode: art catalog by kind, unused view, asset card, kind navigation, previews and
                    model statistics in rows and cards, sort, hidden folders, Open in Blender
js/scenes.js        scenes and what each one uses: the list (filterable) beside one scene's assets by kind
js/marks.js         stars, revision flags and tags, picking several assets, the pick bar, the Marked view, export to a folder
js/checks.js        the Checks view: standards by rule, duplicates with what uses each copy, the rules card
js/i18n.js          every user-visible string, English and Turkish; t(key, vars)
```
The server serves these as static files; `index.html` loads `js/app.js` as an ES module.

## Tokens

| Token | Value | Use |
|---|---|---|
| bg | #161616 | page |
| s1 / s2 / s3 / s4 | #1b1b1b / #212121 / #282828 / #303030 | sidebar+inspector / inputs+plates / hover / active |
| line / line2 | rgba(255,255,255,.075) / .15 | borders / strong borders |
| text / muted / dim | #e4e4e4 / #a8a8a8 / #878787 | |
| accent / accent2 / accent-soft | #e8a33d / #f0b75e / rgba(232,163,61,.13) | the selection only (rows, tiles, figure), the opening's mark |
| ok / warn / bad / info / violet | #8fbf7a / #d98c52 / #e0705f / #79a6dc / #a993d9 | status shapes, kinds; never a filled pill |
| `*-line`, `*-ink`, `*-glow`, `focus-ring`, `glass`, `scrim`, `shadow-side`, `shimmer`, `text-strong` | fixed strengths of the colours above | borders, text on tinted surfaces, overlays; app.css has no raw colour values |
| font | IBM Plex Sans (UI) and IBM Plex Mono (paths, numbers), Google Fonts, system fallbacks; Archivo (wide, 660) only for the wordmark in the opening | |
| type scale | 11 / 12 / 13 / 14 / 16 / 20 / 22 | labels / meta / body / names / titles / stats |
| radius | 2 controls, 3 cards, 4 panels; no pills | |
| spacing | 4 / 8 / 12 / 16 / 20 / 24 | |
| motion | 100 ms ease; nothing lifts on hover; slide-in 140 ms | |
| opening | 3.5 s and a 0.36 s wipe upward: a pencil draws the mark (the A's two legs and bar, then the board) and is then lifted, turned level and dropped onto the board, which gives under it; the name rises with a little spring. Simulated, not keyframed (`makeMotion` in `launch.js`): the lead follows the hand on springs (late, a little past a line's end), the body leans with the stroke, a lifted pencil grows and casts a shadow, the drop falls under gravity and rocks level. None under reduced motion; never blocks clicks | |

Primary buttons are light grey with dark text; figures (stats) are a row of numbers between hairlines, not cards.
Semantic mapping: state ingame ok, outbox warn, stock/archive dim, engine-only info, placeholder violet;
usage used ok / unused warn; sync same ok, desktop newer warn, engine newer info, missing bad.
Asset kinds: model accent, mesh violet, texture ok, material warn, prefab info, scene pink, clip teal,
animator bad, data muted.

## Layout

- **Sidebar 240px**: brand (the Trestle mark, amber, + "Artbench"), project pill (select), Connect a project, nav with
  icons and counts. Tasks comes first: people keep Artbench open beside their AI tools and look at the board most.
  Art mode: Tasks, Library, Engine only, Changes, Scenes, then under **More** Placeholders, Layout, Graph, Blender
  sources, History, Unsorted (when >0). Project mode: Tasks, Art catalog, Unused, Changes, Scenes, then under More
  Placeholders and Layout. More stays open while one of its views is open, remembers being opened, and shows a dot
  when a view under it has something to look at. A project still opens on its assets (catalog or library) when the
  remembered view is not one of its own. Then the category → set tree and filter pills (library only), footer:
  Projects, language, scan stamps. Turkish names come from `i18n.js`.
- **Marks and picks**: a star (amber, filled) and a Revision chip (warn, with a flag) on rows, tiles and the card;
  the card's mark row toggles both and, while flagged, keeps the revision note in a field. Every row and tile has a
  pick box (shown on hover, or ticked); Shift picks a range. While anything is picked a bar sits at the bottom:
  how many, Favorite (or Unstar when all are), Revision coming (asks for an optional note), Export N models to a
  folder (game-project models only: the folder dialog, then the plan in a dialog, then the copy), Clear. **Marked**
  (second in the menu) lists what waits for a revision with its note first, then the favourites, with All /
  Waiting for a revision / Favorites; the catalog's filters gain Favorites and Waiting for a revision. Bringing a
  Unity model into the art folder asks for the category and offers its textures, ticked.
  Tags: small outlined mono chips after the star and the revision chip (two on a row, then +n); on the card, the
  tags with a cross each and a field (Enter adds, the project's other tags suggested); the pick bar's Tag… asks
  for one and adds it to every picked asset; the sidebar's Tags pills filter the catalog, and Marked has the
  same pills beside its switch.
- **Checks**: Standards / Duplicates as a segmented switch with counts, Rules beside it. Standards: one figure per
  rule (its count, a status dot for the rules that have issues, quiet at zero; a click narrows to that rule), then
  the issues grouped by rule, each row with the detail and a Worth fixing (warn) or Note (info) chip. Duplicates: two
  figures (files with copies, the space the copies take), then one group per file with each copy, its usage and
  what uses it. The rules card: largest texture (a select), triangle budget, four checkboxes, name prefixes while
  naming is on, Save rules. Nothing on the page changes a file of the game project.
- **Polling**: every 4 s while the window is in front; about every 30 s while it is open behind other windows (kept
  open for AI tools); never while minimised. Coming back to the window refreshes at once.
- **Main**: topbar (view title + count, search with `/` hint, grid/list toggle, refresh), scrolling view.
- **Inspector 380px**: appears when something is selected, slides in; overlays below 1250px.
- **Projects screen**: a full-screen hub, shown on first run, from the sidebar's **Connect a project** button (under the
  project pill) or the pill's Manage entry. Connecting comes first: the Unity project folder in a large pick area, two
  plain tiles (Game project only / Game project + art folder), the name, Connect; linking an existing art folder folds
  under it. While a connect runs, that area shows its progress: one bar, a row per stage (checking the folder, listing
  the files, the .meta files n / N, what uses what n / N, the project settings, opening the catalog) and the file being
  read. Stages follow `/api/projects/progress` and each stays on screen at least 320 ms, so a small project still reads
  step by step; counts and the bar ease toward the server's numbers and never go back. Below: the connected projects
  as cards (the open one outlined in amber), then the AI connection, the machine check and the About card.

## Views

- **Library**: six stat figures (big numbers, clickable filters; no tiles) then groups per state → category → set,
  ingame first, archive collapsed. Grid cards: square thumbnail on a flat backdrop, name, state chip, usage and
  sync dots, texture count, note caption. List mode: 48px thumb rows.
- **Inspector**: hero thumb, name + meta, chips, copyable paths, ambiguous engine match select, actions
  (Show in folder / Show in Unity / Show in graph / Open in Blender for models), "Send to Unity" when outbox or
  desktop newer
  (plan → modal with fingerprint warnings → send), state segmented bar (moves after modal), sync callout,
  used-by grouped by kind with reveal buttons, textures, Blender source, tasks for the asset, note.
- **Görevler**: three kanban columns, add row, status advances with a button, delete after modal.
- **Layout**: off until turned on, and its count is hidden while off. Off, it says what it does ("where each kind
  of asset belongs") with one button. Turning it on shows the rules it learned from where the assets are now;
  each issue card has Allow this folder next to the hint and reveal buttons. Advisory, never moves anything.
- **Graf**: results card (search, Komşuluk / Sadece kullanılmayan) + canvas; focus node + 2 hops (≤160 nodes),
  force layout, kind colours, arrows referrer → referenced, `.asset` files (data, code meshes) left out, dashed ring = unused, white dot = has desktop copy,
  **model nodes draw their thumbnail**, hover tooltip, click recentres, double-click opens the asset, drag pans,
  wheel zooms.
- **Değişiklikler / Geçmiş**: timelines grouped by day (chips for verb, mono paths).
- **Sadece motorda / Geçiciler / Blender / Sınıflanmamış**: card or row lists with the same chips; callouts
  explain what the list means.
- Empty states (icon + one sentence) everywhere; errors as toasts bottom-right; confirmations in a modal,
  never `window.confirm`.

## Project mode (the game project on its own)

A project-mode project has no art folder, so the page shows a different set of views:
**Art catalog · Tasks · Unused · Placeholders · Scenes · Changes · Layout**. Library, Engine only, Blender sources,
History, Unsorted and Graph are not shown; the card has no send, pull, state bar, note or Changes (Blender) section.

- **Art catalog**: stat tiles (assets with the number of kinds, in use, unreferenced, by name, unknown only when
  there is any, new changes since the last look, open tasks with how many are high priority; usage tiles filter,
  the last two open their views), then one collapsible group per kind (models, prefabs, materials, textures, scenes,
  meshes, animators, clips, shaders, audio, fonts, atlases) of rows: a tinted kind icon, the name, the folder in
  mono, the usage chip, "in the build" for build scenes, open tasks, "used by N", size. Model and texture rows
  show their preview instead of the kind icon; model rows add triangles, texture rows resolution and format.
  A sort control (name, largest first, most triangles, recently changed) orders the rows of each group; each
  folder group has Hide, and a Hidden folders line under the figures shows them again. The sidebar lists the kinds
  with counts (a click filters) and usage pills (only the ones that occur).
- **Usage words and colours**: in use ok, unreferenced warn, loaded by name info, unknown dim. The card always
  explains the word in a callout; "unreferenced" says to check before deleting.
- **Asset card**: kind label, large kind icon with name, folder and size, usage chip and explanation, the Unity
  path, the preview and statistics (triangles, vertices, materials, bones, animations; for a texture its
  resolution, format and size), Used by and Uses as rows (name over folder; a click opens that asset), tasks for
  the asset with an add field, Show in folder, Open in Blender for models.
- **Tasks**: the same three columns; every card starts with a priority pill (high bad-tinted, normal accent, low
  muted; a click cycles it) and a high task has a red left edge. Cards keep the server's order: priority, then
  oldest. The add row has title, priority, asset (the catalog in project mode) and note. Tasks an AI adds over MCP
  appear on the next poll.
- **Scenes**: one scene at a time. A sticky list on the left (filter box, each scene with its folder, how many assets it
  uses, a green dot when the Unity bridge reported it, an amber one for unsaved changes); on the right the selected
  scene: its name, path and source chip, a row of figures between hairlines (All, then one per kind; a click narrows
  the list to that kind), then its assets grouped by kind in columns, each with its preview or kind icon, folder and
  ×count. Below 1100px the list sits above the scene.
- **Changes**: a bar with how many are new since the last Mark as seen and the button, then New and Earlier
  timelines; a moved asset shows old path → new path.
