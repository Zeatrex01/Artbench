// Scenes view: what each engine scene uses (read-only), from the files or a fresh engine-bridge report
// (GET /api/v1/scene_inventory). One scene at a time: the scenes on the left (filterable), the selected scene on the
// right with a figure per kind (a click narrows to that kind) and its assets grouped by kind, in columns. Rows matched
// to an asset open its card.
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $, $$, esc, emptyState, callout, fmtTime } from './ui.js';
import { S, KIND, SYNC, actions, isProject } from './state.js';
import { KIND_ORDER, kindIcon, rowVisual } from './catalog.js';

let loading = false;

/** Loads the inventory for the open project into S.scenes; re-renders when it changed. */
export async function loadScenes() {
  if (loading || !S.project) return;
  loading = true;
  try {
    const r = await api.get('/api/v1/scene_inventory', { project: S.project });
    const before = JSON.stringify([S.scenes, S.scenesError]);
    S.scenes = r.result;
    S.scenesError = null;
    if (JSON.stringify([S.scenes, S.scenesError]) !== before && S.view === 'scenes') actions.render();
  } catch (e) {
    const changed = S.scenesError !== e.message;
    S.scenes = []; S.scenesError = e.message;  // shown in the view; the next poll tries again
    if (changed && S.view === 'scenes') actions.render();
  }
  finally { loading = false; }
}

const name = path => path.split('/').pop();
const folder = path => path.replace(/^Assets\//, '').replace(/\/?[^/]+$/, '');
const kindRank = k => { const i = KIND_ORDER.indexOf(k); return i < 0 ? KIND_ORDER.length : i; };

function row(u) {
  const id = u.desktop_id || u.engine_id;
  const sync = u.sync && SYNC[u.sync] ? `<span class="dot ${SYNC[u.sync][0]}" title="${esc(SYNC[u.sync][1])}"></span>` : '';
  return `<div class="srow ${id ? 'link' : ''} ${id && S.selected === id ? 'on' : ''}" ${id ? `data-id="${esc(id)}"` : ''} title="${esc(u.path)}">
    ${isProject() ? rowVisual(u) : kindIcon(u.kind)}
    <span class="ellip"><span class="name">${esc(name(u.path))}</span><span class="sub">${esc(folder(u.path))}</span></span>
    ${u.placeholder ? `<span class="chip violet nodot">${t('scenes.placeholder')}</span>` : ''}
    ${u.count > 1 ? `<span class="times">×${u.count}</span>` : ''}${sync}</div>`;
}

const sourceChip = s => (s.source === 'live'
  ? `<span class="chip ok nodot" title="${esc(t('scenes.liveTitle'))}">${t('scenes.live', { time: fmtTime(s.time) })}</span>`
  : `<span class="chip dim nodot">${t('scenes.files')}</span>`) + (s.dirty ? `<span class="chip warn nodot">${t('scenes.dirty')}</span>` : '');

/** The selected scene: its name and source, a figure per kind, then its assets grouped by kind. */
function detail(s) {
  const byKind = {};
  s.uses.forEach(u => (byKind[u.kind] = byKind[u.kind] || []).push(u));
  const kinds = Object.keys(byKind).sort((a, b) => kindRank(a) - kindRank(b));
  const only = kinds.includes(S.sceneKind) ? S.sceneKind : null;
  const fig = (k, n, label) => `<button class="scn-fig ${(k || null) === only ? 'on' : ''}" data-skind="${esc(k)}"><b>${n}</b><span>${esc(label)}</span></button>`;
  const groups = (only ? [only] : kinds).map(k => `<div class="scn-group"><div class="scn-ghead">${kindIcon(k)}<b>${esc(KIND[k]?.label || k)}</b><span class="cnt">${byKind[k].length}</span></div>
    <div class="scn-grid">${byKind[k].map(row).join('')}</div></div>`).join('');
  return `<div class="scn-head">${kindIcon('scene', 'lg')}<div class="scn-title"><h3>${esc(name(s.path))}</h3><span class="mono">${esc(s.path)}</span></div><div class="grow"></div>${sourceChip(s)}</div>
    ${s.uses.length ? `<div class="scn-figs">${fig('', s.uses.length, t('scenes.all'))}${kinds.map(k => fig(k, byKind[k].length, KIND[k]?.label || k)).join('')}</div>${groups}`
      : `<div class="muted scn-none">${t('scenes.nothing')}</div>`}`;
}

export function viewScenes() {
  const head = callout('info', t('scenes.head'), 'clapper');
  if (S.scenesError) return head + callout('bad', esc(t('scenes.error', { msg: S.scenesError })));
  if (S.scenes == null) { loadScenes(); return head + emptyState('refresh', t('app.scanning')); }
  if (!S.scenes.length) return head + emptyState('clapper', t('scenes.empty'));
  const sel = S.scenes.find(s => s.path === S.scene) || S.scenes[0];
  const q = (S.sceneQuery || '').toLowerCase();
  const items = S.scenes.map(s => `<button class="scn-item ${s === sel ? 'on' : ''}" data-scene="${esc(s.path)}" title="${esc(s.path)}" ${q && !s.path.toLowerCase().includes(q) ? 'hidden' : ''}>
      ${kindIcon('scene')}<span class="scn-txt"><b>${esc(name(s.path))}</b><span>${esc(folder(s.path) || 'Assets')}</span></span>
      <span class="scn-n">${s.uses.length}</span>${s.source === 'live' ? `<span class="dot ok" title="${esc(t('scenes.liveTitle'))}"></span>` : ''}${s.dirty ? `<span class="dot warn" title="${esc(t('scenes.dirty'))}"></span>` : ''}</button>`).join('');
  return head + `<div class="scn"><aside class="scn-list"><div class="scn-filter">${icon('search')}<input type="text" id="scnFilter" placeholder="${t('scenes.filter')}" value="${esc(S.sceneQuery || '')}" spellcheck="false"></div>
      <div class="scn-items">${items}</div></aside>
    <section class="scn-detail">${detail(sel)}</section></div>`;
}

/** Scene list and kind figures; asset rows open their card through the views' own binding. */
export function bindScenes(el) {
  $$('.scn-item', el).forEach(b => b.onclick = () => { S.scene = b.dataset.scene; S.sceneKind = null; actions.renderView(); });
  $$('.scn-fig', el).forEach(b => b.onclick = () => { S.sceneKind = b.dataset.skind && b.dataset.skind !== S.sceneKind ? b.dataset.skind : null; actions.renderView(); });
  const f = $('#scnFilter', el);
  if (f) f.oninput = () => {
    S.sceneQuery = f.value.trim();                            // kept while another scene is picked
    const q = S.sceneQuery.toLowerCase();
    $$('.scn-item', el).forEach(b => { b.hidden = !!q && !b.dataset.scene.toLowerCase().includes(q); });
  };
}
