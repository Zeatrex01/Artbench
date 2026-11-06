// Boot, polling and routing. Views render into #view; the inspector follows the selection.
import { api } from './api.js';
import { icon } from './icons.js';
import { $, $$, hashOf, prefs, toast, emptyState } from './ui.js';
import { t } from './i18n.js';
import { S, actions, assetsRootOf, counts, filteredItems, findEntry, homeView, isProject, viewsFor } from './state.js';
import { viewCatalog, viewUnused, bindCatalog, filteredAssets, pcounts } from './catalog.js';
import { clearThumbs, observeThumbs } from './thumbs.js';
import { renderSidebar, renderStamps } from './sidebar.js';
import { viewLibrary, bindCommon } from './library.js';
import { renderInspector, resetMeta } from './inspector.js';
import { viewTasks, bindTasks } from './tasks.js';
import { viewEngine, viewPlaceholders, viewLayout, viewBlends, viewChanges, viewHistory, viewUnsorted, bindViews } from './views.js';
import { viewGraph, initGraph } from './graph.js';
import { viewScenes, loadScenes, bindScenes } from './scenes.js';
import { viewChecks, bindChecks } from './checks.js';
import { viewArchive, bindArchive } from './archive.js';
import { viewMarked, bindMarked, bindPicks, renderPickBar } from './marks.js';
import { openProjects, closeProjects, isProjectsOpen } from './projects.js';
import { playLaunch } from './launch.js';

const PULSE_MS = 5000;        // the light look (tasks, open in Blender, the AI line) while the window is in front
const BACKGROUND_PULSE_MS = 30000;
const BACKGROUND_FULL_MS = 60000;   // the project rescan behind other windows: never more often than this
/** Seconds between project rescans, the project's setting (Projects screen): 5, 15 (default), 60, or 0 by hand. */
const refreshSeconds = () => { const p = (S.projects || []).find(x => x.id === S.project); return p && p.refresh != null ? p.refresh : 15; };
const ALIVE_MS = 60000;      // the app window's server stops after a quiet spell; an open page keeps it alive

async function loadProjects() {
  S.projects = await api.get('/api/projects');
  const usable = S.projects.filter(p => !p.error);
  if (!usable.find(p => p.id === S.project)) S.project = usable[0]?.id || null;
  prefs.set('project', S.project);
  if (!S.project) openProjects(); else render();            // 'Scanning…' until the first state arrives
}

/** The light look between rescans: the board and the AI line, no scan. */
async function pulse() {
  if (!S.project || S.busy || !S.data) return;
  const project = S.project;
  try {
    const p = await api.get('/api/pulse', { project });
    if (project !== S.project || S.busy) return;
    S.data.ai_activity = p.ai_activity;
    const h = hashOf(p.tasks);
    if (h === S.hashes.tasks) { renderStamps(); return; }
    S.tasks = p.tasks; S.hashes.tasks = h;
    if (!document.activeElement?.closest('#view, #inspector')) render(); else renderStamps();
  } catch { /* the next rescan says so */ }
}

async function refresh(force = false) {
  if (!S.project || S.busy) return;
  S.busy = true;
  const project = S.project;                                // a switch while this runs must not get this project's data
  try {
    const [data, tasks, history, changes, bridge, github, blenderNotes] = await Promise.all([
      api.get(force ? '/api/refresh' : '/api/state', { project }),
      api.get('/api/tasks', { project }),
      api.get('/api/history', { project }),
      api.get('/api/changes', { project, limit: 400 }),
      api.get('/api/v1/engine_status', { project }).then(r => r.result, () => null),
      api.get('/api/projects/github', { project }).catch(() => null),
      api.get('/api/v1/blender_notes', { project }).then(r => r.result, () => []),
    ]);
    if (project !== S.project) return;
    S.engineStatus = bridge;
    S.github = github;
    const sinceSeen = data.since_seen || [];               // project mode: what came after the last Mark as seen
    S.assetsRoot = assetsRootOf(data.engine_root);
    const h = { github: hashOf(github), data: hashOf([data.items, data.engine_only, data.placeholders, data.blends, data.unsorted, data.layout_issues, data.states, data.catalog]), tasks: hashOf(tasks), notes: hashOf(blenderNotes), history: hashOf(history), changes: hashOf(changes), seen: hashOf(sinceSeen) };
    const changed = Object.keys(h).some(k => h[k] !== S.hashes[k]);
    if (h.data !== S.hashes.data) { resetMeta(); S.checks = null; }   // files changed: compare again, check again
    S.data = data; S.tasks = tasks; S.blenderNotes = blenderNotes; S.history = history; S.changes = changes; S.sinceSeen = sinceSeen; S.hashes = h;
    if (!viewsFor().some(v => v[0] === S.view)) { S.view = homeView(); render(); return; }
    if (S.view === 'scenes') loadScenes();
    if (S.selected && !findEntry(S.selected)) S.selected = null;
    if (changed && !document.activeElement?.closest('#view, #inspector')) render(); else renderStamps();
  } catch (e) { if (project === S.project) toast(t('app.serverUnreachable', { msg: e.message })); }
  finally { S.busy = false; if (project !== S.project) refresh(); }   // the switch's own refresh was skipped while busy
}

function render() {
  if (!S.data) { $('#view').innerHTML = emptyState('refresh', t('app.scanning'), t('app.scanningSub')); const ins = $('#inspector'); if (ins) { ins.hidden = true; ins.innerHTML = ''; } return; }
  renderSidebar(); renderTopbar(); renderView(); renderInspector();
}

function renderTopbar() {
  const v = viewsFor().find(x => x[0] === S.view) || viewsFor()[0];
  const c = counts(), pc = isProject() ? pcounts() : null;
  const cnt = isProject()
    ? { marked: Object.keys(S.data.marks || {}).length, catalog: `${filteredAssets().length} / ${pc.total}`, unused: pc.unreferenced + pc.byName, placeholders: pc.placeholders, tasks: S.tasks.length, layout: S.data.layout?.enabled ? c.layout : null, changes: pc.changes, scenes: S.scenes?.length, checks: S.checks?.std?.total, archive: S.archived?.length }[S.view]
    : { marked: Object.keys(S.data.marks || {}).length, library: `${filteredItems().length} / ${c.models}`, engine: c.engine, placeholders: c.placeholders, tasks: S.tasks.length, layout: S.data.layout?.enabled ? c.layout : null, blends: c.blends, changes: c.changes, history: S.history.length, unsorted: c.unsorted, scenes: S.scenes?.length, checks: S.checks?.std?.total, archive: S.archived?.length }[S.view];
  const searchable = ['library', 'engine', 'placeholders', 'blends', 'catalog', 'unused'].includes(S.view);
  $('#topbar').innerHTML = `<h2>${icon(v[2])} ${t(v[1])} ${cnt != null ? `<span class="cnt">${cnt}</span>` : ''}</h2><div class="grow"></div>
    ${searchable ? `<div class="search">${icon('search')}<input type="text" id="search" placeholder="${t(isProject() ? 'app.searchPlaceholderProject' : 'app.searchPlaceholder')}" value="${S.search.replace(/"/g, '&quot;')}"><kbd>/</kbd></div>` : ''}
    ${S.view === 'library' ? `<div class="seg"><button class="${S.listMode === 'grid' ? 'on' : ''}" data-mode="grid" title="${t('app.gallery')}">${icon('grid')}</button><button class="${S.listMode === 'list' ? 'on' : ''}" data-mode="list" title="${t('app.list')}">${icon('list')}</button></div>` : ''}
    <button class="btn icon" id="refreshBtn" title="${t('app.refreshTitle')}">${icon('refresh')}</button>`;
  const s = $('#search'); if (s) s.oninput = () => {
    S.search = s.value; renderView(); const h = $('#topbar h2 .cnt');
    if (h && S.view === 'library') h.textContent = `${filteredItems().length} / ${c.models}`;
    if (h && S.view === 'catalog') h.textContent = `${filteredAssets().length} / ${pc.total}`;
  };
  $$('[data-mode]').forEach(b => b.onclick = () => { S.listMode = b.dataset.mode; prefs.set('listMode', S.listMode); renderTopbar(); renderView(); });
  $('#refreshBtn').onclick = async () => { const b = $('#refreshBtn'); b.disabled = true; await refresh(true); b.disabled = false; toast(t('app.refreshed'), 'ok'); };
}

function renderView() {
  const el = $('#view');
  const views = { marked: viewMarked, library: viewLibrary, engine: viewEngine, placeholders: viewPlaceholders, tasks: viewTasks, layout: viewLayout, graph: viewGraph, scenes: viewScenes, blends: viewBlends, changes: viewChanges, history: viewHistory, unsorted: viewUnsorted, catalog: viewCatalog, unused: viewUnused, checks: viewChecks, archive: viewArchive };
  const keepScroll = el.dataset.view === S.view ? el.scrollTop : 0;
  el.dataset.view = S.view;
  el.classList.toggle('tight', S.view === 'graph');
  el.innerHTML = (views[S.view] || (isProject() ? viewCatalog : viewLibrary))();
  observeThumbs(el);
  bindCommon(el); bindViews(el); bindTasks(el); if (isProject()) bindCatalog(el);
  if (S.view === 'scenes') bindScenes(el);
  if (S.view === 'marked') bindMarked(el);
  if (S.view === 'checks') bindChecks(el);
  if (S.view === 'archive') bindArchive(el);
  bindPicks(el); renderPickBar();
  if (S.view === 'graph') initGraph();
  el.scrollTop = keepScroll;
}

function setView(view) { S.view = view; prefs.set('view', view); S.search = ''; render(); }
function switchProject(id) { S.picked.clear(); S.project = id; prefs.set('project', id); S.data = null; S.catFilters = { kind: null, usage: null, folder: null, mark: null, tag: null }; S.markTag = null; S.graph = null; S.scenes = null; S.scenesError = null; S.checks = null; S.checkRule = null; S.archived = null; S.taskArchive = null; S.taskArchiveOpen = false; S.engineStatus = null; S.selected = null; S.hashes = {}; clearThumbs(); render(); refresh(); }
function select(id, jump = false) {
  S.selected = (S.selected === id && !jump) ? null : id;
  if (jump && S.selected && isProject()) {
    if (!['catalog', 'unused', 'placeholders'].includes(S.view)) setView(id.startsWith('engine:') && findEntry(id)?.kind ? 'catalog' : 'placeholders');
  } else if (jump && S.selected) {
    const e = findEntry(id);
    if (e?.state === 'engine_only') setView('engine');
    else if (id.startsWith('engine:')) setView('placeholders');
    else if (S.view !== 'library') setView('library');
  }
  $$('.tile, .lrow, .srow, .catrow').forEach(n => n.classList.toggle('on', n.dataset.id === S.selected));
  renderInspector();
}

Object.assign(actions, { setView, select, refresh, switchProject, openProjects, closeProjects, render, renderView, renderInspector, loadProjects });

document.addEventListener('keydown', e => {
  const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
  if (e.key === '/' && !typing) { const s = $('#search'); if (s) { e.preventDefault(); s.focus(); s.select(); } }
  if (e.key === 'Escape' && $('#modal').hidden && isProjectsOpen()) { closeProjects(); return; }
  if (e.key === 'Escape' && !typing && $('#modal').hidden && S.selected) select(null);
});

(async function boot() {
  playLaunch();
  api.get('/api/alive').then(a => { S.about = a; if (S.data) renderSidebar(); }, () => {});   // the version and the signature
  try { await loadProjects(); } catch (e) { toast(t('app.serverUnreachable', { msg: e.message })); }
  if (S.project) await refresh();
  // In front: the light look every 5 s, the project rescan as the project's setting says (15 s unless set; 0: only the
  // refresh button). Open behind other windows (kept open for AI tools): the light look every 30 s, a rescan at most
  // once a minute. Minimised: nothing. Coming back to the window rescans at once.
  let lastFull = Date.now(), lastPulse = Date.now();
  const full = () => { lastFull = lastPulse = Date.now(); refresh(); };
  setInterval(() => {
    if (document.hidden || isProjectsOpen()) return;
    const front = document.hasFocus(), secs = refreshSeconds(), now = Date.now();
    const fullEvery = secs ? (front ? secs * 1000 : Math.max(secs * 1000, BACKGROUND_FULL_MS)) : Infinity;
    if (now - lastFull >= fullEvery) full();
    else if (now - lastPulse >= (front ? PULSE_MS : BACKGROUND_PULSE_MS)) { lastPulse = now; pulse(); }
  }, 1000);
  addEventListener('focus', () => { if (!document.hidden && !isProjectsOpen()) full(); });
  setInterval(() => { api.get('/api/alive').catch(() => {}); }, ALIVE_MS);     // also while hidden or minimised
})();
