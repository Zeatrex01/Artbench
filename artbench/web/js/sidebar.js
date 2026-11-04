// Sidebar: brand, project pill, navigation with counts, category/set tree and filter pills (library only), footer.
import { ICONS, icon, markSvg } from './icons.js';
import { $, $$, esc, fmtTime, prefs, toast } from './ui.js';
import { S, STATE_LABEL, actions, counts, setOf, setLabel, bySet, isProject, viewsFor } from './state.js';
import { kindNav, bindKindNav, pcounts } from './catalog.js';
import { t, lang, setLang, LANGUAGES } from './i18n.js';

const pill = (f, v, label, n) =>
  `<span class="pill ${S.filters[f] === v ? 'on' : ''}" data-f="${f}" data-v="${v}">${esc(label)}<span class="n">${n}</span></span>`;

function tree(c) {
  const cats = {};
  for (const it of S.data.items) {
    const cat = cats[it.category] ||= { n: 0, un: 0, sets: {} };
    cat.n++; if (it.usage === 'unused') cat.un++;
    const s = cat.sets[setOf(it)] ||= { n: 0, un: 0 }; s.n++; if (it.usage === 'unused') s.un++;
  }
  const f = S.filters;
  return `<div class="side-section"><div class="label">${t('side.categories')}</div></div><div class="tree">
    <div class="node ${!f.category ? 'on' : ''}" data-cat="">${icon('layers')}<span class="lbl">${t('side.all')}</span><span class="cnt">${c.models}</span></div>
    ${Object.keys(cats).sort().map(cat => {
      const o = cats[cat], closed = S.closedCats[cat];
      return `<div class="node cat ${closed ? 'closed' : ''} ${f.category === cat && !f.set ? 'on' : ''}" data-cat="${esc(cat)}">
          <svg class="i chev" viewBox="0 0 24 24" data-toggle="${esc(cat)}">${ICONS.chevron}</svg><span class="lbl">${esc(cat)}</span>
          ${o.un ? `<span class="un">${o.un}</span>` : ''}<span class="cnt">${o.n}</span></div>
        ${closed ? '' : Object.keys(o.sets).sort(bySet).map(s =>
          `<div class="node set ${f.category === cat && f.set === s ? 'on' : ''}" data-cat="${esc(cat)}" data-set="${esc(s)}"><span class="lbl ellip">${esc(setLabel(s))}</span>
            ${o.sets[s].un ? `<span class="un">${o.sets[s].un}</span>` : ''}<span class="cnt">${o.sets[s].n}</span></div>`).join('')}`;
    }).join('')}</div>
    <div class="side-section"><div class="label">${t('side.filters')}</div></div>
    <div class="pills">${S.data.states.map(s => pill('state', s, STATE_LABEL[s] || s, c[s] ?? 0)).join('')}</div>
    <div class="pills">${pill('usage', 'used', t('usage.used'), c.used)}${pill('usage', 'unused', t('usage.unused'), c.unused)}</div>
    <div class="pills">${c.conflict ? pill('sync', 'conflict', t('sync.conflict'), c.conflict).replace('class="pill', 'class="pill bad') : ''}${pill('sync', 'same', t('sync.sameShort'), c.same)}${pill('sync', 'desktop_newer', t('sync.desktopNewerShort'), c.desktopNewer)}${pill('sync', 'engine_newer', t('sync.engineNewerShort'), c.engineNewer)}${pill('sync', 'missing_in_engine', t('sync.missing_in_engine'), c.missing)}${c.conflict ? '' : pill('sync', 'conflict', t('sync.conflict'), 0)}</div>
    ${Object.values(f).some(Boolean) ? `<div class="pills"><button class="btn ghost sm" id="clearFilters">${icon('x')} ${t('side.clearFilters')}</button></div>` : ''}`;
}

// The GitHub account this project pushes as, and a warning with the switch command when gh is set to another one.
function githubLine() {
  const g = S.github;
  if (!g?.account) return '';
  const other = g.matches === false ? t('side.ghOther', { active: esc(g.active) }) : g.active ? '' : t('side.ghNone');
  return `<div class="ghline ${g.switch ? 'warn' : ''}">${icon('branch')}<span>GitHub <b>${esc(g.account)}</b>${other ? ` · ${other}` : ''}</span>`
    + `${g.switch ? `<button class="btn ghost sm" data-copy="${esc(g.switch)}" title="${esc(g.switch)}">${t('side.ghCopy')}</button>` : ''}</div>`;
}

export function renderSidebar() {
  const c = counts(), project = isProject(), pc = project ? pcounts() : null;
  const navCount = project
    ? { catalog: pc.total, tasks: pc.tasks, unused: pc.unreferenced + pc.byName, placeholders: pc.placeholders, layout: S.data.layout?.enabled ? c.layout : null, changes: pc.changes || null }
    : { library: c.models, engine: c.engine, placeholders: c.placeholders, tasks: c.tasks, layout: S.data.layout?.enabled ? c.layout : null, graph: null, blends: c.blends, changes: c.changes, history: null, unsorted: c.unsorted };
  const warn = { layout: c.layout > 0, unsorted: c.unsorted > 0, changes: project && pc.changes > 0 };
  const projects = S.projects.map(p => `<option value="${esc(p.id)}" ${p.id === S.project ? 'selected' : ''} ${p.error ? 'disabled' : ''}>${esc(p.name || p.id)}${p.error ? t('side.error') : ''}</option>`).join('');
  const navLink = ([k, label, ic]) => `<a class="${S.view === k ? 'on' : ''}" data-view="${k}">${icon(ic)}<span>${t(label)}</span>${navCount[k] != null ? `<span class="n ${warn[k] ? 'warn' : ''}">${navCount[k]}</span>` : ''}</a>`;
  const views = viewsFor().filter(([k]) => k !== 'unsorted' || c.unsorted > 0), more = views.filter(v => v[3]);
  const moreOpen = prefs.get('navMore', false) || more.some(v => v[0] === S.view);   // a view under More keeps it open
  const moreWarn = !moreOpen && more.some(v => warn[v[0]]);
  $('#sidebar').innerHTML = `
    <div class="brand">${markSvg('mark')}<div><h1>Artbench</h1><small>${t('app.subtitle')}</small></div></div>
    <div class="projpill"><select id="projSel">${projects}<option value="__manage">${t('side.manage')}</option></select></div>
    <button class="btn sm side-connect" id="sideConnect">${icon('plus')} ${t('side.connect')}</button>
    ${githubLine()}
    <nav class="nav">${views.filter(v => !v[3]).map(navLink).join('')}
      ${more.length ? `<button class="nav-more ${moreOpen ? 'open' : ''}" id="navMore">${icon('chevron')}<span>${t('side.more')}</span>${moreWarn ? '<span class="n warn">•</span>' : ''}</button>
      <div class="nav-more-list" ${moreOpen ? '' : 'hidden'}>${more.map(navLink).join('')}</div>` : ''}</nav>
    <div class="side-scroll">${S.view === 'library' && !project ? tree(c) : project && ['catalog', 'unused'].includes(S.view) ? kindNav() : ''}</div>
    <div class="side-foot"><button class="btn ghost sm" id="openProjects">${icon('settings')} ${t('side.projects')}</button><button class="btn ghost sm" id="langBtn" title="${t('ui.language')}">${lang() === 'en' ? 'TR' : 'EN'}</button><div class="stamps" id="stamps"></div></div>`;
  if (S.about) $('#sidebar .side-foot').insertAdjacentHTML('beforeend', `<button class="sign" title="${t('about.title')}">Artbench ${esc(S.about.version)} · ${esc(S.about.author)}</button>`);
  renderStamps();
  const sign = $('#sidebar .sign'); if (sign) sign.onclick = actions.openProjects;
  $$('#sidebar [data-copy]').forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast(t('ui.copied'), 'ok'), () => toast(b.dataset.copy)));
  $('#projSel').onchange = e => { if (e.target.value === '__manage') { e.target.value = S.project; actions.openProjects(); } else actions.switchProject(e.target.value); };
  $('#openProjects').onclick = actions.openProjects;
  $('#sideConnect').onclick = actions.openProjects;
  $('#langBtn').onclick = () => { setLang(lang() === 'en' ? 'tr' : 'en'); actions.render(); };
  $$('.nav a').forEach(a => a.onclick = () => actions.setView(a.dataset.view));
  const navMore = $('#navMore'); if (navMore) navMore.onclick = () => { prefs.set('navMore', !navMore.classList.contains('open')); renderSidebar(); };
  if (project) bindKindNav($('#sidebar'));
  $$('.tree:not(.kindnav) .node').forEach(n => n.onclick = e => {
    const t = e.target.closest('[data-toggle]');
    if (t) { S.closedCats[t.dataset.toggle] = !S.closedCats[t.dataset.toggle]; prefs.set('closedCats', S.closedCats); renderSidebar(); return; }
    S.filters.category = n.dataset.cat || null; S.filters.set = n.dataset.set || null; actions.render();
  });
  $$('.pill[data-f]').forEach(p => p.onclick = () => { const f = p.dataset.f, v = p.dataset.v; S.filters[f] = S.filters[f] === v ? null : v; actions.render(); });
  const clear = $('#clearFilters'); if (clear) clear.onclick = () => { S.filters = { state: null, usage: null, sync: null, category: null, set: null }; actions.render(); };
}

export function renderStamps() {
  const el = $('#stamps'); if (!el || !S.data) return;
  const stale = S.data.engine_scanned && (Date.now() / 1000 - S.data.engine_scanned) > 300;
  const b = S.engineStatus;
  el.innerHTML = `<span>${t('side.scan', { time: fmtTime(S.data.scanned) })}</span><span class="${stale ? 'stale' : ''}">${S.data.engine_scanned ? t('side.engine', { time: fmtTime(S.data.engine_scanned) }) : t('side.noEngineScan')}</span>`
    + (b?.bridge ? `<span>${t('side.bridge', { name: esc(b.bridge), time: fmtTime(b.last_report) })}</span>` : '');
}
