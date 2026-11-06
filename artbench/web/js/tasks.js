// Tasks: kanban view plus the small task rows the inspector shows, and the archive of finished tasks (off the board,
// kept, restorable). All writes go through /api/tasks.
import { api } from './api.js';
import { icon } from './icons.js';
import { $, $$, esc, fmtDate, fmtDateTime, fmtStamp, toast, modal, emptyState, prefs } from './ui.js';
import { thumbHTML } from './thumbs.js';
import { S, KIND, TASK_NEXT, TASK_NEXT_LABEL, actions, findEntry, isProject } from './state.js';
import { t as tr } from './i18n.js';
import { kindIcon, rowVisual } from './catalog.js';

const COLS = [['todo', 'tasks.col.todo', 'dim'], ['doing', 'tasks.col.doing', 'warn'], ['done', 'tasks.col.done', 'ok']];
export const PRIORITIES = ['high', 'normal', 'low'];
const PRIO_NEXT = { high: 'normal', normal: 'low', low: 'high' };
const prioOf = t => t.priority || 'normal';
const prioMark = t => `<button class="prio ${prioOf(t)}" data-task-prio title="${tr('tasks.prioTitle', { p: tr('tasks.priority.' + prioOf(t)) })}">${tr('tasks.priority.' + prioOf(t))}</button>`;

export const addTask = (title, asset, note, priority = 'normal') => api.post('/api/tasks', { project: S.project, op: 'add', title: title.trim(), asset: asset || null, note: note || '', priority }).catch(e => toast(e.message));
const setPriority = t => api.post('/api/tasks', { project: S.project, op: 'update', id: t.id, priority: PRIO_NEXT[prioOf(t)] }).catch(e => toast(e.message));
export const advanceTask = t => api.post('/api/tasks', { project: S.project, op: 'update', id: t.id, status: TASK_NEXT[t.status] }).catch(e => toast(e.message));
export async function deleteTask(t) {
  const ok = await modal({ title: tr('tasks.deleteTitle'), body: tr('tasks.deleteBody', { title: t.title }), ok: tr('ui.delete'), danger: true });
  if (!ok) return false;
  await api.post('/api/tasks', { project: S.project, op: 'delete', id: t.id }).catch(e => toast(e.message));
  return true;
}
async function after() { if (S.taskArchiveOpen) await loadArchive(); await actions.refresh(); actions.render(); }
const taskOp = body => api.post('/api/tasks', { project: S.project, ...body }).catch(e => toast(e.message));
async function loadArchive() {
  try { S.taskArchive = await api.get('/api/tasks', { project: S.project, archived: 1 }); } catch (e) { toast(e.message); }
}

/** Finished tasks that left the board: shown on demand under it, each with Restore. */
function archiveSection() {
  const list = S.taskArchive || [];
  const rows = list.map(t => `<div class="tarow"><span class="t">${esc(t.title)}</span><span class="dim">${tr('tasks.archivedAt', { date: fmtDate(t.archived) })}</span>
    <button class="btn ghost sm" data-task-restore="${esc(t.id)}">${icon('refresh')}${tr('tasks.restore')}</button></div>`).join('');
  return `<div class="tarchive ${S.taskArchiveOpen ? 'open' : ''}"><button class="tarhead" id="taskArchToggle">${icon('inbox')}<span>${tr('tasks.archived')}</span>
      ${S.taskArchive ? `<span class="n">${list.length}</span>` : ''}${icon('chevron')}</button>
    ${S.taskArchiveOpen ? (list.length ? rows : `<div class="dim tarnone">${tr('tasks.archivedNone')}</div>`) : ''}</div>`;
}

/** Compact task row (inspector). */
export const taskMini = t => `<div class="taskmini ${t.status}" data-task="${t.id}" data-priority="${prioOf(t)}"><span class="dot ${COLS.find(c => c[0] === t.status)?.[2] || 'dim'}"></span>${prioOf(t) !== 'normal' ? prioMark(t) : ''}<span class="t">${esc(t.title)}</span>
  <button class="btn ghost sm" data-task-next>${TASK_NEXT_LABEL[t.status]}</button><button class="btn ghost icon sm" data-task-del title="${tr('ui.delete')}">${icon('trash')}</button></div>`;

export function bindTaskMinis(el) {
  $$('[data-task]', el).forEach(row => {
    const t = S.tasks.find(x => x.id === row.dataset.task); if (!t) return;
    const next = $('[data-task-next]', row), del = $('[data-task-del]', row), chip = $('[data-task-asset]', row), prio = $('[data-task-prio]', row), arch = $('[data-task-arch]', row);
    if (arch) arch.onclick = ev => { ev.stopPropagation(); taskOp({ op: 'archive', id: t.id }).then(() => { S.taskArchive = null; return after(); }); };
    if (next) next.onclick = ev => { ev.stopPropagation(); advanceTask(t).then(after); };
    if (prio) prio.onclick = ev => { ev.stopPropagation(); setPriority(t).then(after); };
    if (del) del.onclick = ev => { ev.stopPropagation(); deleteTask(t).then(d => d && after()); };
    if (chip) chip.onclick = ev => { ev.stopPropagation(); actions.select(t.asset, true); };
  });
}

const CHANGE_WORD = { ADDED: 'change.added', CHANGED: 'change.changed', REMOVED: 'change.removed', MOVED: 'change.moved' };
const richCards = () => prefs.get('taskCards', 'rich') === 'rich';
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

/** What the detailed card says about its asset: a large preview, its name and kind, open in Blender right now, when
 * its file last changed, its revision note (the board's `live`, from /api/tasks). */
function assetBlock(t, a) {
  const live = t.live || {}, name = a?.name || t.asset.split('/').pop();
  const visual = isProject() ? (a ? rowVisual(a) : kindIcon('other')) : thumbHTML(a?.path || a?.engine_path || '', 'sq');
  const lines = [
    live.blender ? `<div class="lv now"><span class="dot ok live"></span>${tr('tasks.liveBlender')}<span class="mono">${esc(live.blender)}</span></div>` : '',
    live.changed ? `<div class="lv">${icon('diff')}${tr('tasks.liveChanged', { what: cap(tr(CHANGE_WORD[live.changed.what] || 'change.changed')), time: fmtStamp(live.changed.time) })}</div>` : '',
    live.revision != null ? `<div class="lv rev">${icon('flag')}${live.revision ? esc(live.revision) : tr('marks.revisionComing')}</div>` : '',
  ].join('');
  return `<div class="tasset" data-task-asset title="${esc(t.asset)}"><div class="tvis">${visual}</div><div class="tinfo">
    <div class="aname"><b>${esc(name)}</b><span>${esc(KIND[a?.kind]?.label || '')}</span></div>${lines}</div></div>`;
}

function card(t) {
  const a = t.asset ? findEntry(t.asset) : null;
  if (richCards() && t.asset) return richCard(t, a);
  const visual = isProject() ? kindIcon(a?.kind || 'other', 'xs') : thumbHTML(a?.path || a?.engine_path || '');
  const chip = t.asset ? `<span class="assetchip" data-task-asset title="${esc(t.asset)}">${visual}<span class="ellip">${esc(a?.name || t.asset.split('/').pop())}</span></span>` : '';
  const when = t.status === 'done' && t.done ? tr('tasks.doneAt', { date: fmtDate(t.done) }) : fmtDate(t.created);
  return `<div class="task ${t.status} prio-${prioOf(t)}" data-task="${t.id}" data-priority="${prioOf(t)}"><div class="thead">${prioMark(t)}<div class="t">${esc(t.title)}</div></div>${t.note ? `<div class="n">${esc(t.note)}</div>` : ''}
    <div class="foot">${chip}<span>${when}</span><button class="btn sm" data-task-next>${TASK_NEXT_LABEL[t.status]}</button>${t.status === 'done' ? `<button class="btn ghost icon sm" data-task-arch title="${tr('tasks.archive')}">${icon('inbox')}</button>` : ''}<button class="btn ghost icon sm" data-task-del title="${tr('ui.delete')}">${icon('trash')}</button></div></div>`;
}

function richCard(t, a) {
  const when = t.status === 'done' && t.done ? tr('tasks.doneAt', { date: fmtDate(t.done) }) : fmtDate(t.created);
  return `<div class="task rich ${t.status} prio-${prioOf(t)} ${t.live?.blender ? 'working' : ''}" data-task="${t.id}" data-priority="${prioOf(t)}"><div class="thead">${prioMark(t)}<div class="t">${esc(t.title)}</div></div>
    ${assetBlock(t, a)}${t.note ? `<div class="n">${esc(t.note)}</div>` : ''}
    <div class="foot"><span>${when}</span><button class="btn sm" data-task-next>${TASK_NEXT_LABEL[t.status]}</button>${t.status === 'done' ? `<button class="btn ghost icon sm" data-task-arch title="${tr('tasks.archive')}">${icon('inbox')}</button>` : ''}<button class="btn ghost icon sm" data-task-del title="${tr('ui.delete')}">${icon('trash')}</button></div></div>`;
}

export function viewTasks() {
  const assets = isProject() ? [] : [...S.data.items].sort((x, y) => x.name.localeCompare(y.name));
  // A game project can hold thousands of assets: a text box that suggests the first matches, not one long list.
  const picker = isProject()
    ? `<input type="text" id="taskAsset" list="taskAssetList" autocomplete="off" placeholder="${tr('tasks.assetSearch')}"><datalist id="taskAssetList"></datalist>`
    : `<select id="taskAsset" style="max-width:220px"><option value="">${tr('tasks.noAsset')}</option>${assets.map(i => `<option value="${esc(i.id)}">${esc(i.name)}</option>`).join('')}</select>`;
  const add = `<div class="card addtask"><input type="text" id="taskTitle" placeholder="${tr('tasks.placeholder')}">
    <select id="taskPrio" title="${tr('tasks.priorityLabel')}">${PRIORITIES.map(p => `<option value="${p}" ${p === 'normal' ? 'selected' : ''}>${tr('tasks.priority.' + p)}</option>`).join('')}</select>
    ${picker}
    <textarea id="taskNote" placeholder="${tr('tasks.notePlaceholder')}"></textarea><button class="btn primary" id="taskAdd">${icon('plus')} ${tr('ui.add')}</button></div>`;
  if (!S.tasks.length) return add + emptyState('checksq', tr('tasks.empty'), tr('tasks.emptySub')) + archiveSection() + fromBlender();
  const cols = COLS.map(([k, label, cls]) => {
    const list = S.tasks.filter(t => t.status === k);             // the server's board order: priority, then oldest
    const archAll = k === 'done' && list.length ? `<button class="btn ghost sm" id="taskArchAll" title="${tr('tasks.archiveAllTitle')}">${icon('inbox')}${tr('tasks.archiveAll')}</button>` : '';
    return `<div class="kcol"><div class="khead"><span class="dot ${cls}"></span><b>${tr(label)}</b>${archAll}<span class="n">${list.length}</span></div>${list.map(card).join('') || `<div class="dim" style="font-size:12px;padding:6px 4px">${tr('tasks.colEmpty')}</div>`}</div>`;
  }).join('');
  const mode = `<div class="row taskmode"><div class="seg"><button class="${richCards() ? 'on' : ''}" data-tcards="rich">${tr('tasks.cardsRich')}</button><button class="${richCards() ? '' : 'on'}" data-tcards="plain">${tr('tasks.cardsPlain')}</button></div></div>`;
  return add + mode + `<div class="kanban">${cols}</div>` + archiveSection() + fromBlender();
}

/** Notes artists wrote in Blender: they live in each .blend and come here as a copy when the add-on sends them, so
 * they are shown apart from the board and cannot be changed here. One card per file, its last send. */
function fromBlender() {
  if (!S.blenderNotes?.length) return '';
  const note = n => `<li class="fbnote prio-${esc(n.priority)}${n.kind === 'todo' && n.done ? ' done' : ''}" data-kind="${esc(n.kind)}" data-done="${!!n.done}" data-priority="${esc(n.priority)}">
    <span class="box ${esc(n.kind)}">${n.kind === 'todo' && n.done ? icon('check') : ''}</span><span class="t">${esc(n.text)}</span>${n.object ? `<span class="obj">${icon('cube')}${esc(n.object)}</span>` : ''}</li>`;
  const file = f => {
    const open = f.notes.filter(n => !(n.kind === 'todo' && n.done)).length;
    return `<div class="fbfile"><div class="fbtitle" title="${esc(f.file || f.asset)}">${icon('blender')}<b>${esc(f.name)}</b><span class="dim ellip">${esc(f.asset)}</span>
      <span class="n">${tr('tasks.openCount', { n: open })}</span></div><ul>${f.notes.map(note).join('')}</ul><div class="fbfoot">${tr('tasks.sentAt', { date: fmtDateTime(f.sent) })}</div></div>`;
  };
  return `<section class="fromblender"><div class="fbhead">${icon('blender')}<h3>${tr('tasks.fromBlender')}</h3><span class="dim">${tr('tasks.fromBlenderSub')}</span></div>
    <div class="fbgrid">${S.blenderNotes.map(file).join('')}</div></section>`;
}

export function bindTasks(el) {
  if (S.view !== 'tasks') return;
  const title = $('#taskTitle', el), picker = $('#taskAsset', el), add = async () => {
    if (!title.value.trim()) { title.focus(); return; }
    const asset = isProject() ? pickedAsset(picker.value) : picker.value;
    if (asset === undefined) { toast(tr('tasks.assetPick')); picker.focus(); return; }
    await addTask(title.value, asset, $('#taskNote', el).value, $('#taskPrio', el).value);
    await after(); toast(tr('tasks.added'), 'ok'); $('#taskTitle')?.focus();
  };
  $('#taskAdd', el).onclick = add; title.onkeydown = ev => { if (ev.key === 'Enter') add(); };
  $$('[data-tcards]', el).forEach(b => b.onclick = () => { prefs.set('taskCards', b.dataset.tcards); actions.renderView(); });
  const archAll = $('#taskArchAll', el);
  if (archAll) archAll.onclick = () => taskOp({ op: 'archive_done' }).then(r => { if (r) toast(tr('tasks.archivedN', { n: r.archived }), 'ok'); S.taskArchive = null; return after(); });
  $('#taskArchToggle', el).onclick = async () => { S.taskArchiveOpen = !S.taskArchiveOpen; if (S.taskArchiveOpen) await loadArchive(); actions.renderView(); };
  $$('[data-task-restore]', el).forEach(b => b.onclick = () => taskOp({ op: 'restore', id: b.dataset.taskRestore }).then(after));
  if (isProject()) picker.oninput = () => { $('#taskAssetList', el).innerHTML = suggestions(picker.value).map(a => `<option value="${esc(a.id)}" label="${esc(a.folder)}"></option>`).join(''); };
  bindTaskMinis(el);
}

const SUGGESTIONS = 30;
function suggestions(text) {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  return (S.data.catalog?.assets || []).filter(a => words.every(w => a.id.toLowerCase().includes(w))).slice(0, SUGGESTIONS);
}
/** The catalog id a typed value names: '' for none, the id itself, or the one asset of that name; undefined otherwise. */
function pickedAsset(value) {
  const v = value.trim(), all = S.data.catalog?.assets || [];
  if (!v) return '';
  if (all.some(a => a.id === v)) return v;
  const named = all.filter(a => a.name.toLowerCase() === v.toLowerCase());
  return named.length === 1 ? named[0].id : undefined;
}
