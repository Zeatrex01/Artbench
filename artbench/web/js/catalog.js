// Project mode (the game project on its own): the art catalog grouped by kind or folder, the unused view and the asset
// card. The polled state has light rows (used_by_count, uses_count); the card asks /api/v1/asset for the lists.
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $, $$, esc, fmtCount, fmtSize, prefs, emptyState, callout, toast } from './ui.js';
import { S, KIND, actions, enginePathAbs } from './state.js';
import { groupHead } from './library.js';
import { thumbHTML } from './thumbs.js';
import { markBadges, markOf, markSection, pickBox } from './marks.js';

export const KIND_ORDER = ['model', 'prefab', 'material', 'texture', 'scene', 'mesh', 'animator', 'clip', 'shader', 'audio', 'font', 'atlas'];
export const USAGE_CLS = { used: 'ok', unreferenced: 'warn', by_name: 'info', unknown: 'dim' };
const USAGE_ORDER = ['used', 'unreferenced', 'by_name', 'unknown'];

export const catalogAssets = () => S.data?.catalog?.assets || [];
const relOf = path => path.replace(/^Assets\//, '');
/** Absolute path of a project path: Assets/... under the Assets folder, anything else (ProjectSettings/...) beside it. */
const projectPathAbs = path => (path.startsWith('Assets/') ? enginePathAbs(relOf(path))
  : S.assetsRoot ? S.assetsRoot.replace(/\/Assets$/, '') + '/' + path : path);
const inFolder = (a, folder) => a.folder === folder || a.folder.startsWith(folder + '/');

/** Counts the catalog views and the sidebar show. */
export function pcounts() {
  const all = catalogAssets(), by = u => all.filter(a => a.usage === u).length;
  const open = S.tasks.filter(x => x.status !== 'done');
  return { total: all.length, kinds: S.data?.catalog?.counts?.kinds || {}, used: by('used'), unreferenced: by('unreferenced'),
    byName: by('by_name'), unknown: by('unknown'), changes: S.sinceSeen.length, tasks: open.length,
    high: open.filter(x => x.priority === 'high').length, placeholders: S.data?.placeholders?.length || 0 };
}

export function filteredAssets() {
  const f = S.catFilters, words = (S.search || '').toLowerCase().split(/\s+/).filter(Boolean);
  return catalogAssets().filter(a => (!f.kind || a.kind === f.kind) && (!f.usage || a.usage === f.usage) && (!f.mark || markOf(a.id)[f.mark])
    && (!f.folder || inFolder(a, f.folder)) && words.every(w => (a.name + ' ' + a.path).toLowerCase().includes(w)));
}

export const kindIcon = (kind, cls = '') => `<span class="kicon ${cls}" style="--c:${KIND[kind]?.color || KIND.other.color}">${icon(KIND[kind]?.icon || 'box')}</span>`;
/** Models show their Blender render, textures the image itself; other kinds keep their icon. */
const PREVIEW_KINDS = new Set(['model', 'texture']);
const hasPreview = a => PREVIEW_KINDS.has(a.kind) && a.path?.startsWith('Assets/');
const preview = (a, cls) => thumbHTML(enginePathAbs(relOf(a.path)), `${cls} ${a.kind === 'texture' ? 'tex' : ''}`);
export const rowVisual = a => (hasPreview(a) ? preview(a, 'sq') : kindIcon(a.kind));
/** Model statistics: "1,234 tris" for a row, the full line for the card; "measuring…" while Blender reads it. */
const plural = (key, n) => t(n === 1 ? key + '1' : key, { n: fmtCount(n) });
const imageSize = i => `${i.width} × ${i.height}`;
const rowStats = a => (a.kind === 'texture' ? (a.image ? imageSize(a.image) : '')
  : a.kind !== 'model' || a.stats === undefined ? '' : a.stats ? t('stats.tris', { n: fmtCount(a.stats.tris) }) : t('stats.measuring'));
function cardStats(e) {
  if (e.kind === 'texture') return e.image ? `<div class="mstats"><span>${imageSize(e.image)} · ${esc(e.image.format)}</span></div>` : '';
  if (e.kind !== 'model' || e.stats === undefined) return '';
  if (!e.stats) return `<div class="mstats dim">${t('stats.measuring')}</div>`;
  const s = e.stats, parts = [plural('stats.triangles', s.tris), plural('stats.vertices', s.verts), plural('stats.objects', s.objects),
    plural('stats.materials', s.materials), plural('stats.textures', s.textures)];
  if (s.bones) parts.push(plural('stats.bones', s.bones));
  if (s.animations) parts.push(plural('stats.animations', s.animations));
  return `<div class="mstats">${parts.map(p => `<span>${p}</span>`).join('')}</div>`;
}
export const usageChip = a => `<span class="chip ${USAGE_CLS[a.usage] || 'dim'}">${t('usage.' + a.usage)}</span>`;

export function catRow(a) {
  const open = S.tasks.filter(x => x.asset === a.id && x.status !== 'done').length;
  return `<div class="catrow lrow ${S.selected === a.id ? 'on' : ''}" data-id="${esc(a.id)}">${pickBox(a.id)}${rowVisual(a)}
    <div class="ellip"><span class="name">${esc(a.name)}</span> <span class="sub">${esc(a.folder)}</span></div>
    <div class="meta">${markBadges(a.id)}${usageChip(a)}${a.in_build === true ? `<span class="chip accent nodot">${t('ins.inBuild')}</span>` : ''}${open ? `<span class="chip accent nodot">${open === 1 ? t('lib.openTask') : t('lib.openTasks', { n: open })}</span>` : ''}</div>
    <div class="r">${a.used_by_count ? t('cat.usedByN', { n: a.used_by_count }) : ''}</div><div class="r">${rowStats(a)}</div><div class="r">${a.size != null ? fmtSize(a.size) : ''}</div></div>`;
}

function stat(v, label, color, sub, target) {
  const on = target && ((target[0] === 'usage' && S.catFilters.usage === target[1]));
  return `<div class="stat ${on ? 'on' : ''} ${target ? '' : 'static'}" style="--c:${color}" data-cstat="${target ? target.join(':') : ''}"><div class="v">${v}</div><div class="l">${label}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
}

function warnings() {
  if (S.data.engine_unreachable) return callout('warn', t('lib.engineUnreachable', { root: esc(S.data.engine_root) }));
  if (S.data.catalog?.force_text === false) return callout('warn', t('cat.forceTextOff'));
  return '';
}

/** The folders hidden from the catalog (their references still count), each with a button to show it again. */
function hiddenLine() {
  const hidden = (S.data.hidden_folders || []).filter(f => f.includes('/'));   // the folders the person hid, not the default third-party names
  if (!hidden.length) return '';
  return `<div class="hiddenline">${icon('eyeoff')}<span class="lbl">${t('cat.hiddenFolders')}</span>${hidden.map(f => `<span class="hf"><span class="mono">${esc(f)}</span><button class="btn ghost sm" data-cshow="${esc(f)}" title="${t('cat.showTitle')}">${t('cat.show')}</button></span>`).join('')}</div>`;
}

async function setHidden(folder, hidden) {
  try {
    await api.post('/api/projects/hide_folder', { project: S.project, folder, hidden });
    if (hidden && S.catFilters.folder && (S.catFilters.folder === folder || S.catFilters.folder.startsWith(folder + '/'))) S.catFilters.folder = null;
    document.activeElement?.blur();          // the refresh redraws only while nothing in the view has focus
    await actions.refresh();
    actions.render();
  } catch (e) { toast(e.message); }
}

/** Rows within a group: by name, or largest, most triangles, most recently changed first (unknown values last). */
const SORTS = ['name', 'size', 'tris', 'changed'];
const sortKey = { size: a => a.size ?? -1, tris: a => a.stats?.tris ?? -1, changed: a => a.mtime ?? -1 };
function sorted(rows) {
  const key = sortKey[S.catSort];
  const byName = (x, y) => x.path.toLowerCase().localeCompare(y.path.toLowerCase());
  return rows.slice().sort(key ? (x, y) => key(y) - key(x) || byName(x, y) : byName);
}

export function viewCatalog() {
  const c = pcounts(), kinds = Object.keys(c.kinds).length;
  const stats = warnings() + `<div class="stats">
    ${stat(c.total, t('cat.stat.assets'), 'var(--accent)', t('cat.stat.assetsSub', { n: kinds }), null)}
    ${stat(c.used, t('cat.stat.used'), 'var(--ok)', '', ['usage', 'used'])}
    ${stat(c.unreferenced, t('cat.stat.unreferenced'), 'var(--warn)', t('cat.stat.unreferencedSub'), ['usage', 'unreferenced'])}
    ${stat(c.byName, t('cat.stat.byName'), 'var(--info)', t('cat.stat.byNameSub'), ['usage', 'by_name'])}
    ${c.unknown ? stat(c.unknown, t('cat.stat.unknown'), 'var(--dim)', '', ['usage', 'unknown']) : ''}
    ${stat(c.changes, t('cat.stat.changes'), 'var(--violet)', t('cat.stat.changesSub'), ['view', 'changes'])}
    ${stat(c.tasks, t('cat.stat.tasks'), 'var(--accent2)', c.high ? t('cat.stat.tasksSub', { n: c.high }) : '', ['view', 'tasks'])}
  </div>`;
  const head = stats + hiddenLine() + toolbar();
  const list = filteredAssets();
  if (!list.length) return head + emptyState('search', t('cat.empty'), t('cat.emptySub'));
  const byFolder = S.catGroup === 'folder', groups = {};
  for (const a of list) (groups[byFolder ? a.folder : a.kind] ||= []).push(a);
  const rank = k => KIND_ORDER.indexOf(k) + 99 * (KIND_ORDER.indexOf(k) < 0);
  const order = Object.keys(groups).sort(byFolder ? (x, y) => x.localeCompare(y) : (x, y) => rank(x) - rank(y));
  return head + order.map(k => {
    const key = (byFolder ? 'catf|' : 'cat|') + k, rows = groups[k], closed = S.closedGroups[key] ?? false;
    const used = rows.filter(a => a.usage === 'used').length, un = rows.filter(a => a.usage === 'unreferenced').length;
    const title = byFolder ? k : t('kinds.' + k), mark = byFolder ? `<span class="kicon sm" style="--c:var(--dim)">${icon('folder')}</span>` : kindIcon(k, 'sm');
    const hide = byFolder ? `<button class="btn ghost sm hidebtn" data-chide="${esc(k)}" title="${t('cat.hideTitle')}">${icon('eyeoff')}${t('cat.hide')}</button>` : '';
    const extra = `${mark}${hide}<span class="dots">${used ? `<span class="dot ok" title="${t('lib.used', { n: used })}"></span>` : ''}${un ? `<span class="dot warn" title="${t('cat.unreferencedN', { n: un })}"></span>` : ''}</span>`;
    return `<div class="group ${closed ? 'closed' : ''}" data-group="${esc(key)}">${groupHead(esc(title), '', rows.length, extra)}<div class="list">${sorted(rows).map(catRow).join('')}</div></div>`;
  }).join('');
}

/** Group by kind or folder, and narrow to one folder (with everything under it). */
function toolbar() {
  const all = catalogAssets(), folders = [...new Set(all.map(a => a.folder))].sort((x, y) => x.localeCompare(y));
  const f = S.catFilters.folder, n = folder => all.filter(a => inFolder(a, folder)).length;
  return `<div class="cattools"><div class="seg">
      <button class="${S.catGroup !== 'folder' ? 'on' : ''}" data-cgroup="kind">${icon('layers')}${t('cat.byKind')}</button>
      <button class="${S.catGroup === 'folder' ? 'on' : ''}" data-cgroup="folder">${icon('folder')}${t('cat.byFolder')}</button></div>
    <select id="catFolder" title="${t('cat.allFolders')}"><option value="">${t('cat.allFolders')}</option>${folders.map(x => `<option value="${esc(x)}" ${x === f ? 'selected' : ''}>${esc(x)} (${n(x)})</option>`).join('')}</select>
    <select id="catSort" title="${t('cat.sortTitle')}">${SORTS.map(k => `<option value="${k}" ${S.catSort === k ? 'selected' : ''}>${t('cat.sort.' + k)}</option>`).join('')}</select></div>`;
}

export function viewUnused() {
  const head = callout('info', t('cat.unusedHead'));
  const words = (S.search || '').toLowerCase().split(/\s+/).filter(Boolean);
  const pick = u => catalogAssets().filter(a => a.usage === u && words.every(w => (a.name + ' ' + a.path).toLowerCase().includes(w)));
  const un = pick('unreferenced'), byName = pick('by_name');
  if (!un.length && !byName.length) return warnings() + head + emptyState('check', t('cat.unusedEmpty'));
  const section = (title, rows, cls) => rows.length ? `<div class="group"><div class="ghead"><h3>${title}</h3><span class="cnt">${rows.length}</span><span class="chip ${cls} nodot">${t(cls === 'warn' ? 'usage.unreferenced' : 'usage.by_name')}</span><div class="line"></div></div><div class="list">${rows.map(catRow).join('')}</div></div>` : '';
  return warnings() + head + section(t('cat.unreferencedTitle'), un, 'warn') + section(t('cat.byNameTitle'), byName, 'info');
}

/** Sidebar list of kinds with counts; a click filters the catalog. */
export function kindNav() {
  const c = pcounts(), f = S.catFilters;
  const kinds = Object.keys(c.kinds).sort((x, y) => KIND_ORDER.indexOf(x) - KIND_ORDER.indexOf(y));
  return `<div class="side-section"><div class="label">${t('cat.kinds')}</div></div><div class="tree kindnav">
    <div class="node ${!f.kind ? 'on' : ''}" data-kind="">${icon('layers')}<span class="lbl">${t('cat.allKinds')}</span><span class="cnt">${c.total}</span></div>
    ${kinds.map(k => `<div class="node ${f.kind === k ? 'on' : ''}" data-kind="${esc(k)}">${kindIcon(k, 'xs')}<span class="lbl">${t('kinds.' + k)}</span><span class="cnt">${c.kinds[k]}</span></div>`).join('')}</div>
    <div class="side-section"><div class="label">${t('side.filters')}</div></div>
    <div class="pills">${USAGE_ORDER.map(u => [u, catalogAssets().filter(a => a.usage === u).length]).filter(([u, n]) => n || f.usage === u)
      .map(([u, n]) => `<span class="pill ${f.usage === u ? 'on' : ''}" data-cusage="${u}">${t('usage.' + u)}<span class="n">${n}</span></span>`).join('')}</div>
    <div class="pills">${['favorite', 'revision'].map(m => [m, catalogAssets().filter(a => markOf(a.id)[m]).length]).filter(([m, n]) => n || f.mark === m)
      .map(([m, n]) => `<span class="pill ${f.mark === m ? 'on' : ''}" data-cmark="${m}">${t('marks.filter.' + m)}<span class="n">${n}</span></span>`).join('')}</div>`;
}

export function bindKindNav(el) {
  $$('.kindnav .node', el).forEach(n => n.onclick = () => { S.catFilters.kind = n.dataset.kind || null; if (S.view !== 'catalog') actions.setView('catalog'); else actions.render(); });
  $$('[data-cusage]', el).forEach(p => p.onclick = () => { const u = p.dataset.cusage; S.catFilters.usage = S.catFilters.usage === u ? null : u; actions.render(); });
  $$('[data-cmark]', el).forEach(p => p.onclick = () => { const m = p.dataset.cmark; S.catFilters.mark = S.catFilters.mark === m ? null : m; if (S.view !== 'catalog') actions.setView('catalog'); else actions.render(); });
}

export function bindCatalog(el) {
  $$('[data-cstat]', el).forEach(n => n.onclick = () => {
    const [k, v] = n.dataset.cstat.split(':'); if (!k) return;
    if (k === 'view') { actions.setView(v); return; }
    S.catFilters.usage = S.catFilters.usage === v ? null : v; actions.render();
  });
  const sortSel = $('#catSort', el);
  if (sortSel) sortSel.onchange = () => { S.catSort = sortSel.value; prefs.set('catSort', S.catSort); sortSel.blur(); actions.render(); };
  $$('[data-chide]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); setHidden(b.dataset.chide, true); });
  $$('[data-cshow]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); setHidden(b.dataset.cshow, false); });
  $$('[data-cgroup]', el).forEach(b => b.onclick = () => { S.catGroup = b.dataset.cgroup; prefs.set('catGroup', S.catGroup); actions.render(); });
  const folder = $('#catFolder', el); if (folder) folder.onchange = () => { S.catFilters.folder = folder.value || null; actions.render(); };
}

function refs(rows, total, none, failed = false) {
  if (failed) return `<div class="muted" style="font-size:12px">${t('cat.detailFailed')}</div>`;
  if (rows == null) return `<div class="muted" style="font-size:12px">${t('cat.loading')}</div>`;
  const more = total > rows.length ? `<div class="muted" style="font-size:12px">${t('cat.andMore', { n: total - rows.length })}</div>` : '';
  if (!rows.length) return `<div class="muted" style="font-size:12px">${none}</div>`;
  const known = new Set(catalogAssets().map(a => a.path));
  return rows.map(r => {
    const id = known.has(r.path) ? 'engine:' + relOf(r.path) : null;
    const folder = r.path.split('/').slice(0, -1).join('/');
    return `<div class="refrow pref ${id ? 'link' : ''}" ${id ? `data-sel="${esc(id)}"` : ''} title="${esc(r.path)}">${kindIcon(r.kind, 'sm')}<span class="refname ellip"><b>${esc(r.name)}</b><span class="mono">${esc(folder)}</span></span>
      <button class="btn ghost icon sm" data-reveal="${esc(projectPathAbs(r.path))}" title="${t('ui.reveal')}">${icon('folder')}</button></div>`;
  }).join('') + more;
}

// The full entry of the selected catalog asset (its used_by and uses lists), fetched once per scan of the project.
let detail = { key: null, entry: null };
function detailOf(e) {
  const key = S.project + '|' + e.id + '|' + (S.hashes.data || '');
  if (detail.key === key) return detail.entry;
  detail = { key, entry: null };
  api.get('/api/v1/asset', { project: S.project, id: e.id }).then(r => r.result, () => ({ failed: true }))
    .then(entry => { if (detail.key !== key) return; detail.entry = entry; if (S.selected === e.id) actions.renderInspector(); });
  return null;
}

/** The inspector for a catalog asset: what it is, how sure we are it is used, what uses it, what it uses, tasks. */
export function assetCard(e, { pathRow, taskMini }) {
  const myTasks = S.tasks.filter(x => x.asset === e.id);
  const isCatalog = !!e.kind, full = isCatalog ? detailOf(e) : e;
  const sub = [e.folder, e.size != null ? fmtSize(e.size) : null].filter(Boolean).join(' · ');
  const usedBy = full ? full.used_by || [] : null, uses = full ? full.uses || [] : null;
  const usedByN = isCatalog ? e.used_by_count : (e.used_by || []).length;
  const failed = !!full?.failed;
  return `<div class="ins" data-detail="${failed ? 'failed' : full ? 'ready' : 'loading'}">
    <div class="top"><span class="label">${isCatalog ? (KIND[e.kind]?.label || e.kind) : t('ins.kind.placeholder')}</span><button class="btn ghost icon sm" id="insClose" title="${t('ui.closeEsc')}">${icon('x')}</button></div>
    ${isCatalog && hasPreview(e) ? preview(e, 'hero') : ''}
    <div class="assethead">${kindIcon(e.kind || 'mesh', 'lg')}<div class="ellip"><h2>${esc(e.name)}</h2><div class="sub">${esc(sub)}</div></div></div>
    ${isCatalog ? cardStats(e) : ''}
    <div class="chips">${e.usage ? `<span class="chip ${USAGE_CLS[e.usage] || 'dim'}">${t('usage.' + e.usage)}</span>` : ''}${e.in_build === true ? `<span class="chip accent nodot">${t('ins.inBuild')}</span>` : e.in_build === false ? `<span class="chip dim nodot">${t('ins.notInBuild')}</span>` : ''}</div>
    ${e.usage ? callout(USAGE_CLS[e.usage] === 'dim' ? 'info' : USAGE_CLS[e.usage], t('usage.explain.' + e.usage)) : ''}
    ${markSection(e)}
    ${e.path ? pathRow(t('ins.unity'), e.path) : e.engine_path ? pathRow(t('ins.unity'), e.engine_path) : ''}
    <div class="sec"><span class="label">${t('ins.usedBy')} <span class="n">${usedByN}</span></span>${refs(usedBy, usedByN, t('ins.usedByNone'), failed)}</div>
    ${isCatalog ? `<div class="sec"><span class="label">${t('ins.uses')} <span class="n">${e.uses_count}</span></span>${refs(uses, e.uses_count, t('ins.usesNone'), failed)}</div>` : ''}
    <div class="sec"><span class="label">${t('ins.tasks')} <span class="n">${myTasks.length}</span></span>${myTasks.map(taskMini).join('')}
      <div class="row"><input type="text" id="insTask" placeholder="${t('tasks.forAsset')}" style="flex:1"><button class="btn icon" id="insTaskAdd" title="${t('ui.add')}">${icon('plus')}</button></div></div>
    <div class="actions">${e.kind === 'model' ? `<button class="btn" data-openblender="${esc(e.id)}">${icon('cube')}${t('ins.openBlender')}</button>` : ''}<button class="btn" data-reveal="${esc(enginePathAbs(relOf(e.path || '')))}">${icon('folder')}${t('ui.reveal')}</button></div>
  </div>`;
}

export async function openInBlender(id) {
  try {
    await api.post('/api/v1/open_in_blender', { project: S.project, id });
    toast(t('ins.openingBlender'), 'ok');
  } catch (e) { toast(e.message); }
}

export function bindAssetCard(el) {
  $$('[data-openblender]', el).forEach(b => b.onclick = () => openInBlender(b.dataset.openblender));
  $$('[data-sel]', el).forEach(r => r.onclick = ev => { if (ev.target.closest('button')) return; actions.select(r.dataset.sel, true); });
}
