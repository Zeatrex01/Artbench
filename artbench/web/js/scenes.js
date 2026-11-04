// Scenes view: what each engine scene uses (read-only), from the files or a fresh engine-bridge report
// (GET /api/v1/scene_inventory). Rows matched to an art item open its card.
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { esc, emptyState, callout, fmtTime } from './ui.js';
import { S, KIND, SYNC, actions } from './state.js';
import { groupHead } from './library.js';

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

function row(u) {
  const k = KIND[u.kind] || { icon: 'question', color: 'var(--muted)', label: u.kind };
  const id = u.desktop_id || u.engine_id;
  const sync = u.sync && SYNC[u.sync] ? `<span class="dot ${SYNC[u.sync][0]}" title="${esc(SYNC[u.sync][1])}"></span>` : '';
  return `<div class="srow ${id ? 'link' : ''} ${id && S.selected === id ? 'on' : ''}" ${id ? `data-id="${esc(id)}"` : ''}>
    <span class="k" style="color:${k.color}" title="${esc(k.label)}">${icon(k.icon)}</span>
    <span class="ellip"><span class="name">${esc(name(u.path))}</span> <span class="sub">${esc(u.path.replace(/^Assets\//, ''))}</span></span>
    ${u.placeholder ? `<span class="chip violet nodot">${t('scenes.placeholder')}</span>` : ''}
    ${u.count != null ? `<span class="sub">×${u.count}</span>` : ''}${sync}</div>`;
}

export function viewScenes() {
  const head = callout('info', t('scenes.head'), 'clapper');
  if (S.scenesError) return head + callout('bad', esc(t('scenes.error', { msg: S.scenesError })));
  if (S.scenes == null) { loadScenes(); return head + emptyState('refresh', t('app.scanning')); }
  if (!S.scenes.length) return head + emptyState('clapper', t('scenes.empty'));
  return head + S.scenes.map(s => {
    const src = s.source === 'live'
      ? `<span class="chip ok nodot" title="${esc(t('scenes.liveTitle'))}">${t('scenes.live', { time: fmtTime(s.time) })}</span>`
      : `<span class="chip dim nodot">${t('scenes.files')}</span>`;
    const dirty = s.dirty ? `<span class="chip warn nodot">${t('scenes.dirty')}</span>` : '';
    return `<div class="group">${groupHead(name(s.path), s.path.replace(/^Assets\//, '').replace(/\/[^/]+$/, ''), s.uses.length, src + dirty, false)}
      <div class="slist">${s.uses.length ? s.uses.map(row).join('') : `<div class="muted" style="font-size:12px">${t('scenes.nothing')}</div>`}</div></div>`;
  }).join('');
}
