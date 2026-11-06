// Secondary views: engine-only, placeholders, layout, blends, changes, history, unsorted. Read-only lists with
// the same chips as the library; bindViews wires reveal / open / jump / graph buttons.
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $, $$, esc, emptyState, callout, toast, fmtStamp } from './ui.js';
import { api } from './api.js';
import { thumbHTML } from './thumbs.js';
import { S, KIND, actions, matches, enginePathAbs, isProject, underPrefix } from './state.js';
import { tile, lrow, groupHead } from './library.js';
import { reveal, openFile } from './inspector.js';

const stem = n => String(n || '').replace(/\.[^.]+$/, '').toLowerCase();
const byCategory = list => { const g = {}; for (const i of list) (g[i.category || '(root)'] ||= []).push(i); return Object.entries(g).sort(); };
const revealBtn = path => `<button class="btn ghost icon sm" data-reveal="${esc(path)}" title="${t('ui.reveal')}">${icon('folder')}</button>`;

export function viewEngine() {
  const list = S.data.engine_only.filter(i => matches(i, S.search));
  const head = callout('info', t('views.engineHead'));
  if (!list.length) return head + emptyState('inbox', t('views.engineEmpty'), S.search ? t('views.engineEmptySearch') : t('views.engineEmptyAll'));
  return head + byCategory(list).map(([cat, items]) => {
    const un = items.filter(i => i.usage === 'unused').length;
    return `<div class="group">${groupHead(cat, '', items.length, un ? `<span class="chip warn nodot">${t('lib.unused', { n: un })}</span>` : '', false)}<div class="grid">${items.map(i => tile(i, i.engine_path)).join('')}</div></div>`;
  }).join('');
}

export function viewPlaceholders() {
  const list = S.data.placeholders.filter(i => matches(i, S.search));
  const head = callout('info', t('views.placeholdersHead'), 'cube');
  if (!list.length) return head + emptyState('cube', t('views.placeholdersEmpty'));
  return head + byCategory(list).map(([cat, items]) => {
    const used = items.filter(i => i.usage === 'used').length;
    return `<div class="group">${groupHead(cat, '', items.length, used ? `<span class="chip violet nodot">${t('lib.used', { n: used })}</span>` : '', false)}<div class="list">${items.map(i => lrow(i, '', i.id.replace(/^engine:/, ''))).join('')}</div></div>`;
  }).join('');
}

/** Rules as "model: Art/Props/, Art/Characters/" lines. */
const rulesList = rules => `<div class="rules">${rules.map(r => `<div class="rule"><span class="k">${esc(r.kinds.map(k => KIND[k]?.label || k).join(', '))}</span><span class="mono">${esc(r.allow.map(a => a.replace(/\*$/, '') || t('views.layoutRoot')).join('   '))}</span></div>`).join('')}</div>`;

export function viewLayout() {
  const issues = S.data.layout_issues, st = S.data.layout || { enabled: true, rules: [], proposed: [] };
  if (!st.enabled) {
    const rules = st.rules.length ? st.rules : st.proposed;
    return callout('info', t('views.layoutOff'), 'map') + (rules.length
      ? `<div class="card layoutcard"><div class="label">${t(st.rules.length ? 'views.layoutOwnRules' : 'views.layoutLearned')}</div>${rulesList(rules)}
         <div class="row"><button class="btn primary" data-layout-on>${icon('check')}${t('views.layoutTurnOn')}</button></div></div>`
      : emptyState('map', t('views.layoutNothing'), ''));
  }
  const head = callout('info', t('views.layoutHead'), 'map')
    + `<div class="card layoutcard"><div class="row"><span class="label">${t('views.layoutRules')}</span><div class="grow"></div><button class="btn ghost sm" data-layout-off>${t('views.layoutTurnOff')}</button></div>${rulesList(st.rules)}</div>`;
  if (!issues.length) return head + emptyState('check', t('views.layoutEmpty'), t('views.layoutEmptySub'));
  const g = {};
  for (const i of issues) (g[i.kind] ||= []).push(i);
  return head + `<div class="issuegrid">${Object.entries(g).sort().map(([kind, rows]) => `<div class="card issuecard">
      <div class="ihead" style="color:${KIND[kind]?.color || KIND.other.color}">${icon(KIND[kind]?.icon || 'box')}${KIND[kind]?.label || kind}<span class="n">${rows.length}</span></div>
      <div class="muted" style="font-size:12px;margin-bottom:8px">${esc(rows[0].hint)}</div>
      ${rows.map(r => `<div class="refrow" style="padding-left:6px"><span class="mono ellip" title="${esc(r.path)}">${esc(r.path)}</span><button class="btn ghost sm" data-allow-kind="${esc(r.kind)}" data-allow-folder="${esc(r.folder === '(root)' ? '' : r.folder)}" title="${t('views.layoutAllowTitle')}">${t('views.layoutAllow')}</button>${revealBtn(r.engine_path)}<button class="btn ghost icon sm" data-graph="${esc(r.path)}" title="${t('ui.showInGraph')}">${icon('share')}</button></div>`).join('')}</div>`).join('')}</div>`;
}

export function viewBlends() {
  const list = S.data.blends.filter(b => matches(b, S.search));
  const head = callout('info', t('views.blendsHead'), 'blender');
  if (!list.length) return head + emptyState('blender', t('views.blendsEmpty'));
  const models = S.data.items;
  return head + byCategory(list).map(([cat, rows]) => `<div class="group">${groupHead(cat, '', rows.length, '', false)}<div class="list">
    ${rows.sort((a, b) => a.name.localeCompare(b.name)).map(b => {
      const n = models.filter(m => stem(m.name) === stem(b.name)).length;
      return `<div class="lrow" style="cursor:default"><div class="thumb sq" style="color:var(--dim)">${icon('blender')}</div><div class="ellip"><span class="name">${esc(b.name)}</span> <span class="sub">${esc(b.id)}</span></div>
        <div class="meta">${n ? `<span class="chip ok nodot">${t('views.blendsModels', { n })}</span>` : `<span class="chip dim nodot">${t('views.blendsNoMatch')}</span>`}</div>
        <div class="r"><button class="btn ghost icon sm" data-open="${esc(b.path)}" title="${t('ui.openInBlender')}">${icon('play')}</button></div><div class="r">${revealBtn(b.path)}</div></div>`;
    }).join('')}</div></div>`).join('');
}

const CHANGE = { ADDED: ['ok', 'change.added'], CHANGED: ['warn', 'change.changed'], REMOVED: ['bad', 'change.removed'], MOVED: ['info', 'change.moved'], BASELINE: ['dim', 'change.baseline'] };

/** Project mode: what is new since the person's last Mark as seen, then the whole feed. */
function projectChange(c) {
  const [cls, labelKey] = CHANGE[c.change] || ['dim', null];
  const id = 'engine:' + underPrefix(String(c.path));
  const known = c.change !== 'REMOVED' && (S.data.catalog?.assets || []).some(a => a.id === id);
  const path = known ? `<a class="mono" data-jump="${esc(id)}" style="cursor:pointer;color:var(--text)">${esc(c.path)}</a>` : `<span class="mono">${esc(c.path)}</span>`;
  return { time: c.time, cls, html: `<span class="chip ${cls} nodot">${labelKey ? t(labelKey) : esc(c.change)}</span>${c.from ? `<span class="mono dim">${esc(c.from)}</span><span class="dim">→</span>` : ''}${path}` };
}

function viewProjectChanges() {
  const head = callout('info', t('views.changesHeadProject'), 'diff');
  const news = S.sinceSeen;
  const top = `<div class="card seenbar"><div><b>${news.length ? t('changes.newCount', { n: news.length }) : t('changes.noneNew')}</b><div class="muted">${t('changes.newSub')}</div></div><div class="grow"></div>
    <button class="btn ${news.length ? 'primary' : ''}" id="markSeen" ${news.length ? '' : 'disabled'}>${icon('check')} ${t('changes.markSeen')}</button></div>`;
  const earlier = S.changes.filter(c => c.change !== 'BASELINE').slice(news.length);   // both newest first: skip the new ones
  return head + top + (news.length ? `<div class="label" style="margin:14px 0 6px">${t('changes.newTitle')}</div>` + timeline(news.map(projectChange)) : '')
    + (earlier.length ? `<div class="label" style="margin:18px 0 6px">${t('changes.all')}</div>` + timeline(earlier.map(projectChange)) : '');
}

export function viewChanges() {
  if (isProject()) return viewProjectChanges();
  const head = callout('info', t('views.changesHead'), 'diff');
  if (!S.changes.length) return head + emptyState('diff', t('views.changesEmpty'));
  return head + timeline(S.changes.map(c => {
    const [cls, labelKey] = CHANGE[c.change] || ['dim', null];
    const label = labelKey ? t(labelKey) : c.change;
    const item = c.side === 'art' ? S.data.items.find(i => i.id === c.path) : null;
    return { time: c.time, cls, html: `<span class="chip ${cls} nodot">${label}</span><span class="chip dim nodot">${c.side === 'art' ? t('change.art') : t('change.engine')}</span>
      ${item ? `<a class="mono" data-jump="${esc(item.id)}" style="cursor:pointer;color:var(--text)">${esc(c.path)}</a>` : `<span class="mono">${esc(c.path)}</span>`}` };
  }));
}

const VERB = { MOVE: 'info', META: 'dim', TASK: 'accent', CONNECT: 'violet', SEND: 'ok', PULL: 'info' };
const VERBS = new Set(['MOVE', 'META', 'TASK ADD', 'TASK TODO', 'TASK DOING', 'TASK DONE', 'TASK DELETE', 'CONNECT', 'SEND', 'PULL']);
const verbLabel = verb => (VERBS.has(verb) ? t(`verb.${verb}`) : verb.toLowerCase());
export function viewHistory() {
  const head = callout('info', t('views.historyHead'), 'clock');
  if (!S.history.length) return head + emptyState('clock', t('views.historyEmpty'));
  return head + timeline(S.history.map(line => {
    const [time, verb = '', ...rawFields] = line.split('\t');
    const forced = (verb === 'SEND' || verb === 'PULL') && rawFields[rawFields.length - 1] === 'FORCED';
    const fields = forced ? rawFields.slice(0, -1) : rawFields;
    const cls = VERB[verb.split(' ')[0]] || 'dim';
    const item = fields[0] && S.data.items.find(i => i.id === fields[0]);
    return { time, cls, html: `<span class="chip ${cls} nodot">${esc(verbLabel(verb))}</span>${forced ? `<span class="chip warn nodot" title="${t('verb.forcedTitle')}">${t('verb.forced')}</span>` : ''}
      ${fields.filter(Boolean).map((f, i) => i === 0 && item ? `<a class="mono" data-jump="${esc(item.id)}" style="cursor:pointer;color:var(--text)">${esc(f)}</a>` : `<span class="mono">${esc(f)}</span>`).join('')}` };
  }));
}

/** Rows {time 'YYYY-MM-DD HH:MM:SS', cls, html} grouped by day, newest first. */
function timeline(rows) {
  let day = null, out = '<div class="timeline">';
  for (const r of rows) {
    const [d, t = ''] = String(r.time).split(' ');
    if (d !== day) { day = d; out += `<div class="label day">${esc(dayLabel(d))}</div>`; }
    out += `<div class="tl"><span class="time">${esc(t.slice(0, 5))}</span><span class="dotcol"><span class="dot ${r.cls}"></span></span><div class="body">${r.html}</div></div>`;
  }
  return out + '</div>';
}
function dayLabel(d) {
  const today = new Date().toISOString().slice(0, 10);
  const y = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  return d === today ? t('ui.today') : d === y ? t('ui.yesterday') : d;
}

export function viewUnsorted() {
  const list = S.data.unsorted;
  const head = callout('warn', t('views.unsortedHead'), 'question');
  if (!list.length) return head + emptyState('check', t('views.unsortedEmpty'));
  return head + `<div class="list">${list.map(u => `<div class="lrow" style="cursor:default">${thumbHTML(u.path, 'sq')}<div class="ellip"><span class="name">${esc(u.name)}</span> <span class="sub">${esc(u.id)}</span></div><div class="meta"></div><div class="r"></div><div class="r">${revealBtn(u.path)}</div></div>`).join('')}</div>`;
}

async function layoutSettings(args) {
  try {
    await api.post('/api/v1/layout_settings', { project: S.project, ...args });
    document.activeElement?.blur();          // the refresh redraws only while nothing in the view has focus
    await actions.refresh();
    actions.render();
  } catch (e) { toast(e.message); }
}

export function bindViews(el) {
  $$('[data-layout-on]', el).forEach(b => b.onclick = () => layoutSettings({ enabled: true }));
  $$('[data-layout-off]', el).forEach(b => b.onclick = () => layoutSettings({ enabled: false }));
  $$('[data-allow-kind]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); layoutSettings({ allow_kind: b.dataset.allowKind, allow_folder: b.dataset.allowFolder }); });
  $$('[data-reveal]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); reveal(b.dataset.reveal); });
  $$('[data-open]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); openFile(b.dataset.open); });
  $$('[data-jump]', el).forEach(a => a.onclick = () => actions.select(a.dataset.jump, true));
  $$('[data-graph]', el).forEach(b => b.onclick = ev => { ev.stopPropagation(); S.graphFocus = b.dataset.graph; actions.setView('graph'); });
  const seen = $('#markSeen', el);
  if (seen) seen.onclick = async () => {
    seen.disabled = true;
    try { await api.post('/api/changes/seen', { project: S.project }); await actions.refresh(); actions.render(); toast(t('changes.marked'), 'ok'); }
    catch (e) { toast(e.message); seen.disabled = false; }
  };
}

/** The card's History: collapsed to one line; opened, one asset's history lines and file changes, newest first
 * (GET /api/v1/asset_history), loaded each time it opens. */
const ahist = { open: false, id: null, data: null, error: null };
export function assetHistorySection(id) {
  if (ahist.id !== id) Object.assign(ahist, { id, data: null, error: null });
  const d = ahist.data, rows = d ? d.entries.map(e => {
    const [cls, label] = e.source === 'change' ? (CHANGE[e.what] ? [CHANGE[e.what][0], t(CHANGE[e.what][1])] : ['dim', e.what])
      : [VERB[e.what.split(' ')[0]] || 'dim', verbLabel(e.what)];
    return `<div class="ahrow"><span class="time">${esc(fmtStamp(e.time))}</span><span class="chip ${cls} nodot">${esc(label)}</span><span class="mono">${esc(e.detail)}</span></div>`;
  }).join('') : '';
  const body = !ahist.open ? '' : ahist.error ? `<div class="muted">${esc(ahist.error)}</div>`
    : !d ? `<div class="muted">${t('app.scanning')}</div>`
    : d.total ? rows + (d.total > d.entries.length ? `<div class="muted ahmore">${t('ins.historyMore', { n: d.total - d.entries.length })}</div>` : '')
    : `<div class="muted">${t('ins.historyNone')}</div>`;
  return `<div class="sec ahist ${ahist.open ? 'open' : ''}"><button class="ahist-head" id="ahToggle">${icon('clock')}<span>${t('ins.history')}</span>
    ${d ? `<span class="n">${d.total}</span>` : ''}<span class="grow"></span>${icon('chevron')}</button>${body}</div>`;
}
export function bindAssetHistory(el, id) {
  const b = $('#ahToggle', el);
  if (!b) return;
  b.onclick = async () => {
    ahist.open = !ahist.open;
    actions.renderInspector();
    if (!ahist.open) return;
    try { ahist.data = (await api.get('/api/v1/asset_history', { project: S.project, id, limit: 30 })).result; ahist.error = null; }
    catch (e) { ahist.error = e.message; }
    if (ahist.id === id) actions.renderInspector();
  };
}
