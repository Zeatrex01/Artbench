// Projects screen, a hub: connecting comes first (pick the Unity project, choose the game project alone or with an art
// folder), then the connected projects as cards, then the AI connection, the machine check and who made Artbench.
// While a connect runs, the connect area shows its progress stage by stage (/api/projects/progress), with counts and
// the file being read, and opens the catalog when it is ready. Full-screen overlay; shown on first run, from the
// sidebar's Connect button or the project pill.
import { api } from './api.js';
import { icon, markSvg } from './icons.js';
import { $, $$, esc, toast, modal, callout } from './ui.js';
import { S, actions } from './state.js';
import { t, locale } from './i18n.js';

const DEFAULT_CATS = 'Characters, Props, Environment, Weapons, Blocks';
const P = { mode: 'project', engine: '', check: null, checking: false, name: '', parent: '', artName: '', cats: DEFAULT_CATS, link: '', busy: false, doctor: null, doctoring: false, mcp: null, mcpBusy: false, run: null };
const DOCTOR_CLS = { ok: 'ok', warn: 'warn', fail: 'bad', skip: 'dim' };
const safe = s => s.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'Project';

export const isProjectsOpen = () => !$('#projects').hidden;
export function openProjects() { $('#projects').hidden = false; render(); loadMcp(); }
export function closeProjects() { if (!S.project || P.run) return; $('#projects').hidden = true; $('#projects').innerHTML = ''; }

function render() {
  const el = $('#projects');
  const mine = S.projects.length;
  el.innerHTML = `<div class="pwrap">
    <header class="phead"><div class="brand" style="padding:0">${markSvg('mark')}<div><h1>Artbench</h1><small>${t('projects.subtitle')}</small></div></div><div class="grow"></div>${S.project && !P.run ? `<button class="btn" id="pClose">${icon('x')} ${t('ui.close')}</button>` : ''}</header>
    <section class="card connect" data-part="connect">${P.run ? progressView() : connectForm()}</section>
    <section class="mine" data-part="projects"><div class="label">${t('projects.connected')}${mine ? ` <span class="cnt">${mine}</span>` : ''}</div>
      ${mine ? `<div class="pgrid">${S.projects.map(projectCard).join('')}</div>` : callout('info', t('projects.none'))}</section>
    <section class="more" data-part="more"><div class="pcols">${mcpCard()}${S.project ? doctorCard() : aboutCard()}</div>${S.project ? aboutCard() : ''}</section>
  </div>`;
  bind(el);
  if (P.run) paint();
}

/** One connected project: its name, where it lives, what kind it is, its GitHub account, Open and Detach. */
function projectCard(p) {
  const here = p.id === S.project;
  return `<div class="card projcard ${here ? 'here' : ''}"><div class="pmark ${p.error ? 'err' : ''}">${icon(p.error ? 'alert' : p.mode === 'project' ? 'grid' : 'layers')}</div>
    <div class="pinfo"><b>${esc(p.name || p.id)}</b><span class="mono ellip" title="${esc(p.config_path || '')}">${esc(p.config_path || '')}</span>${p.error ? `<span class="err">${esc(p.error)}</span>` : ''}
      ${!p.error ? `<div class="prow"><span class="chip ${p.mode === 'project' ? 'info' : 'violet'} nodot">${t('projects.modeChip.' + (p.mode || 'art'))}</span><input type="text" class="ghfield" data-gh="${esc(p.id)}" value="${esc(p.github_account || '')}" placeholder="${t('projects.github')}" title="${t('projects.githubHint')}" spellcheck="false"></div>` : ''}</div>
    <div class="pact">${!p.error ? `<button class="btn ${here ? '' : 'primary'} sm" data-popen="${esc(p.id)}">${here ? t('projects.opened') : t('projects.open')}</button>` : ''}<button class="btn ghost sm danger" data-pdetach="${esc(p.id)}" title="${t('projects.detachTitle')}">${t('projects.detach')}</button></div></div>`;
}

/** The connect area: the Unity project folder first, then the two ways to connect it. */
function connectForm() {
  const ok = P.check?.ok, art = P.mode === 'art';
  const ready = ok && (!art || (P.name.trim() && P.parent.trim()));
  const tile = (mode, ic) => `<button class="ptile ${P.mode === mode ? 'on' : ''}" data-pmode="${mode}" aria-pressed="${P.mode === mode}">${icon(ic)}<b>${t('projects.mode.' + mode)}</b><span>${t('hub.mode.' + mode)}</span></button>`;
  return `<div class="chead"><h2>${t('hub.title')}</h2><p>${t('projects.projectHint')}</p></div>
    <div class="pick ${ok ? 'ok' : ''}"><div class="pick-ic">${icon(ok ? 'check' : 'folder')}</div><div class="pick-body">
      <label for="pEngine">${t(art ? 'projects.engineLabel' : 'projects.engineLabelProject')}</label>
      <div class="row"><input type="text" id="pEngine" placeholder="${art ? 'D:/Projects/MyGame/Assets/_GAME' : 'D:/Projects/MyGame'}" value="${esc(P.engine)}"><button class="btn" data-pick="engine">${icon('folder')} ${t('ui.browse')}</button></div>
      ${P.checking ? `<div class="pick-note">${t('projects.checking')}</div>` : P.check ? `<div class="pick-note ${ok ? 'ok' : 'bad'}">${ok ? `<b>${t('projects.unityProject')}</b> · <span class="mono">${esc(P.check.project_root)}</span>` : esc(P.check.message)}</div>` : ''}</div></div>
    <div class="ptiles">${tile('project', 'grid')}${tile('art', 'layers')}</div>
    <div class="pfields">
      <div class="field"><label>${t('projects.nameLabel')}</label><input type="text" id="pName" placeholder="${t('projects.namePlaceholder')}" value="${esc(P.name)}"></div>
      ${art ? `<div class="field"><label>${t('projects.parentLabel')}</label><div class="row"><input type="text" id="pParent" placeholder="C:/Users/me/Desktop" value="${esc(P.parent)}"><button class="btn" data-pick="parent">${icon('folder')} ${t('ui.browse')}</button></div></div>
      <div class="pair"><div class="field"><label>${t('projects.artNameLabel')}</label><input type="text" id="pArt" placeholder="${esc(safe(P.name || 'MyGame'))}" value="${esc(P.artName)}"></div>
        <div class="field"><label>${t('projects.catsLabel')}</label><input type="text" id="pCats" value="${esc(P.cats)}"></div></div>
      <pre class="tree">${esc(previewTree())}</pre>` : ''}
    </div>
    <div class="cgo"><button class="btn primary lg" id="${art ? 'pConnect' : 'pConnectProject'}" ${ready ? '' : 'disabled'}>${icon('plus')} ${t('hub.connect')}</button></div>
    <details class="plink" ${P.link ? 'open' : ''}><summary>${t('projects.linkTitle')}</summary>
      <div class="field"><label>${t('projects.linkLabel')}</label><div class="row"><input type="text" id="pLink" placeholder="C:/Users/me/Desktop/MyGameArt" value="${esc(P.link)}"><button class="btn" data-pick="link">${icon('folder')} ${t('ui.browse')}</button><button class="btn" id="pLinkBtn" ${P.link.trim() ? '' : 'disabled'}>${t('ui.connect')}</button></div></div></details>`;
}

// --- a connect in progress: the server's stages, shown one after another at a pace a person can follow ---------------
const STAGES = ['check', 'files', 'meta', 'refs', 'settings', 'open'];
const WEIGHT = { check: 4, files: 8, meta: 36, refs: 36, settings: 4, open: 12 };
const MIN_STAGE_MS = 320;                                   // a quick stage still shows, so the steps read one by one
const num = n => Math.round(n).toLocaleString(locale());

function progressView() {
  return `<div class="cprog" data-pct="0"><div class="chead"><h2>${t('hub.connecting', { name: esc(P.run.name) })}</h2><span class="celapsed mono">0 s</span></div>
    <div class="cbar"><i></i></div>
    <ol class="cstages">${STAGES.map(st => `<li class="cstage" data-stage="${st}"><span class="cdot">${icon('check')}</span><b>${t('hub.stage.' + st)}</b><span class="ccount"></span><span class="cmini"><i></i></span></li>`).join('')}</ol>
    <div class="ccur mono ellip"></div><div class="cerr"></div></div>`;
}

/** What the server has reached for a stage: {done, total, finished}. The page's own last stage is opening the catalog. */
function reached(st) {
  const r = P.run, rec = r.record || {};
  if (st === 'open') return { done: r.opened ? 1 : 0, total: 1, finished: r.opened };
  const stages = rec.stages || [], i = stages.findIndex(s => s.id === st), s = stages[i];
  const finished = !!s && (i < stages.length - 1 || rec.state === 'done');
  return { done: s?.done || 0, total: s?.total || 0, finished: finished || (rec.state === 'done' && r.answered) };
}

/** One frame: the shown stage moves on only when the server has passed it and it has been on screen a moment;
 * counts and the bar ease toward what was reached, so nothing jumps. */
function tick(now) {
  const r = P.run;
  if (!r || !isProjectsOpen()) return;
  const dt = Math.min(.1, (now - (r.last || now)) / 1000); r.last = now;
  let st = STAGES[r.at];
  const got = reached(st);
  r.shown += (got.done - r.shown) * Math.min(1, dt * 9) + (got.done > r.shown ? .5 : 0);
  if (r.shown > got.done) r.shown = got.done;
  if (got.finished && now - r.since >= MIN_STAGE_MS && r.shown >= got.done - .5 && r.at < STAGES.length - 1) {
    r.counts[st] = got; r.at += 1; r.since = now; r.shown = 0; st = STAGES[r.at];
  } else if (got.finished && st === 'open' && now - r.since >= MIN_STAGE_MS) r.complete = true;
  const frac = got.total ? Math.min(1, r.shown / got.total) : got.finished ? 1 : 0;
  const goal = STAGES.slice(0, r.at).reduce((a, s) => a + WEIGHT[s], 0) + WEIGHT[st] * frac;
  r.pct = Math.max(r.pct, r.pct + (goal - r.pct) * Math.min(1, dt * 6));
  paint();
  if (r.complete && !r.closing) { r.closing = true; setTimeout(finishRun, 350); }
  if (!r.failed) requestAnimationFrame(tick);
}

function paint() {
  const r = P.run, box = $('#projects .cprog');
  if (!r || !box) return;
  box.dataset.pct = Math.round(r.pct);
  box.querySelector('.cbar i').style.width = `${r.pct.toFixed(1)}%`;
  box.querySelector('.celapsed').textContent = `${((performance.now() - r.t0) / 1000).toFixed(1)} s`;
  STAGES.forEach((st, i) => {
    const li = box.querySelector(`[data-stage="${st}"]`), on = i === r.at && !r.complete;
    li.classList.toggle('done', i < r.at || (r.complete && i === r.at));
    li.classList.toggle('on', on);
    li.classList.toggle('bad', !!r.failed && i === r.at);
    const c = i < r.at ? r.counts[st] : on ? { done: r.shown, total: reached(st).total } : null;
    li.querySelector('.ccount').textContent = c ? countText(st, c) : '';
    li.querySelector('.cmini i').style.width = on && c?.total ? `${Math.min(100, c.done / c.total * 100)}%` : '0';
  });
  box.querySelector('.ccur').textContent = r.failed ? '' : r.at === STAGES.indexOf('open') ? r.name : (r.files[STAGES[r.at]] || '');
}

function countText(st, c) {
  if (st === 'files') return t('hub.files', { n: num(c.done) });
  if (st === 'meta' || st === 'refs') return `${num(c.done)} / ${num(c.total)}`;
  return '';
}

/** Runs one connect call with its progress: polls the server's record while the call is out, then opens the project. */
async function runConnect(name, call) {
  P.run = { name: name || '…', t0: performance.now(), since: performance.now(), at: 0, shown: 0, pct: 0, counts: {}, files: {}, record: null, answered: false, opened: false };
  const run = P.run;
  render();
  requestAnimationFrame(tick);
  const poll = async () => {
    while (P.run === run && !run.answered) {
      try {
        const rec = await api.get('/api/projects/progress');
        if (rec.state === 'running') run.seenRunning = true;
        if (run.seenRunning && !run.answered) {                   // an older connect's record is not this one's
          run.record = rec;
          if (rec.stage) run.files[rec.stage] = rec.current;      // the file line follows the stage on screen, not the server
        }
      } catch (e) { /* the call itself reports errors */ }
      await new Promise(res => setTimeout(res, 150));
    }
  };
  poll();
  try {
    const r = await call();
    run.record = await api.get('/api/projects/progress').catch(() => run.record);
    run.answered = true;
    run.name = run.record?.name || run.name;
    await actions.loadProjects();
    actions.switchProject(r.id);
    for (let waited = 0; !S.data && P.run === run && waited < 60000; waited += 100) await new Promise(res => setTimeout(res, 100));   // the catalog's first state
    run.opened = true;
    run.toast = r.art_root ? t('projects.connectedToast', { root: r.art_root }) : t('projects.connectedProjectToast', { id: r.id });
  } catch (e) {
    run.answered = true; run.failed = true;
    const box = $('#projects .cprog .cerr');
    if (box) box.innerHTML = `${callout('bad', esc(e.message))}<div class="row"><div class="grow"></div><button class="btn" id="pBack">${t('hub.back')}</button></div>`;
    paint();
    const back = $('#pBack'); if (back) back.onclick = () => { P.run = null; render(); };
  }
}

function finishRun() {
  const r = P.run;
  if (!r) return;
  P.run = null;
  Object.assign(P, { engine: '', check: null, name: '', parent: '', artName: '', link: '' });
  closeProjects();
  if (r.toast) toast(r.toast, 'ok');
}

/** Who made Artbench, which version this is, and what its licence lets you do. */
function aboutCard() {
  const a = S.about || {};
  return `<div class="card about"><div class="row">${markSvg('mark')}<div><b>Artbench ${esc(a.version || '')}</b>
    <div class="muted">${t('about.by', { author: esc(a.author || '') })}</div></div></div><p class="muted">${t('about.terms')}</p></div>`;
}

/** "AI connection": which AI tools start this Artbench's MCP server; Claude Code is added with one click, the others get
 * the line to paste. Machine-wide, so it shows with or without a project. */
const MCP_CHIP = { here: ['ok', 'mcp.here'], elsewhere: ['warn', 'mcp.elsewhere'], unknown: ['dim', 'mcp.unknown'] };
function mcpCard() {
  const st = P.mcp;
  const rows = (st?.tools || []).map(x => {
    const [cls, key] = MCP_CHIP[x.state] || ['dim', x.installed ? 'mcp.missing' : 'mcp.notInstalled'];
    let action = '';
    if (x.state !== 'here') {
      action = x.tool === 'claude' && x.installed
        ? `<button class="btn sm primary" id="mcpAdd" ${P.mcpBusy ? 'disabled' : ''}>${P.mcpBusy ? t('mcp.adding') : t(x.state === 'elsewhere' ? 'mcp.update' : 'mcp.add')}</button>`
        : `<button class="btn sm" data-copy="${esc(st.lines?.[x.tool] || '')}" title="${t('mcp.copyTitle')}">${icon('copy')} ${t('ui.copy')}</button>`;
    }
    return `<div class="check-row" data-tool="${esc(x.tool)}" data-state="${esc(x.state)}"><span class="chip ${cls}" ${x.state === 'elsewhere' ? `title="${t('mcp.elsewhereTitle')}"` : ''}>${t(key)}</span><b>${esc(x.name)}</b><span class="mcp-act">${action}</span></div>`;
  }).join('');
  return `<div class="card mcp"><div class="label">${t('mcp.title')}</div>
    <div class="muted" style="font-size:12px;margin:6px 0">${t('mcp.hint')}</div>
    ${st?.error ? callout('bad', esc(st.error)) : rows ? `<div class="checks-list">${rows}</div>` : `<div class="muted" style="font-size:12px">${t('cat.loading')}</div>`}
    <div class="muted" style="font-size:12px;margin-top:10px">${t('mcp.example')}</div></div>`;
}

async function loadMcp() {
  try { P.mcp = await api.get('/api/mcp'); } catch (e) { P.mcp = { error: e.message }; }
  if (isProjectsOpen()) render();
}

async function addToClaude() {
  P.mcpBusy = true; render();
  try {
    const r = await api.post('/api/mcp/register', { tool: 'claude' });
    const ok = ['registered', 'updated', 'already'].includes(r.result);
    toast(r.result === 'already' ? t('mcp.already') : ok ? t('mcp.added') : r.message, ok ? 'ok' : undefined);
  } catch (e) { toast(e.message); }
  finally { P.mcpBusy = false; await loadMcp(); }
}

/** "Check this machine": the doctor's checks for the open project (the Windows trial starts here). */
function doctorCard() {
  const d = P.doctor?.project === S.project ? P.doctor : null;      // results belong to the project they ran for
  const rows = d?.checks?.map(c => `<div class="check-row" data-check="${esc(c.id)}" data-status="${esc(c.status)}">
      <span class="chip ${DOCTOR_CLS[c.status] || 'dim'} nodot">${t('doctor.' + c.status)}</span><b>${esc(t('doctor.check.' + c.id))}</b><span class="muted ellip" title="${esc(c.detail)}">${esc(c.detail)}</span></div>`).join('') || '';
  return `<div class="card doctor"><div class="row"><div class="label">${t('doctor.title')}</div><div class="grow"></div>
      <button class="btn sm" id="doctorBtn" ${P.doctoring ? 'disabled' : ''}>${icon('activity')} ${P.doctoring ? t('doctor.running') : t('doctor.run')}</button></div>
    <div class="muted" style="font-size:12px;margin:6px 0">${t('doctor.hint')}</div>
    ${d?.error ? callout('bad', esc(d.error)) : ''}${rows ? `<div class="checks-list">${rows}</div>` : ''}</div>`;
}

async function runDoctor() {
  const project = S.project;
  P.doctoring = true; render();
  try { P.doctor = { project, ...(await api.post('/api/v1/doctor', { project })).result }; }
  catch (err) { P.doctor = { project, error: err.message }; }
  finally { P.doctoring = false; render(); }
}

function previewTree() {
  const art = P.artName.trim() || safe(P.name || 'MyGame');
  const cats = P.cats.split(',').map(s => s.trim()).filter(Boolean);
  return `${art}/\n├─ FBX/${cats.length ? `          ${cats.join(', ')}/` : ''}\n├─ Outbox/\n├─ Stock/\n├─ _Archive/\n├─ Blend/${cats.length ? `        ${cats.join(', ')}/` : ''}\n├─ Textures/\n├─ README.md\n└─ art_inventory.json`;
}

function bind(el) {
  const on = (sel, ev, fn) => { const n = $(sel, el); if (n) n[ev] = fn; };
  on('#pClose', 'onclick', closeProjects);
  $$('[data-popen]', el).forEach(b => b.onclick = () => { actions.switchProject(b.dataset.popen); closeProjects(); });
  $$('[data-gh]', el).forEach(f => {
    const save = async () => {
      try {
        await api.post('/api/projects/github', { project: f.dataset.gh, account: f.value });
        toast(t('projects.githubSaved'), 'ok');
        await actions.loadProjects();
        if (f.dataset.gh === S.project) actions.refresh();
      } catch (e) { toast(e.message); }
    };
    f.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); f.blur(); } };
    f.onchange = save;
  });
  $$('[data-pdetach]', el).forEach(b => b.onclick = async () => {
    const ok = await modal({ title: t('projects.detachDialogTitle'), body: t('projects.detachDialogBody'), ok: t('projects.detach'), danger: true });
    if (!ok) return;
    try { await api.post('/api/projects/detach', { id: b.dataset.pdetach }); await actions.loadProjects(); render(); toast(t('projects.detached'), 'ok'); } catch (e) { toast(e.message); }
  });
  const doc = $('#doctorBtn'); if (doc) doc.onclick = runDoctor;
  const add = $('#mcpAdd'); if (add) add.onclick = addToClaude;
  $$('.mcp [data-copy]', el).forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast(t('ui.copied'), 'ok'), () => toast(b.dataset.copy)));
  if (P.run) return;                                         // the connect area shows the progress, not the form
  const ready = () => {
    const b = $('#pConnect') || $('#pConnectProject');
    if (b) b.disabled = !(P.check?.ok && (P.mode !== 'art' || (P.name.trim() && P.parent.trim())));
  };
  $$('[data-pmode]', el).forEach(b => b.onclick = () => { P.mode = b.dataset.pmode; render(); });
  on('#pEngine', 'onchange', ev => { P.engine = ev.target.value; check(); });
  on('#pName', 'oninput', ev => {
    P.name = ev.target.value;
    const art = $('#pArt', el); if (art) art.placeholder = safe(P.name || 'MyGame');
    const tree = $('.tree', el); if (tree) tree.textContent = previewTree();
    ready();
  });
  on('#pParent', 'onchange', ev => { P.parent = ev.target.value; ready(); });
  on('#pArt', 'oninput', ev => { P.artName = ev.target.value; $('.tree', el).textContent = previewTree(); });
  on('#pCats', 'oninput', ev => { P.cats = ev.target.value; $('.tree', el).textContent = previewTree(); });
  on('#pConnect', 'onclick', connect);
  on('#pConnectProject', 'onclick', connectProject);
  on('#pLink', 'oninput', ev => { P.link = ev.target.value; $('#pLinkBtn').disabled = !P.link.trim(); });
  on('#pLinkBtn', 'onclick', link);
  $$('[data-pick]', el).forEach(b => b.onclick = async () => {
    const which = b.dataset.pick;
    try {
      const r = await api.post('/api/pick_folder', { title: { engine: t('projects.pickEngine'), parent: t('projects.pickParent'), link: t('projects.pickLink') }[which], initial: P[which] || null });
      if (!r.path) return;
      P[which] = r.path;
      if (which === 'engine') await check(); else render();
    } catch (e) { toast(e.message); }
  });
}

async function check() {
  P.checking = true; P.check = null; render();
  try { P.check = await api.get('/api/projects/check', { engine_root: P.engine }); }
  catch (e) { P.check = { ok: false, message: e.message }; }
  P.checking = false;
  if (P.check.ok && !P.name) P.name = P.check.project_root.split(/[\\/]/).pop() || '';
  render();
}

const connect = () => runConnect(P.name.trim(), () => api.post('/api/projects/connect', { name: P.name.trim(), engine_root: P.engine, art_parent: P.parent, art_name: P.artName.trim() || null, categories: P.cats.split(',').map(s => s.trim()).filter(Boolean) }));
const connectProject = () => runConnect(P.name.trim() || P.check?.project_root.split(/[\\/]/).pop(), () => api.post('/api/projects/connect_project', { engine_path: P.engine, name: P.name.trim() || null }));
const link = () => runConnect(P.link.trim().split(/[\\/]/).filter(Boolean).pop(), () => api.post('/api/projects/link', { path: P.link.trim() }));
