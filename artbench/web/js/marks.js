// Marks and selection: the star, the "revision coming" flag and tags on rows, tiles and cards (the project's marks.json,
// /api/v1/mark), the Marked view, picking several assets (a box on each row, Shift for a range) with a bar to star,
// flag or export them, and the export of game-project models with their textures into a folder of one's own
// (/api/v1/export_plan, /api/v1/export: one folder per model, nothing overwritten).
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $, $$, esc, toast, modal, emptyState, prefs } from './ui.js';
import { S, KIND, actions, findEntry, isProject } from './state.js';
import { kindIcon, rowVisual } from './catalog.js';
import { archiveFlow } from './archive.js';

export const markOf = id => (S.data?.marks || {})[id] || {};
/** [[tag, assets carrying it]], the most used first. */
export function allTags() {
  const per = {};
  Object.values(S.data?.marks || {}).forEach(m => (m.tags || []).forEach(x => { per[x] = (per[x] || 0) + 1; }));
  return Object.entries(per).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
const tagChip = x => `<span class="mtag">${esc(x)}</span>`;

/** The star, the revision chip and the first tags a row or tile shows (nothing when the asset carries no mark). */
export function markBadges(id) {
  const m = markOf(id), tags = m.tags || [];
  return (m.favorite ? `<span class="mstar" title="${t('marks.favorite')}">${icon('star')}</span>` : '')
    + (m.revision ? `<span class="chip warn nodot mrev" title="${esc(m.revision.note || t('marks.revisionComing'))}">${icon('flag')}${t('marks.revision')}</span>` : '')
    + tags.slice(0, 2).map(tagChip).join('') + (tags.length > 2 ? `<span class="mtag more" title="${esc(tags.slice(2).join(', '))}">+${tags.length - 2}</span>` : '');
}

/** The pick box on a row or tile. */
export const pickBox = id => `<button class="pickbox ${S.picked.has(id) ? 'on' : ''}" data-pickbox="${esc(id)}" title="${t('pick.title')}">${icon('check')}</button>`;

let lastPick = null;
export function bindPicks(el) {
  $$('[data-pickbox]', el).forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    const all = $$('[data-pickbox]', el).map(x => x.dataset.pickbox), id = b.dataset.pickbox, on = !S.picked.has(id);
    if (ev.shiftKey && lastPick && all.includes(lastPick)) {                 // Shift: everything between, like a file list
      const [a, z] = [all.indexOf(lastPick), all.indexOf(id)].sort((x, y) => x - y);
      all.slice(a, z + 1).forEach(x => (on ? S.picked.add(x) : S.picked.delete(x)));
    } else on ? S.picked.add(id) : S.picked.delete(id);
    lastPick = id;
    $$('[data-pickbox]', el).forEach(x => x.classList.toggle('on', S.picked.has(x.dataset.pickbox)));
    renderPickBar();
  });
}

const exportable = () => [...S.picked].filter(id => id.startsWith('engine:') && kindOf(id) === 'model');
function kindOf(id) {
  const a = (S.data?.catalog?.assets || []).find(x => x.id === id);
  return a ? a.kind : findEntry(id)?.kind || (/\.(fbx|obj|glb|gltf|blend)$/i.test(id) ? 'model' : null);
}

/** The bar at the bottom while something is picked. */
export function renderPickBar() {
  let bar = $('#pickbar');
  if (!bar) { bar = document.createElement('div'); bar.id = 'pickbar'; document.body.appendChild(bar); }
  const n = S.picked.size;
  bar.hidden = !n;
  document.body.classList.toggle('picking', n > 0);       // every box shows; the list makes room for the bar
  if (!n) { bar.innerHTML = ''; return; }
  const ids = [...S.picked], allFav = ids.every(id => markOf(id).favorite), models = exportable().length;
  bar.innerHTML = `<b>${t('pick.n', { n })}</b>
    <button class="btn sm" id="pkFav">${icon('star')}${t(allFav ? 'marks.unfavorite' : 'marks.favorite')}</button>
    <button class="btn sm" id="pkRev">${icon('flag')}${t('marks.revisionComing')}</button>
    <button class="btn sm" id="pkTag">${icon('plus')}${t('pick.tag')}</button>
    <button class="btn sm primary" id="pkExport" ${models ? '' : 'disabled'} title="${models ? '' : t('pick.exportOnlyModels')}">${icon('folder')}${t('pick.export', { n: models })}</button>
    ${ids.some(id => id.startsWith('engine:')) ? `<button class="btn sm" id="pkArch" title="${t('arch.pickTitle')}">${icon('trash')}${t('arch.button')}</button>` : ''}
    <div class="grow"></div><button class="btn ghost sm" id="pkClear">${icon('x')}${t('pick.clear')}</button>`;
  $('#pkFav').onclick = () => setMarks(ids, { favorite: !allFav });
  $('#pkRev').onclick = () => askRevision(ids);
  $('#pkTag').onclick = () => askTag(ids);
  const arch = $('#pkArch'); if (arch) arch.onclick = () => archiveFlow(ids);
  $('#pkExport').onclick = () => exportModels(exportable());
  $('#pkClear').onclick = () => { S.picked.clear(); actions.renderView(); };
}

export async function setMarks(ids, payload) {
  try {
    await api.post('/api/v1/mark', { project: S.project, ids, ...payload });
    await actions.refresh();
    actions.renderView(); actions.renderInspector(); renderPickBar();
  } catch (e) { toast(e.message); }
}

async function askRevision(ids, current = '') {
  const note = await modal({ title: t('marks.revisionTitle', { n: ids.length }), body: t('marks.revisionBody'),
    field: { label: t('marks.notePh'), value: current, allowEmpty: true }, ok: t('marks.revisionOk') });
  if (note === null || note === false) return;
  await setMarks(ids, { revision: true, note });
}

async function askTag(ids) {
  const tag = await modal({ title: t('marks.tagTitle', { n: ids.length }), body: t('marks.tagBody'),
    field: { label: t('marks.tagLabel'), value: '' }, ok: t('marks.tagOk') });
  if (!tag) return;
  await setMarks(ids, { tags_add: [tag] });
}

/** The card's own row: star, flag, the revision note, and the tags (a field to add one, a cross to remove one). */
export function markSection(e) {
  const m = markOf(e.id), mine = m.tags || [];
  const known = allTags().map(([x]) => x).filter(x => !mine.includes(x));
  return `<div class="sec marksec"><div class="row">
      <button class="btn sm ${m.favorite ? 'on' : ''}" id="mkFav">${icon('star')}${t(m.favorite ? 'marks.unfavorite' : 'marks.favorite')}</button>
      <button class="btn sm ${m.revision ? 'on' : ''}" id="mkRev">${icon('flag')}${t(m.revision ? 'marks.revisionDone' : 'marks.revisionComing')}</button>
      ${String(e.id || '').startsWith('engine:') && !e.placeholder ? `<div class="grow"></div><button class="btn ghost sm" id="mkArch" title="${t('arch.cardTitle')}">${icon('trash')}${t('arch.button')}</button>` : ''}</div>
    ${m.revision ? `<textarea id="mkNote" rows="2" placeholder="${t('marks.notePh')}">${esc(m.revision.note || '')}</textarea>` : ''}
    <div class="mtags">${mine.map(x => `<span class="mtag">${esc(x)}<button data-untag="${esc(x)}" title="${t('marks.tagRemove')}">${icon('x')}</button></span>`).join('')}
      <input type="text" id="mkTag" list="mkTagList" placeholder="${t('marks.tagPh')}" maxlength="40" spellcheck="false">
      <datalist id="mkTagList">${known.map(x => `<option value="${esc(x)}">`).join('')}</datalist></div></div>`;
}
export function bindMarkSection(el, e) {
  const fav = $('#mkFav', el); if (fav) fav.onclick = () => setMarks([e.id], { favorite: !markOf(e.id).favorite });
  const rev = $('#mkRev', el); if (rev) rev.onclick = () => (markOf(e.id).revision ? setMarks([e.id], { revision: false }) : askRevision([e.id]));
  const note = $('#mkNote', el);
  if (note) note.onchange = () => setMarks([e.id], { revision: true, note: note.value });
  const arch = $('#mkArch', el); if (arch) arch.onclick = () => archiveFlow([e.id]);
  const tag = $('#mkTag', el);
  if (tag) tag.onkeydown = ev => { if (ev.key === 'Enter' && tag.value.trim()) setMarks([e.id], { tags_add: [tag.value] }); };
  $$('[data-untag]', el).forEach(b => b.onclick = () => setMarks([e.id], { tags_remove: [b.dataset.untag] }));
}

/** The Marked view: what waits for a revision (with its note), then the favourites; a tag narrows. */
export function viewMarked() {
  const marks = S.data?.marks || {}, f = S.markFilter || 'all', tags = allTags();
  if (S.markTag && !tags.some(([x]) => x === S.markTag)) S.markTag = null;
  const ids = Object.keys(marks).filter(id => (f === 'all' || marks[id][f]) && (!S.markTag || (marks[id].tags || []).includes(S.markTag)));
  ids.sort((a, b) => (!marks[a].revision - !marks[b].revision) || a.localeCompare(b));
  const seg = ['all', 'revision', 'favorite'].map(k => `<button class="${f === k ? 'on' : ''}" data-mfilter="${k}">${t('marks.filter.' + k)}
    <span class="n">${k === 'all' ? Object.keys(marks).length : Object.values(marks).filter(m => m[k]).length}</span></button>`).join('');
  const tagPills = tags.length ? `<div class="pills mtagpills">${tags.map(([x, n]) => `<span class="pill ${S.markTag === x ? 'on' : ''}" data-mtag="${esc(x)}">${esc(x)}<span class="n">${n}</span></span>`).join('')}</div>` : '';
  return `<div class="row mhead"><div class="seg">${seg}</div>${tagPills}</div>
    ${ids.length ? `<div class="mlist">${ids.map(id => markedRow(id, marks[id])).join('')}</div>` : emptyState('star', t('marks.empty'))}`;
}
function markedRow(id, m) {
  const a = (S.data?.catalog?.assets || []).find(x => x.id === id) || findEntry(id) || { id, name: id.split('/').pop(), kind: kindOf(id) };
  const folder = a.folder || (a.path || id).split('/').slice(0, -1).join('/');
  return `<div class="lrow mrow ${S.selected === id ? 'on' : ''}" data-id="${esc(id)}">${pickBox(id)}${isProject() && a.path ? rowVisual(a) : kindIcon(a.kind || 'other')}
    <div class="ellip"><span class="name">${esc(a.name)}</span> <span class="sub">${esc(folder)}</span>
      ${m.revision ? `<div class="mnote">${icon('flag')}${esc(m.revision.note || t('marks.noNote'))}</div>` : ''}</div>
    <div class="meta">${markBadges(id)}</div><div class="r">${esc(KIND[a.kind]?.label || '')}</div></div>`;
}
export function bindMarked(el) {
  $$('[data-mfilter]', el).forEach(b => b.onclick = () => { S.markFilter = b.dataset.mfilter; actions.renderView(); });
  $$('[data-mtag]', el).forEach(b => b.onclick = () => { S.markTag = S.markTag === b.dataset.mtag ? null : b.dataset.mtag; actions.renderView(); });
}

/** Game-project models with their textures into a folder: choose it, see the plan, copy. */
async function exportModels(ids) {
  if (!ids.length) return;
  let dest = null;
  try { dest = (await api.post('/api/pick_folder', { title: t('export.pickFolder'), initial: prefs.get('exportDest', null) })).path; }
  catch (e) { /* no folder dialog here: ask for the path */ }
  if (!dest) {
    dest = await modal({ title: t('export.pickFolder'), body: t('export.folderBody'), field: { label: t('export.folderLabel'), value: prefs.get('exportDest', '') }, ok: t('ui.ok') });
    if (!dest) return;
  }
  let plan;
  try { plan = (await api.post('/api/v1/export_plan', { project: S.project, ids, dest })).result; }
  catch (e) { toast(e.message); return; }
  prefs.set('exportDest', dest);
  const items = plan.models.map(m => t('export.item', { name: m.name, folder: m.folder.split(/[\\/]/).pop(), n: m.files.length })
    + (m.files.some(f => f.exists) ? t('export.exists', { n: m.files.filter(f => f.exists).length }) : ''));
  const ok = await modal({ title: t('export.title', { n: plan.models.length }), body: t('export.planBody', { files: plan.files, dest: plan.dest }),
    items, ok: t('export.ok', { n: plan.files - plan.exists }) });
  if (!ok) return;
  try {
    const r = (await api.post('/api/v1/export', { project: S.project, ids, dest })).result;
    toast(t('export.done', { copied: r.copied, dest: r.dest }) + (r.skipped ? t('export.skipped', { n: r.skipped }) : ''), 'ok');
    S.picked.clear(); actions.renderView();
  } catch (e) { toast(e.message); }
}
