// Inspector: detail panel for the selected entry (desktop model, engine-only model or placeholder mesh).
// Mutations go through the API, then `commit()` refreshes the state and re-renders.
import { api } from './api.js';
import { icon } from './icons.js';
import { t, locale } from './i18n.js';
import { $, $$, esc, base, fmtDate, fmtDateTime, fmtStamp, fmtSize, toast, modal, callout } from './ui.js';
import { thumbHTML, observeThumbs } from './thumbs.js';
import { S, KIND, STATE_LABEL, SYNC, actions, findEntry, setOf, setLabel, chipsFor, enginePathAbs, relToAssets, isPlaceholder, engineUnreachable, syncOf, changedFiles, isProject } from './state.js';
import { taskMini, bindTaskMinis, addTask } from './tasks.js';
import { assetCard, bindAssetCard } from './catalog.js';
import { bindMarkSection, markSection } from './marks.js';


/** Refresh after a write; render explicitly because the refresh skips rendering while focus sits in the inspector. */
export async function commit(message) {
  await actions.refresh();
  actions.render();
  if (message) toast(message, 'ok');
}
export const reveal = path => api.post('/api/reveal', { project: S.project, path }).catch(e => toast(e.message));
export const openFile = path => api.post('/api/open', { project: S.project, path }).catch(e => toast(e.message));
export function showInGraph(enginePath) {
  if (!enginePath) return;
  S.graphFocus = relToAssets(enginePath);
  actions.setView('graph');
}

export function renderInspector() {
  const el = $('#inspector'), e = findEntry(S.selected);
  document.getElementById('app').classList.toggle('has-inspector', !!e);
  el.hidden = !e;
  if (!e) { el.innerHTML = ''; return; }
  if (isProject()) { el.innerHTML = assetCard(e, { pathRow, taskMini }); observeThumbs(el); bindProjectCard(el, e); return; }
  const desktop = !!e.path, placeholder = isPlaceholder(e);
  const kindLabel = placeholder ? t('ins.kind.placeholder') : desktop ? t('ins.kind.model') : t('ins.kind.engine');
  const myTasks = S.tasks.filter(t => t.asset === e.id);
  // Buttons follow the whole package: a model that is the same with a changed texture can still be sent.
  const pkgFiles = e.package?.files || [];
  const canSend = desktop && (e.state === 'outbox' || pkgFiles.some(f => ['desktop_newer', 'missing_in_engine', 'conflict'].includes(f.sync)));
  const canPull = desktop && !!e.engine_path && pkgFiles.some(f => f.engine_path && ['engine_newer', 'conflict'].includes(f.sync));
  const sub = [e.category, desktop ? setLabel(setOf(e)) : null, desktop ? fmtSize(e.size) : null, desktop ? fmtDate(e.mtime) : null].filter(Boolean).join(' · ');

  el.innerHTML = `<div class="ins">
    <div class="top"><span class="label">${kindLabel}</span><button class="btn ghost icon sm" id="insClose" title="${t('ui.closeEsc')}">${icon('x')}</button></div>
    ${placeholder ? '' : thumbHTML(desktop ? e.path : e.engine_path, 'hero')}
    <div><h2>${esc(e.name)}</h2><div class="sub">${esc(sub)}</div><div class="chips">${chipsFor(e)}</div></div>
    ${desktop ? pathRow(t('ins.desktop'), e.path) : ''}
    ${e.engine_path ? pathRow(t('ins.unity'), e.engine_path) : ''}
    ${markSection(e)}
    ${e.imported ? `<div class="muted imported" style="font-size:12px">${icon('inbox')} ${esc(t('ins.imported', { time: e.imported.time, from: e.imported.from }))}</div>` : ''}
    ${!desktop && !placeholder ? `<div class="sec bringin">${callout('info', t('bring.hint'))}<button class="btn primary" id="insBringIn">${icon('inbox')}${t('bring.button')}</button></div>` : ''}
    ${e.ambiguous ? `<div class="sec"><span class="label">${t('ins.ambiguous')}</span><select id="insAmbig"><option value="" selected>${t('pkg.pickOne')}</option>${e.ambiguous.map(p => `<option value="${esc(p)}">${esc(relToAssets(p))}</option>`).join('')}</select></div>` : ''}
    ${desktop && engineUnreachable() && ['ingame', 'outbox'].includes(e.state) ? callout('warn', t('ins.engineUnreachable', { root: esc(S.data.engine_root) })) : desktop && e.sync ? syncBlock(e, canSend, canPull) : ''}
    ${desktop && !e.sync && !(engineUnreachable() && ['ingame', 'outbox'].includes(e.state)) ? callout('info', e.state === 'stock' ? t('ins.stock') : e.state === 'archive' ? t('ins.archive') : t('ins.noCompare')) : ''}
    ${placeholder ? callout('info', t('ins.placeholderNote'), 'cube') : ''}
    ${desktop ? `<div class="sec" id="insMeta"><span class="label">${t('ins.changes')}</span>${metaCache.get(e.id) || `<div class="muted" style="font-size:12px">${t('ins.blenderBusy')}</div>`}</div>` : ''}
    ${desktop ? `<div class="sec"><span class="label">${t('ins.location')} <span class="muted" style="text-transform:none;letter-spacing:0;font-weight:500">${t('ins.inArtFolder')}</span></span><div class="statebar">${S.data.states.map(s => `<button class="${s === e.state ? 'on' : ''}" data-state="${s}" title="${t('ins.moveTo', { state: STATE_LABEL[s] || s })}">${STATE_LABEL[s] || s}</button>`).join('')}</div></div>` : ''}
    <div class="sec"><span class="label">${t('ins.usedBy')} <span class="n">${e.used_by?.length || 0}</span></span>${usedBy(e)}</div>
    ${desktop && e.textures?.length ? `<div class="sec"><span class="label">${t('ins.textures')} <span class="n">${e.textures.length}</span></span>${e.textures.map(t => `<div class="texrow">${icon('image')}<span class="ellip">${esc(t)}</span></div>`).join('')}</div>` : ''}
    ${desktop ? blendSection(e) : ''}
    <div class="sec"><span class="label">${t('ins.tasks')} <span class="n">${myTasks.length}</span></span>${myTasks.map(taskMini).join('')}
      <div class="row"><input type="text" id="insTask" placeholder="${t('tasks.forModel')}" style="flex:1"><button class="btn icon" id="insTaskAdd" title="${t('ui.add')}">${icon('plus')}</button></div></div>
    <div class="sec"><span class="label">${t('ins.note')}</span><textarea class="note" id="insNote" placeholder="${t('ins.notePlaceholder')}">${esc(e.note || '')}</textarea></div>
    <div class="actions">
      ${desktop ? `<button class="btn" data-reveal="${esc(e.path)}">${icon('folder')}${t('ui.reveal')}</button>` : ''}
      ${e.engine_path ? `<button class="btn" data-reveal="${esc(e.engine_path)}">${icon('external')}${t('ui.showInEngine')}</button>` : ''}
      ${e.engine_path ? `<button class="btn" id="insGraph">${icon('share')}${t('ui.showInGraph')}</button>` : ''}
    </div>
  </div>`;
  observeThumbs(el);
  bind(el, e);
  if (desktop && !metaCache.has(e.id) && !metaInflight.has(e.id)) loadMeta(e, 0);
}

/** An engine-only model into the art folder, with the textures it uses when asked (ticked by default), marked as
 * brought in from Unity; the new card opens. */
async function bringIn(e) {
  let plan;
  try { plan = (await api.get('/api/v1/bring_in_plan', { project: S.project, id: e.id })).result; }
  catch (err) { toast(friendlyError(err.message)); return; }
  const stem = e.name.replace(/\.[^.]+$/, '');
  const tex = plan.textures || [];
  const answer = await modal({ title: t('bring.title', { name: e.name }), body: t('bring.body', { path: `FBX/<${t('bring.category')}>/${stem}/${e.name}` }),
    checks: tex.length ? [{ id: 'textures', label: t('bring.textures', { n: tex.length }), note: tex.map(x => x.source.split(/[\\/]/).pop()).join(', '), checked: true }] : null,
    field: { label: t('bring.category'), value: plan.category || '', options: plan.categories }, ok: t('bring.ok') });
  const category = typeof answer === 'object' && answer ? answer.field : answer;
  if (!category) return;
  const textures = !!(answer && answer.checks && answer.checks.includes('textures'));
  try {
    const r = (await api.post('/api/v1/bring_in', { project: S.project, id: e.id, category, textures })).result;
    toast(t('bring.done', { path: r.id }), 'ok');
    await actions.refresh();
    actions.select(r.id);
  } catch (err) { toast(friendlyError(err.message)); }
}

/** Server messages the artist may meet, in plain Turkish; anything else passes through. */
function friendlyError(msg) {
  if (/no engine target/.test(msg)) return t('err.noTarget');
  if (/changed since the last sync|no sync record|changed since the plan/.test(msg)) return t('err.raced');
  if (/project is busy/.test(msg)) return t('err.busy');
  if (/outside (engine|art) root/.test(msg)) return t('err.outside');
  return msg;
}

/** "Etkilenen: 3 prefab/sahne/materyal: PF_Crate.prefab, Main.unity, …" or the no-reference sentence. */
function affectedLine(e) {
  const refs = e.used_by || [];
  if (refs.length) return t('affected.some', { n: refs.length, names: refs.slice(0, 3).map(r => r.name).join(', ') + (refs.length > 3 ? ', …' : '') });
  if (!e.engine_path) return t('affected.noCopy');
  if (e.usage === null || e.usage === undefined) return t('affected.unknown');
  return t('affected.none');
}

/** Package files under the sync sides: one row per file with its state and engine folder, then a total line. */
const ROLE_ICON = { model: 'box', texture: 'image', buffer: 'database' };   // a .gltf's .bin is data, not an image

function packageRows(e) {
  const files = e.package?.files || [];
  const sources = e.package?.sources || [];
  const unresolved = e.package?.unresolved || [];
  if (files.length < 2 && !sources.length && !unresolved.length) return '';
  const label = f => f.sync === 'missing_in_engine' ? t('pkg.new') : f.sync ? SYNC[f.sync][1] : '';
  const cls = f => f.sync ? SYNC[f.sync][0] : 'dim';
  const rows = files.map(f => `<div class="pkgrow ${f.role}">${icon(ROLE_ICON[f.role] || 'image')}<span class="ellip" title="${esc(f.id)}">${esc(f.name)}</span>
      <span class="synclabel ${cls(f)} ${f.basis === 'mtime' ? 'provisional' : ''}">${esc(label(f))}</span>
      <span class="mono dim ellip" title="${esc(f.engine_path || '')}">${f.engine_path ? esc(relToAssets(f.engine_path).split('/').slice(0, -1).join('/') || '/') : ''}</span></div>
      ${f.role === 'texture' && f.ambiguous ? ambiguityPicker(f) : ''}
      ${f.shared ? `<div class="muted pkgtotal pkgshared">${esc(t('pkg.shared', { name: f.name, others: f.shared.join(', ') }))}</div>` : ''}`).join('');
  const toSend = files.filter(f => ['desktop_newer', 'missing_in_engine', 'conflict'].includes(f.sync)).length;
  const same = files.filter(f => f.sync === 'same').length;
  return `<div class="pkg"><div class="label">${t('pkg.title')}</div>${rows}
    <div class="muted pkgtotal">${t('pkg.total', { n: files.length, send: toSend, same })}</div>
    ${sources.length ? `<div class="muted pkgtotal">${esc(t('pkg.sources', { names: sources.join(', ') }))}</div>` : ''}
    ${unresolved.length ? callout('warn', esc(t('pkg.unresolved', { name: e.name, list: unresolved.join(', ') }))) : ''}</div>`;
}

/** Several engine files share this texture's name: the artist pins the one that is this texture. */
function ambiguityPicker(f) {
  return `<div class="pkgpick"><span class="muted">${esc(t('pkg.pickEngineCopy', { name: f.name }))}</span>
    <select data-texture="${esc(f.id)}"><option value="" selected>${t('pkg.pickOne')}</option>${f.ambiguous.map(p => `<option value="${esc(p)}">${esc(relToAssets(p))}</option>`).join('')}</select></div>`;
}

/** The .blend the model comes from: bound explicitly or matched by name; a picker binds another one. */
function blendSection(e) {
  const b = e.blend;
  const row = b ? `<div class="refrow" style="padding-left:6px">${icon('blender')}<span class="mono ellip" title="${esc(b.path)}">${esc(b.id)}</span>
      <span class="chip ${b.bound ? 'accent' : 'dim'} nodot">${b.bound ? t('blend.bound') : t('blend.auto')}</span>
      <button class="btn ghost icon sm" data-open="${esc(b.path)}" title="${t('ui.openInBlender')}">${icon('play')}</button>
      <button class="btn ghost icon sm" data-reveal="${esc(b.path)}" title="${t('ui.reveal')}">${icon('folder')}</button></div>`
    : `<div class="muted" style="font-size:12px">${t('blend.none')}</div>`;
  const options = S.data.blends.map(x => `<option value="${esc(x.id)}" ${b?.bound && b.id === x.id ? 'selected' : ''}>${esc(x.id)}</option>`).join('');
  return `<div class="sec"><span class="label">${t('ins.blenderSource')}</span>${row}
    <select id="insBlend"><option value="">${b?.bound ? t('blend.clear') : t('blend.pick')}</option>${options}</select>
    <div class="muted" style="font-size:11.5px">${t('blend.neverSent')}</div></div>`;
}

const META_RETRY_MS = 2500, META_MAX_TRIES = 40;
const metaCache = new Map();        // item id -> rendered Changes HTML (cleared on each data refresh)
const metaInflight = new Set();     // item ids with a polling loop running

/** Forget rendered sections (called when the project state changes, so a new file version is re-compared). */
export function resetMeta() { metaCache.clear(); }

/** Fills the Changes section from /api/meta/diff; one loop per item, asks again while Blender works. */
async function loadMeta(e, tries) {
  metaInflight.add(e.id);
  const paint = html => { const box = $('#insMeta'); if (box && S.selected === e.id) box.innerHTML = `<span class="label">${t('ins.changes')}</span>${html}`; };
  let r;
  try { r = await api.getWithStatus('/api/meta/diff', { project: S.project, id: e.id }); }
  catch (err) { metaInflight.delete(e.id); paint(callout('bad', esc(err.message))); return; }
  if (r.status === 202 || r.data.state === 'pending') {
    if (tries < META_MAX_TRIES && S.selected === e.id) { setTimeout(() => loadMeta(e, tries + 1), META_RETRY_MS); return; }
    metaInflight.delete(e.id);
    if (tries >= META_MAX_TRIES) paint(`<div class="muted" style="font-size:12px">${t('meta.stillBusy')}</div>`);
    return;
  }
  metaInflight.delete(e.id);
  const html = metaHTML(r.data);
  metaCache.set(e.id, html);
  paint(html);
}

const lines = arr => arr.map(l => `<div class="refrow"><span class="ellip">${esc(l)}</span></div>`).join('');
const fmtSizePair = s => t('meta.size', { sizes: `${fmtSize(s.art)}${s.engine != null ? ` → ${fmtSize(s.engine)}` : ''}` });

function metaHTML(m) {
  if (m.state === 'none') return callout('info', `${t('meta.noBlender')}<br>${esc(fmtSizePair(m.size))}`);
  if (m.state === 'failed') return callout('bad', t('meta.failed'));
  let html = '';
  if (m.send) {
    html += m.send.diff.empty ? `<div class="muted" style="font-size:12px">${t('meta.noDiff')}</div>` : lines(m.send.summary);
    if (m.send.warnings?.length) html += `<div class="sec"><span class="label">${t('meta.warnings')}</span>${callout('warn', m.send.warnings.map(esc).join('<br>'))}</div>`;
  } else if (m.after) {
    const a = m.after;
    html += `<div class="muted" style="font-size:12px">${t('meta.newContent')}</div>` +
      lines([t('meta.objects', { objects: a.object_names?.length || 0, tris: (a.totals?.tris || 0).toLocaleString(locale()), verts: (a.totals?.verts || 0).toLocaleString(locale()) }),
        t('meta.materials', { materials: a.materials?.length || 0, textures: a.textures?.length || 0 }),
        a.bones ? t('meta.rig', { bones: a.bones, actions: a.action_names?.length || 0 }) : null].filter(Boolean));
  }
  if (m.conflict) {
    html += `<div class="sec"><span class="label">${t('meta.artChanged')}</span>${m.conflict.art.summary.length ? lines(m.conflict.art.summary) : `<div class="muted" style="font-size:12px">${t('meta.noDiff')}</div>`}</div>`;
    html += `<div class="sec"><span class="label">${t('meta.engineChanged')}</span>${m.conflict.engine.summary.length ? lines(m.conflict.engine.summary) : `<div class="muted" style="font-size:12px">${t('meta.noDiff')}</div>`}</div>`;
  }
  // Affected engine usage is the "Kullanan" section right below this one; it is not repeated here.
  return html || `<div class="muted" style="font-size:12px">${t('meta.nothing')}</div>`;
}

const pathRow = (label, path) => `<div class="path"><span class="label">${label}</span><span class="mono" title="${esc(path)}">${esc(path)}</span>
  <button class="btn ghost icon sm" data-copy="${esc(path)}" title="${t('ui.copy')}">${icon('copy')}</button><button class="btn ghost icon sm" data-reveal="${esc(path)}" title="${t('ui.reveal')}">${icon('folder')}</button></div>`;

/** The card's decision point: both sides, the last sync, one sentence, and only the actions that fit. */
function syncBlock(e, canSend, canPull) {
  const s = e.sync, provisional = e.basis === 'mtime', synced = e.synced_at ? fmtStamp(e.synced_at) : '';
  // Side states: same | changed | unchanged (a sync record proves it) | older (only the dates say so) | new | missing
  const other = provisional ? 'older' : 'unchanged';
  const art = s === 'same' ? 'same' : s === 'missing_in_engine' ? 'new' : (s === 'desktop_newer' || s === 'conflict') ? 'changed' : other;
  const eng = s === 'same' ? 'same' : s === 'missing_in_engine' ? 'missing' : (s === 'engine_newer' || s === 'conflict') ? 'changed' : other;
  const word = state => t(`side.word.${state}`);
  const side = (name, state, time, size) => `<div class="side ${state}">
    <span class="k">${name}</span><span class="v">${word(state)}</span>
    ${state === 'missing' ? '<span class="t">—</span>' : `<span class="t">${time ? fmtDateTime(time) : ''}</span><span class="t">${size != null ? fmtSize(size) : ''}</span>`}</div>`;
  // Times sit inside parentheses so no language needs a suffix after them (Turkish: "10:53'te" vs "11:40'ta").
  const since = synced ? t('syncb.since', { time: synced }) : '';
  const text = {
    same: changedFiles(e).length ? t('pkg.filesChanged', { names: changedFiles(e).join(', ') }) : synced ? t('syncb.same', { time: synced }) : t('syncb.sameNoTime'),
    desktop_newer: t('syncb.desktopNewer', { time: fmtDateTime(e.mtime), clause: provisional ? '' : t('syncb.desktopNewerClause', { since }) }),
    engine_newer: t('syncb.engineNewer', { time: e.engine_mtime ? fmtDateTime(e.engine_mtime) : '', clause: provisional ? '' : t('syncb.engineNewerClause', { since }) }),
    conflict: t('syncb.conflict', { detail: synced ? t('syncb.conflictDetail', { time: synced }) : t('syncb.conflictNoTime') }),
    missing_in_engine: t('syncb.missing', { category: e.category }),
  }[s] || SYNC[s]?.[1] || s;
  const outbox = e.state === 'outbox' ? t('syncb.outbox', { state: STATE_LABEL.ingame }) : '';
  const prov = provisional ? ` <span class="muted">${t('syncb.provisional')}</span>` : '';
  const sendLabel = s === 'conflict' ? t('syncb.sendMine') : t('syncb.send');
  const pullLabel = s === 'conflict' ? t('syncb.takeTheirs') : t('syncb.pull');
  return `<div class="sec sync ${s} ${provisional ? 'provisional' : ''}"><span class="label">${t('syncb.title')}</span>
    <div class="sync-sides">${side(t('syncb.desktop'), art, e.mtime, e.size)}<span class="arrow">⟷</span>${side(t('syncb.unity'), eng, e.engine_mtime, e.engine_size)}</div>
    <div class="sync-text">${text}${outbox}${prov}</div>
    ${packageRows(e)}
    ${canSend || canPull ? `<div class="sync-actions">
      ${canSend ? `<button class="btn ${s === 'conflict' ? 'danger' : 'primary'}" id="insSend">${icon('send')} ${sendLabel}</button>` : ''}
      ${canPull ? `<button class="btn ${s === 'conflict' ? 'danger' : ''}" id="insPull">${icon('inbox')} ${pullLabel}</button>` : ''}</div>` : ''}
  </div>`;
}

function usedBy(e) {
  if (!e.used_by?.length) return `<div class="muted" style="font-size:12px">${e.usage === 'unused' ? t('usedBy.unused') : e.engine_path ? t('usedBy.noneFound') : t('usedBy.unknown')}</div>`;
  const groups = {};
  for (const r of e.used_by) (groups[r.kind || 'other'] ||= []).push(r);
  return Object.entries(groups).sort().map(([k, rows]) => `<div class="kindgroup"><div class="kindhead" style="color:${KIND[k]?.color || KIND.other.color}">${icon(KIND[k]?.icon || 'box')}${KIND[k]?.label || k}<span class="n">${rows.length}</span></div>
    ${rows.map(r => `<div class="refrow"><span class="mono ellip" title="${esc(r.path)}">${esc(r.path)}</span><button class="btn ghost icon sm" data-reveal="${esc(enginePathAbs(r.path))}" title="${t('ui.reveal')}">${icon('folder')}</button><button class="btn ghost icon sm" data-graph="${esc(r.path)}" title="${t('ui.showInGraph')}">${icon('share')}</button></div>`).join('')}</div>`).join('');
}

/** Project mode: the asset card has no art-folder controls; only reveal, copy, related assets and tasks. */
function bindProjectCard(el, e) {
  $('#insClose').onclick = () => actions.select(null);
  $$('[data-copy]', el).forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast(t('ui.copied'), 'ok')));
  $$('[data-reveal]', el).forEach(b => b.onclick = () => reveal(b.dataset.reveal));
  bindAssetCard(el);
  bindMarkSection(el, e);
  bindTaskMinis(el);
  const input = $('#insTask'), add = () => { if (!input.value.trim()) return; addTask(input.value, e.id, '').then(() => commit(t('tasks.added'))); };
  input.onkeydown = ev => { if (ev.key === 'Enter') add(); }; $('#insTaskAdd').onclick = add;
}

function bind(el, e) {
  $('#insClose').onclick = () => actions.select(null);
  $$('[data-copy]', el).forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast(t('ui.copied'), 'ok')));
  $$('[data-reveal]', el).forEach(b => b.onclick = () => reveal(b.dataset.reveal));
  $$('[data-open]', el).forEach(b => b.onclick = () => openFile(b.dataset.open));
  $$('[data-graph]', el).forEach(b => b.onclick = () => { S.graphFocus = b.dataset.graph; actions.setView('graph'); });
  const g = $('#insGraph'); if (g) g.onclick = () => showInGraph(e.engine_path);
  const bi = $('#insBringIn'); if (bi) bi.onclick = () => bringIn(e);
  bindMarkSection(el, e);
  $$('select[data-texture]', el).forEach(s => s.onchange = () => { if (!s.value) return; api.post('/api/meta', { project: S.project, id: s.dataset.texture, engine_path: s.value }).then(() => commit(t('ins.engineMatchSaved'))).catch(err => toast(err.message)); });
  const amb = $('#insAmbig'); if (amb) amb.onchange = () => amb.value && api.post('/api/meta', { project: S.project, id: e.id, engine_path: amb.value }).then(() => commit(t('ins.engineMatchSaved'))).catch(err => toast(err.message));
  const send = $('#insSend'); if (send) send.onclick = () => sendToEngine(e);
  const pull = $('#insPull'); if (pull) pull.onclick = () => pullFromEngine(e);
  $$('.statebar button', el).forEach(b => b.onclick = () => moveTo(e, b.dataset.state));
  const blend = $('#insBlend'); if (blend) blend.onchange = () => api.post('/api/meta', { project: S.project, id: e.id, blend: blend.value }).then(() => commit(t('blend.saved'))).catch(err => toast(err.message));
  const note = $('#insNote');
  const saveNote = () => { if (note.value === (e.note || '')) return; api.post('/api/meta', { project: S.project, id: e.id, note: note.value }).then(() => commit(t('ins.noteSaved'))).catch(err => toast(err.message)); };
  note.onblur = saveNote; note.onkeydown = ev => { if (ev.key === 'Enter' && ev.ctrlKey) note.blur(); };
  const input = $('#insTask'), add = () => { if (!input.value.trim()) return; addTask(input.value, e.id, '').then(() => commit(t('tasks.added'))); };
  input.onkeydown = ev => { if (ev.key === 'Enter') add(); }; $('#insTaskAdd').onclick = add;
  bindTaskMinis(el);
}

async function moveTo(e, state) {
  if (state === e.state) return;
  const ok = await modal({ title: t('move.title', { state: STATE_LABEL[state] }), body: t('move.body', { name: e.name, state: STATE_LABEL[state] }), ok: t('move.ok') });
  if (!ok) return;
  try { await api.post('/api/move', { project: S.project, id: e.id, state }); S.selected = null; await commit(`${e.name} → ${STATE_LABEL[state]}`); }
  catch (err) { toast(err.message); }
}

async function sendToEngine(e) {
  const btn = $('#insSend'); if (btn) { btn.disabled = true; btn.textContent = t('send.preparing'); }
  let plan;
  try { plan = await api.get('/api/send/plan', { project: S.project, id: e.id }); }
  catch (err) { toast(friendlyError(err.message)); renderInspector(); return; }
  const movable = plan.files.filter(f => f.action === 'send');
  if (!movable.length && e.state === 'outbox' && plan.files[0].sync === 'same') {     // sent earlier, the move failed
    try {
      const r = await api.post('/api/send', { project: S.project, id: e.id });
      if (r.move_error) { toast(t('pkg.moveFailed', { msg: r.move_error })); renderInspector(); return; }
      S.selected = null;
      await commit(t('pkg.movedToGame'));
    } catch (err) { toast(friendlyError(err.message)); renderInspector(); }
    return;
  }
  const checks = movable.map(f => ({ id: f.id, checked: f.default, label: `${base(f.source)} → ${relToAssets(f.target)}`,
    note: f.team_changed ? t('pkg.teamChanged') : f.ambiguous ? t('pkg.ambiguousNote') : f.force_reason === 'no_base' ? t('pkg.noBaseNote') : '' }));
  const items = [];
  const model = plan.files[0];
  if (model.action === 'send') {
    if (plan.force_reason === 'changed') items.push(t('send.changed', { when: e.engine_mtime ? t('send.changedWhen', { time: fmtDateTime(e.engine_mtime) }) : '', backup: plan.backup }));
    else if (plan.force_reason === 'no_base') items.push(t('send.noBase', { backup: plan.backup }));
    else if (plan.overwrites) items.push(t('send.overwrites', { backup: plan.backup }));
    else items.push(t('send.newFile'));
  }
  for (const f of plan.files.filter(x => x.action === 'no_target')) items.push(t('pkg.noTarget', { name: base(f.source) }));
  items.push(t('send.meta'));
  if (e.state === 'outbox') items.push(t('send.outboxMove', { state: STATE_LABEL.ingame }));
  items.push(affectedLine(e));
  for (const w of plan.warnings) items.push('⚠ ' + w);
  const teamWork = movable.some(f => f.team_changed);
  const danger = plan.warnings.length > 0 || teamWork;
  const picked = await modal({ title: teamWork ? t('send.titleForce') : plan.warnings.length ? t('send.titleWarn') : t('send.title'),
    body: plan.warnings.length ? t('send.bodyWarn', { name: base(plan.source) }) : t('send.body', { name: base(plan.source) }),
    checks, checksTitle: t('pkg.filesToSend'), items, ok: teamWork ? t('send.okForce') : t('send.ok'), danger });
  if (!picked || !picked.length) { renderInspector(); return; }
  const force = movable.some(f => picked.includes(f.id) && f.force_reason);
  try {
    const expect = Object.fromEntries(movable.filter(f => picked.includes(f.id)).map(f => [f.id, { target: f.target_sha, source: f.source_sha }]));
    const r = await api.post('/api/send', { project: S.project, id: e.id, accept_warnings: true, force, files: picked, expect });
    if (r.moved_to) S.selected = null;
    const sent = r.results.filter(x => x.outcome === 'sent').length, failed = r.results.find(x => x.outcome === 'failed');
    if (failed) toast(t('pkg.partial', { name: base(failed.target || failed.id) }));
    if (r.refresh_error) toast(t('pkg.refreshFailed'));
    if (r.move_error) toast(t('pkg.moveFailed', { msg: r.move_error }));
    await commit(t('pkg.sentN', { n: sent }));
  } catch (err) { toast(friendlyError(err.message)); renderInspector(); }
}

async function pullFromEngine(e) {
  const btn = $('#insPull'); if (btn) { btn.disabled = true; btn.textContent = t('send.preparing'); }
  let plan;
  try { plan = await api.get('/api/pull/plan', { project: S.project, id: e.id }); }
  catch (err) { toast(friendlyError(err.message)); renderInspector(); return; }
  const movable = plan.files.filter(f => f.action === 'pull');
  const checks = movable.map(f => ({ id: f.id, checked: f.default, label: `${relToAssets(f.source)} → ${base(f.target)}`,
    note: f.art_changed ? t('pkg.artChanged') : f.ambiguous ? t('pkg.ambiguousNote') : f.force_reason === 'no_base' ? t('pkg.noBaseNote') : '' }));
  const modelMoves = movable.some(f => f.role === 'model');
  const items = [...(modelMoves ? [t('pull.overwrites', { backup: plan.backup })] : []), affectedLine(e)];
  const artWork = movable.some(f => f.art_changed);
  const picked = await modal({ title: artWork ? t('pull.titleForce') : t('pull.title'), body: t('pull.body', { name: base(plan.source) }),
    checks, checksTitle: t('pkg.filesToPull'), items, ok: artWork ? t('pull.okForce') : t('pull.ok'), danger: artWork });
  if (!picked || !picked.length) { renderInspector(); return; }
  const force = movable.some(f => picked.includes(f.id) && f.force_reason);
  try {
    const expect = Object.fromEntries(movable.filter(f => picked.includes(f.id)).map(f => [f.id, { target: f.target_sha, source: f.source_sha }]));
    const r = await api.post('/api/pull', { project: S.project, id: e.id, force, files: picked, expect });
    const failed = r.results.find(x => x.outcome === 'failed');
    if (failed) toast(t('pkg.partial', { name: base(failed.target || failed.id) }));
    if (r.refresh_error) toast(t('pkg.refreshFailed'));
    await commit(t('pkg.pulledN', { n: r.results.filter(x => x.outcome === 'sent').length }));
  } catch (err) { toast(friendlyError(err.message)); renderInspector(); }
}
