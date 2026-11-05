// Archive: engine assets the game no longer needs move with their .meta out of the game project
// (/api/v1/archive_plan, /api/v1/archive), only when nothing uses them; the Archive view lists them and Restore puts one
// back where it was with the same GUID (/api/v1/archived, /api/v1/restore). Nothing is deleted.
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $$, esc, toast, modal, emptyState, callout, fmtDateTime } from './ui.js';
import { S, actions } from './state.js';

const nameOf = p => (p || '').split('/').pop();

/** Shows what would go and what stays, then archives on OK. */
export async function archiveFlow(ids) {
  ids = ids.filter(id => id.startsWith('engine:'));
  if (!ids.length) return;
  let plan;
  try { plan = (await api.post('/api/v1/archive_plan', { project: S.project, ids })).result; }
  catch (e) { toast(e.message); return; }
  const stays = plan.blocked.map(b => t('arch.blocked.' + b.reason, { name: nameOf(b.path || b.id), n: b.used_by_count || 0, first: nameOf((b.used_by || [])[0]) }));
  if (!plan.archive.length) { toast(t('arch.none') + (stays.length ? ' ' + stays[0] : '')); return; }
  const items = plan.archive.map(a => (a.warn ? '⚠ ' + t('arch.warn.' + a.warn, { name: nameOf(a.path) }) : nameOf(a.path)) + (a.files.length > 1 ? t('arch.withMeta') : ''))
    .concat(stays.map(s => t('arch.stays') + ' ' + s));
  const ok = await modal({ title: t('arch.title', { n: plan.archive.length }), body: t('arch.body', { dest: plan.dest }), items, ok: t('arch.ok', { n: plan.archive.length }), danger: true });
  if (!ok) return;
  try {
    const r = (await api.post('/api/v1/archive', { project: S.project, ids: plan.archive.map(a => a.id) })).result;
    toast(t('arch.done', { n: r.archived }), 'ok');
    plan.archive.forEach(a => S.picked.delete(a.id));
    if (plan.archive.some(a => a.id === S.selected)) S.selected = null;
    S.archived = null;
    await actions.refresh(true);
  } catch (e) { toast(e.message); }
}

async function loadArchived() {
  const project = S.project;
  try { const r = (await api.get('/api/v1/archived', { project })).result; if (project === S.project) S.archived = r; }
  catch (e) { if (project === S.project) S.archived = { error: e.message }; }
  if (S.view === 'archive') actions.renderView();
}

export function viewArchive() {
  const head = callout('info', t('arch.head'), 'trash');
  if (S.archived == null) { loadArchived(); return head + emptyState('refresh', t('app.scanning')); }
  if (S.archived.error) return head + callout('bad', esc(S.archived.error));
  if (!S.archived.length) return head + emptyState('trash', t('arch.empty'));
  return head + `<div class="list archlist">${S.archived.map(r => `<div class="lrow archrow">
      <span class="kicon" style="--c:var(--dim)">${icon('trash')}</span>
      <div class="ellip"><span class="name">${esc(nameOf(r.path))}</span> <span class="sub">${esc(r.path.split('/').slice(0, -1).join('/'))}</span></div>
      <div class="meta"><span class="muted">${esc(fmtDateTime(r.time))}</span></div>
      <div class="r"><button class="btn sm" data-restore="${esc(r.id)}">${icon('refresh')}${t('arch.restore')}</button></div></div>`).join('')}</div>`;
}

export function bindArchive(el) {
  $$('[data-restore]', el).forEach(b => b.onclick = async () => {
    b.disabled = true;
    try {
      const r = (await api.post('/api/v1/restore', { project: S.project, ids: [b.dataset.restore] })).result;
      if (r.restored.length) toast(t('arch.restored', { n: r.restored.length }), 'ok');
      else toast(t('arch.exists'));
      S.archived = null;
      await actions.refresh(true);
      actions.renderView();
    } catch (e) { toast(e.message); b.disabled = false; }
  });
}
