// Page state (S), vocabularies and pure derived helpers. Views read S; only app.js and user actions change it.
// `actions` is filled by app.js so views can trigger navigation/selection without importing app.js (no cycles).
import { t } from './i18n.js';
import { esc, prefs } from './ui.js';

export const actions = {};          // setView, select, refresh, switchProject, openProjects, render, renderView

export const S = {
  project: prefs.get('project', null), projects: [],
  about: null, data: null, tasks: [], blenderNotes: [], history: [], changes: [], graph: null,
  view: prefs.get('view', 'library'), listMode: prefs.get('listMode', 'grid'), search: '',
  filters: { state: null, usage: null, sync: null, category: null, set: null },
  selected: null, graphFocus: null,
  closedGroups: prefs.get('closedGroups', {}), closedCats: prefs.get('closedCats', {}),
  hashes: {}, busy: false, assetsRoot: null, scenes: null, engineStatus: null,
  sinceSeen: [], picked: new Set(), markFilter: 'all', catFilters: { kind: null, usage: null, folder: null, mark: null }, catGroup: prefs.get('catGroup', 'kind'), catSort: prefs.get('catSort', 'name'),   // project mode
};

/** [view key, i18n key of its label, icon, more]: Tasks first (the view people keep open); views marked more wait under
 * the sidebar's More. */
export const VIEWS = [
  ['tasks', 'nav.tasks', 'checksq'], ['marked', 'nav.marked', 'star'], ['library', 'nav.library', 'grid'], ['engine', 'nav.engine', 'inbox'],
  ['changes', 'nav.changes', 'diff'], ['scenes', 'nav.scenes', 'clapper'],
  ['placeholders', 'nav.placeholders', 'cube', true], ['layout', 'nav.layout', 'map', true], ['graph', 'nav.graph', 'share', true],
  ['blends', 'nav.blends', 'blender', true], ['history', 'nav.history', 'clock', true], ['unsorted', 'nav.unsorted', 'question', true],
];
/** Views of a project-mode project (the game project on its own, no art folder). */
export const VIEWS_PROJECT = [
  ['tasks', 'nav.tasks', 'checksq'], ['marked', 'nav.marked', 'star'], ['catalog', 'nav.catalog', 'grid'], ['unused', 'nav.unused', 'inbox'],
  ['changes', 'nav.changes', 'diff'], ['scenes', 'nav.scenes', 'clapper'],
  ['placeholders', 'nav.placeholders', 'cube', true], ['layout', 'nav.layout', 'map', true],
];
export const isProject = () => S.data?.mode === 'project';
export const viewsFor = () => (isProject() ? VIEWS_PROJECT : VIEWS);
/** Where a project opens when the remembered view is not one of its own: its assets (a new project's board is empty). */
export const homeView = () => (isProject() ? 'catalog' : 'library');
const kind = (icon, color, key) => ({ icon, color, get label() { return t(key); } });
export const KIND = {
  model: kind('box', '#6f7dff', 'kind.model'), mesh: kind('cube', '#b48cff', 'kind.mesh'),
  texture: kind('image', '#3ecf8e', 'kind.texture'), material: kind('droplet', '#f5b942', 'kind.material'),
  prefab: kind('package', '#5ab0ff', 'kind.prefab'), scene: kind('clapper', '#ff7ab6', 'kind.scene'),
  clip: kind('play', '#39c6c0', 'kind.clip'), animator: kind('activity', '#ff6b6b', 'kind.animator'),
  data: kind('database', '#9aa3b2', 'kind.data'), audio: kind('music', '#c0c6d1', 'kind.audio'),
  atlas: kind('image', '#3ecf8e', 'kind.atlas'), shader: kind('activity', '#39c6c0', 'kind.shader'),
  font: kind('list', '#c0c6d1', 'kind.font'), settings: kind('settings', '#9aa3b2', 'kind.settings'),
  other: kind('box', '#646c7a', 'kind.other'),
};
const labels = (prefix, keys) => Object.fromEntries(keys.map(k => [k, { get: () => t(`${prefix}.${k}`), enumerable: true }]));
export const STATE_LABEL = Object.defineProperties({}, labels('state', ['ingame', 'outbox', 'stock', 'archive', 'engine_only']));
export const STATE_CLS = { ingame: 'ok', outbox: 'warn', stock: 'dim', archive: 'dim', engine_only: 'info' };
export const STATE_ORDER = { ingame: 0, outbox: 1, stock: 2, archive: 3 };
/** sync state -> [css class, label]; the label is translated when read. */
const pair = (cls, key) => { const a = [cls]; Object.defineProperty(a, 1, { get: () => t(key), enumerable: true }); return a; };
export const SYNC = {
  same: pair('ok', 'sync.same'), desktop_newer: pair('warn', 'sync.desktop_newer'), engine_newer: pair('info', 'sync.engine_newer'),
  missing_in_engine: pair('bad', 'sync.missing_in_engine'), not_on_desktop: pair('info', 'sync.not_on_desktop'), conflict: pair('bad', 'sync.conflict'),
};
export const USAGE = { used: pair('ok', 'usage.used'), unused: pair('warn', 'usage.unused') };
export const TASK_NEXT = { todo: 'doing', doing: 'done', done: 'todo' };
export const TASK_NEXT_LABEL = Object.defineProperties({}, labels('task.next', ['todo', 'doing', 'done']));

/** Any entry by id: desktop item, engine-only model or placeholder. */
export function findEntry(id) {
  if (!S.data || !id) return null;
  return S.data.items.find(i => i.id === id) || S.data.engine_only.find(i => i.id === id) || S.data.placeholders.find(i => i.id === id)
    || (S.data.catalog?.assets || []).find(i => i.id === id) || null;
}
/** The set key of a model that sits right in its category folder. No real set can be named so: every walk skips
 * folders whose name ends with "~". The page shows setLabel(). */
export const NO_SET = '~';
/** Set key of a desktop item: the folders between its category and the file (NO_SET when none). */
export function setOf(item) {
  const parts = item.id.replace(/^\.\.\//, '').split('/');
  const ci = parts.findIndex(p => p.toLowerCase() === (item.category || '').toLowerCase());
  const between = ci >= 0 ? parts.slice(ci + 1, -1) : parts.slice(1, -1);
  return between.length ? between.join(' / ') : NO_SET;
}
/** What the page shows for a set key: "(no set)" in the page's language for NO_SET. */
export const setLabel = set => (set === NO_SET ? t('lib.noSet') : set);
/** Sets in order, NO_SET first. */
export const bySet = (a, b) => (b === NO_SET) - (a === NO_SET) || (a < b ? -1 : a > b ? 1 : 0);
export function assetsRootOf(engineRoot) {
  if (!engineRoot) return null;
  const norm = engineRoot.replace(/\\/g, '/');
  const i = norm.indexOf('/Assets');
  return i >= 0 ? norm.slice(0, i + 7) : norm;
}
export const enginePathAbs = relToAssets => (S.assetsRoot ? S.assetsRoot + '/' + relToAssets : relToAssets);
export function relToAssets(absPath) { const n = absPath.replace(/\\/g, '/'); const i = n.indexOf('/Assets/'); return i >= 0 ? n.slice(i + 8) : n; }

export function matches(entry, q) {
  if (!q) return true;
  const hay = [entry.name, entry.id, entry.category, entry.note, entry.engine_path, entry.category ? setLabel(setOf(entry)) : ''].join(' ').toLowerCase();
  return q.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}
export function filteredItems() {
  const f = S.filters;
  return S.data.items.filter(i => (!f.state || i.state === f.state) && (!f.usage || i.usage === f.usage) && (!f.sync || syncOf(i) === f.sync)
    && (!f.category || i.category === f.category) && (!f.set || setOf(i) === f.set) && matches(i, S.search));
}
/** Engine folder configured but not readable right now (unplugged drive, other machine): sync states are not trustworthy. */
export const engineUnreachable = () => !!S.data?.engine_unreachable;
/** The sync state lists and counters show: the package's worst file state, else the model's own. */
export const syncOf = i => i.package?.state ?? i.sync;
/** Package files (not the model) whose state differs from "same", for tooltips. */
export const changedFiles = i => (i.package?.files || []).filter(f => f.role !== 'model' && f.sync && f.sync !== 'same').map(f => f.name);
export function counts() {
  const d = S.data, items = d.items;
  const by = k => items.filter(i => i.state === k).length;
  return {
    models: items.length, ingame: by('ingame'), outbox: by('outbox'), stock: by('stock'), archive: by('archive'),
    used: items.filter(i => i.usage === 'used').length, unused: items.filter(i => i.usage === 'unused').length,
    same: items.filter(i => syncOf(i) === 'same').length, missing: items.filter(i => syncOf(i) === 'missing_in_engine').length,
    desktopNewer: items.filter(i => syncOf(i) === 'desktop_newer').length, engineNewer: items.filter(i => syncOf(i) === 'engine_newer').length,
    conflict: items.filter(i => syncOf(i) === 'conflict').length,
    engine: d.engine_only.length, engineUnused: d.engine_only.filter(i => i.usage === 'unused').length,
    placeholders: d.placeholders.length, placeholdersUsed: d.placeholders.filter(p => p.usage === 'used').length,
    tasks: S.tasks.filter(t => t.status !== 'done').length, layout: d.layout_issues.length, unsorted: d.unsorted.length,
    blends: d.blends.length, changes: S.changes.filter(c => c.change !== 'BASELINE').length,
  };
}
/** State chip + usage/sync dots for an entry. */
export const isPlaceholder = i => !i.state && String(i.id || '').startsWith('engine:');
export function chipsFor(i) {
  const out = [i.state ? `<span class="chip ${STATE_CLS[i.state] || 'dim'}">${STATE_LABEL[i.state] || i.state}</span>`
    : isPlaceholder(i) ? `<span class="chip violet">${t('chip.placeholder')}</span>` : ''];
  if (i.imported) out.push(`<span class="chip info" title="${esc(t('chip.fromUnityTitle', { from: i.imported.from, time: i.imported.time }))}">${t('chip.fromUnity')}</span>`);
  if (i.usage) out.push(`<span class="dot ${USAGE[i.usage][0]}" title="${USAGE[i.usage][1]}"></span>`);
  const s = syncOf(i), changed = changedFiles(i);
  const why = changed.length ? ` · ${t('pkg.changedFile', { name: changed.join(', ') })}` : '';
  if (s === 'conflict') out.push(`<span class="chip bad" title="${t('sync.conflict')}${why}">${t('sync.conflict')}</span>`);
  else if (s) out.push(`<span class="dot ${SYNC[s][0]} ${i.basis === 'mtime' ? 'provisional' : ''}" title="${SYNC[s][1]}${i.basis === 'mtime' ? t('chip.provisional') : ''}${why}"></span>`);
  return out.join('');
}
