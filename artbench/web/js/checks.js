// Checks view: advisory, nothing is changed. Standards (GET /api/v1/checks): the project's rules — texture size,
// power of two, Read/Write, compression, naming, triangle budget — as a figure per rule (a click narrows) and the
// issues grouped by rule. Duplicates (what=duplicates): files with the same content in several places, each copy with
// what uses it. The rules card reads and writes the project's standards (/api/v1/checks_settings). Loaded when the
// view opens and again after the files change (S.checks is cleared then).
import { api } from './api.js';
import { icon } from './icons.js';
import { t } from './i18n.js';
import { $, $$, esc, emptyState, callout, toast, fmtSize } from './ui.js';
import { S, KIND, actions, findEntry } from './state.js';
import { catalogAssets, rowVisual, kindIcon, usageChip } from './catalog.js';
import { pickBox, markBadges } from './marks.js';

export const RULES = ['texture_max', 'power_of_two', 'read_write', 'uncompressed', 'naming', 'tris_max'];
const TEXTURE_SIZES = [0, 1024, 2048, 4096, 8192];
const PREFIX_KINDS = ['texture', 'material', 'prefab', 'model'];
let loading = false;

/** Loads the issues, the copies and the rules for the open project into S.checks; re-renders the view. */
export async function loadChecks() {
  if (loading || !S.project) return;
  loading = true;
  const project = S.project;
  try {
    const [std, dup, rules] = await Promise.all([
      api.get('/api/v1/checks', { project, limit: 500 }),
      api.get('/api/v1/checks', { project, what: 'duplicates', limit: 500 }),
      api.post('/api/v1/checks_settings', { project }),
    ]);
    if (project !== S.project) return;
    S.checks = { std: std.result, dup: dup.result, rules: rules.result, error: null };
  } catch (e) {
    if (project !== S.project) return;
    S.checks = { error: e.message };
  } finally { loading = false; }
  if (S.view === 'checks') actions.render();
}

function assetIndex() {
  const m = new Map();
  catalogAssets().forEach(a => m.set(a.id, a));
  return id => m.get(id) || findEntry(id) || { id, name: id.split('/').pop(), kind: 'other', path: id.replace(/^engine:/, '') };
}
const folderOf = a => a.folder ?? (a.path || '').split('/').slice(0, -1).join('/');

function issueRow(i, a) {
  return `<div class="lrow chkrow ${S.selected === i.id ? 'on' : ''}" data-id="${esc(i.id)}">${pickBox(i.id)}${a.path ? rowVisual(a) : kindIcon(a.kind)}
    <div class="ellip"><span class="name">${esc(a.name)}</span> <span class="sub">${esc(folderOf(a))}</span></div>
    <div class="meta">${markBadges(i.id)}<span class="chk-detail">${esc(i.detail)}</span></div>
    <div class="r"><span class="chip ${i.level === 'warn' ? 'warn' : 'info'}">${t('checks.level.' + i.level)}</span></div></div>`;
}

function viewStandards() {
  const { std } = S.checks, of = assetIndex(), only = RULES.includes(S.checkRule) ? S.checkRule : null;
  const counts = std.counts || {}, live = RULES.filter(r => counts[r]);
  const figs = `<div class="stats chk-figs">${RULES.map(r => `<button class="stat ${only === r ? 'on' : ''} ${counts[r] ? '' : 'quiet'}" data-crule="${r}"
      style="--c:var(--${r === 'power_of_two' || r === 'naming' ? 'info' : 'warn'})"><div class="v">${counts[r] || 0}</div><div class="l">${t('checks.rule.' + r)}</div></button>`).join('')}</div>`;
  if (!std.total) return figs + emptyState('check', t('checks.clean'), t('checks.cleanSub'));
  const groups = (only ? [only] : live).map(r => {
    const rows = std.issues.filter(i => i.rule === r);
    return `<div class="group" data-group="chk:${r}"><div class="ghead"><h3>${t('checks.rule.' + r)}</h3><span class="cnt">${counts[r]}</span><div class="line"></div></div>
      <div class="list">${rows.map(i => issueRow(i, of(i.id))).join('')}</div>${rows.length < counts[r] ? `<div class="muted chk-more">${t('checks.more', { n: counts[r] - rows.length })}</div>` : ''}</div>`;
  }).join('');
  return figs + groups;
}

function copyRow(c, a) {
  return `<div class="lrow chkrow ${S.selected === c.id ? 'on' : ''}" data-id="${esc(c.id)}">${pickBox(c.id)}${rowVisual({ ...a, ...c, name: a.name || c.path.split('/').pop() })}
    <div class="ellip"><span class="name">${esc(c.path.split('/').pop())}</span> <span class="sub">${esc(c.path.split('/').slice(0, -1).join('/'))}</span></div>
    <div class="meta">${markBadges(c.id)}${usageChip(c)}</div>
    <div class="r">${c.used_by_count ? t('cat.usedByN', { n: c.used_by_count }) : t('checks.notUsed')}</div></div>`;
}

function viewDuplicates() {
  const { dup } = S.checks, of = assetIndex();
  const figs = `<div class="stats chk-figs"><div class="stat static" style="--c:var(--warn)"><div class="v">${dup.total}</div><div class="l">${t('checks.groups')}</div></div>
    <div class="stat static" style="--c:var(--warn)"><div class="v">${dup.wasted ? fmtSize(dup.wasted) : '0'}</div><div class="l">${t('checks.wastedTotal')}</div></div></div>`;
  if (!dup.total) return figs + emptyState('check', t('checks.noDuplicates'));
  return figs + dup.groups.map(g => `<div class="group chk-dup" data-group="dup:${esc(g.sha)}"><div class="ghead">${kindIcon(g.assets[0].kind)}<h3>${esc(g.assets[0].path.split('/').pop())}</h3>
      <span class="cnt">${t('checks.copies', { n: g.assets.length })} · ${fmtSize(g.size)}</span><span class="chip warn nodot">${t('checks.wasted', { size: fmtSize(g.wasted) })}</span><div class="line"></div></div>
      <div class="list">${g.assets.map(c => copyRow(c, of(c.id))).join('')}</div></div>`).join('');
}

function rulesCard() {
  const r = S.checks.rules || {}, p = r.prefixes || {};
  const box = (key) => `<label class="chk-opt"><input type="checkbox" data-rset="${key}" ${r[key] ? 'checked' : ''}><span>${t('checks.rule.' + key)}</span></label>`;
  return `<div class="card chk-rules"><div class="chk-rgrid">
      <label class="chk-field"><span>${t('checks.textureMax')}</span><select id="rTexMax">${TEXTURE_SIZES.map(n => `<option value="${n}" ${(r.texture_max || 0) === n ? 'selected' : ''}>${n ? n + ' px' : t('checks.off')}</option>`).join('')}</select></label>
      <label class="chk-field"><span>${t('checks.trisMax')}</span><input type="text" inputmode="numeric" id="rTris" value="${r.tris_max || ''}" placeholder="${t('checks.off')}"></label>
      <div class="chk-opts">${box('power_of_two')}${box('read_write')}${box('uncompressed')}${box('naming')}</div>
      <div class="chk-prefixes" ${r.naming ? '' : 'hidden'}>${PREFIX_KINDS.map(k => `<label class="chk-field sm"><span>${esc(KIND[k]?.label || k)}</span><input type="text" data-prefix="${k}" value="${esc(p[k] || '')}" spellcheck="false"></label>`).join('')}</div>
    </div><div class="row chk-rfoot"><span class="muted">${t('checks.trisHint')}</span><div class="grow"></div><button class="btn sm primary" id="rSave">${icon('check')}${t('checks.save')}</button></div></div>`;
}

export function viewChecks() {
  const head = callout('info', t('checks.head'), 'checksq');
  if (S.checks == null) { loadChecks(); return head + emptyState('refresh', t('checks.running')); }
  if (S.checks.error) return head + callout('bad', esc(t('checks.error', { msg: S.checks.error })));
  const tab = S.checkTab === 'duplicates' ? 'duplicates' : 'standards';
  const n = { standards: S.checks.std.total, duplicates: S.checks.dup.total };
  const seg = ['standards', 'duplicates'].map(k => `<button class="${tab === k ? 'on' : ''}" data-ctab="${k}">${t('checks.' + k)}<span class="n">${n[k]}</span></button>`).join('');
  return head + `<div class="row chk-head"><div class="seg">${seg}</div><div class="grow"></div>
      <button class="btn sm ${S.checkRulesOpen ? 'on' : ''}" id="chkRules">${icon('settings')}${t('checks.rules')}</button></div>
    ${S.checkRulesOpen ? rulesCard() : ''}${tab === 'duplicates' ? viewDuplicates() : viewStandards()}`;
}

async function saveRules(el) {
  const set = { texture_max: +$('#rTexMax', el).value, tris_max: +($('#rTris', el).value.replace(/\D/g, '') || 0), prefixes: {} };
  $$('[data-rset]', el).forEach(b => { set[b.dataset.rset] = b.checked; });
  $$('[data-prefix]', el).forEach(i => { set.prefixes[i.dataset.prefix] = i.value.trim(); });
  try {
    await api.post('/api/v1/checks_settings', { project: S.project, set });
    toast(t('checks.saved'), 'ok');
    S.checks = null; actions.renderView();
  } catch (e) { toast(e.message); }
}

export function bindChecks(el) {
  $$('[data-ctab]', el).forEach(b => b.onclick = () => { S.checkTab = b.dataset.ctab; actions.renderView(); });
  $$('[data-crule]', el).forEach(b => b.onclick = () => { S.checkRule = S.checkRule === b.dataset.crule ? null : b.dataset.crule; actions.renderView(); });
  const rules = $('#chkRules', el); if (rules) rules.onclick = () => { S.checkRulesOpen = !S.checkRulesOpen; actions.renderView(); };
  const naming = $('[data-rset="naming"]', el), pre = $('.chk-prefixes', el);
  if (naming && pre) naming.onchange = () => { pre.hidden = !naming.checked; };
  const save = $('#rSave', el); if (save) save.onclick = () => saveRules(el);
}
