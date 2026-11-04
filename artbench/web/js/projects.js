// Projects screen: list of connected projects and the two-step connect wizard (game project -> art folder),
// plus linking an existing art folder. Full-screen overlay; shown on first run or from the project pill.
import { api } from './api.js';
import { ICONS, icon, markSvg } from './icons.js';
import { $, $$, esc, toast, modal, callout } from './ui.js';
import { S, actions } from './state.js';
import { t } from './i18n.js';

const DEFAULT_CATS = 'Characters, Props, Environment, Weapons, Blocks';
const P = { mode: 'project', engine: '', check: null, checking: false, name: '', parent: '', artName: '', cats: DEFAULT_CATS, link: '', busy: false, doctor: null, doctoring: false, mcp: null, mcpBusy: false };
const DOCTOR_CLS = { ok: 'ok', warn: 'warn', fail: 'bad', skip: 'dim' };
const safe = s => s.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'Project';

export const isProjectsOpen = () => !$('#projects').hidden;
export function openProjects() { $('#projects').hidden = false; render(); loadMcp(); }
export function closeProjects() { if (!S.project) return; $('#projects').hidden = true; $('#projects').innerHTML = ''; }

function render() {
  const el = $('#projects');
  const step1 = P.check?.ok, step2 = step1 && P.name.trim() && P.parent.trim();
  el.innerHTML = `<div class="pwrap">
    <div class="row"><div class="brand" style="padding:0">${markSvg('mark')}<div><h1>Artbench</h1><small>${t('projects.subtitle')}</small></div></div><div class="grow"></div>${S.project ? `<button class="btn" id="pClose">${icon('x')} ${t('ui.close')}</button>` : ''}</div>
    <div class="card"><div class="label" style="margin-bottom:10px">${t('projects.connected')}</div>
      ${S.projects.length ? S.projects.map(p => `<div class="projcard" style="padding-left:0;padding-right:0"><div class="pmark ${p.error ? 'err' : ''}">${icon(p.error ? 'alert' : 'cube')}</div>
        <div class="pinfo"><b>${esc(p.name || p.id)}</b><span class="mono ellip">${esc(p.config_path || '')}</span>${p.error ? `<span class="err">${esc(p.error)}</span>` : ''}</div>
        ${!p.error ? `<input type="text" class="ghfield" data-gh="${esc(p.id)}" value="${esc(p.github_account || '')}" placeholder="${t('projects.github')}" title="${t('projects.githubHint')}" spellcheck="false">` : ''}
        ${!p.error ? `<span class="chip ${p.mode === 'project' ? 'info' : 'violet'} nodot">${t('projects.modeChip.' + (p.mode || 'art'))}</span>` : ''}
        ${!p.error ? `<button class="btn ${p.id === S.project ? '' : 'primary'} sm" data-popen="${esc(p.id)}">${p.id === S.project ? t('projects.opened') : t('projects.open')}</button>` : ''}<button class="btn ghost sm danger" data-pdetach="${esc(p.id)}" title="${t('projects.detachTitle')}">${t('projects.detach')}</button></div>`).join('')
      : callout('info', t('projects.none'))}</div>
    ${mcpCard()}
    ${aboutCard()}
    ${S.project ? doctorCard() : ''}
    <div class="card">
      <div class="seg pmode"><button class="${P.mode === 'project' ? 'on' : ''}" data-pmode="project">${icon('grid')} ${t('projects.mode.project')}</button><button class="${P.mode === 'art' ? 'on' : ''}" data-pmode="art">${icon('layers')} ${t('projects.mode.art')}</button></div>
      ${P.mode === 'project' ? projectModeForm() : `<div class="steps"><div class="step ${step1 ? 'done' : 'on'}"><span class="num">${step1 ? icon('check') : '1'}</span>${t('projects.step1')}</div><div class="bar"></div><div class="step ${step2 ? 'done' : step1 ? 'on' : ''}"><span class="num">${step2 ? icon('check') : '2'}</span>${t('projects.step2')}</div><div class="bar"></div><div class="step"><span class="num">3</span>${t('projects.step3')}</div></div>
      <div class="field"><label>${t('projects.engineLabel')}</label>
        <div class="row"><input type="text" id="pEngine" placeholder="D:/Projects/MyGame/Assets/_GAME" value="${esc(P.engine)}"><button class="btn" data-pick="engine">${icon('folder')} ${t('ui.browse')}</button></div>
        ${P.checking ? callout('info', t('projects.checking')) : P.check ? callout(P.check.ok ? 'ok' : 'bad', P.check.ok ? `<b>${t('projects.unityProject')}</b> · ${esc(P.check.project_root)}<br>${t('projects.engineArtRoot')}: <span class="mono">${esc(P.check.engine_root)}</span>` : esc(P.check.message)) : ''}</div>
      <div ${step1 ? '' : 'style="opacity:.45;pointer-events:none"'}>
        <div class="field"><label>${t('projects.nameLabel')}</label><input type="text" id="pName" placeholder="${t('projects.namePlaceholder')}" value="${esc(P.name)}"></div>
        <div class="field"><label>${t('projects.parentLabel')}</label><div class="row"><input type="text" id="pParent" placeholder="C:/Users/me/Desktop" value="${esc(P.parent)}"><button class="btn" data-pick="parent">${icon('folder')} ${t('ui.browse')}</button></div></div>
        <div class="field"><label>${t('projects.artNameLabel')}</label><input type="text" id="pArt" placeholder="${esc(safe(P.name || 'MyGame'))}" value="${esc(P.artName)}"></div>
        <div class="field"><label>${t('projects.catsLabel')}</label><input type="text" id="pCats" value="${esc(P.cats)}"></div>
        <pre class="tree">${esc(previewTree())}</pre>
        <div class="row" style="margin-top:14px"><div class="grow"></div><button class="btn primary" id="pConnect" ${step2 && !P.busy ? '' : 'disabled'}>${icon('plus')} ${P.busy ? t('projects.connecting') : t('ui.connect')}</button></div></div>`}</div>
    <div class="card"><div class="label" style="margin-bottom:10px">${t('projects.linkTitle')}</div>
      <div class="field"><label>${t('projects.linkLabel')}</label><div class="row"><input type="text" id="pLink" placeholder="C:/Users/me/Desktop/MyGameArt" value="${esc(P.link)}"><button class="btn" data-pick="link">${icon('folder')} ${t('ui.browse')}</button><button class="btn" id="pLinkBtn" ${P.link.trim() ? '' : 'disabled'}>${t('ui.connect')}</button></div></div></div>
  </div>`;
  bind(el);
}

/** Project mode: only the game project; Artbench reads its art inventory and writes nothing into it. */
function projectModeForm() {
  return `<div class="muted" style="margin:10px 0 14px;font-size:12.5px">${t('projects.projectHint')}</div>
    <div class="field"><label>${t('projects.engineLabelProject')}</label>
      <div class="row"><input type="text" id="pEngine" placeholder="D:/Projects/MyGame" value="${esc(P.engine)}"><button class="btn" data-pick="engine">${icon('folder')} ${t('ui.browse')}</button></div>
      ${P.checking ? callout('info', t('projects.checking')) : P.check ? callout(P.check.ok ? 'ok' : 'bad', P.check.ok ? `<b>${t('projects.unityProject')}</b> · ${esc(P.check.project_root)}` : esc(P.check.message)) : ''}</div>
    <div class="field"><label>${t('projects.nameLabel')}</label><input type="text" id="pName" placeholder="${t('projects.namePlaceholder')}" value="${esc(P.name)}"></div>
    <div class="row" style="margin-top:14px"><div class="grow"></div><button class="btn primary" id="pConnectProject" ${P.check?.ok && !P.busy ? '' : 'disabled'}>${icon('plus')} ${P.busy ? t('projects.connecting') : t('ui.connect')}</button></div>`;
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
  const close = $('#pClose'); if (close) close.onclick = closeProjects;
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
  $$('[data-pmode]', el).forEach(b => b.onclick = () => { P.mode = b.dataset.pmode; render(); });
  const eng = $('#pEngine'); eng.onchange = () => { P.engine = eng.value; check(); };
  if (P.mode === 'project') {
    $('#pName').oninput = ev => { P.name = ev.target.value; };
    $('#pConnectProject').onclick = connectProject;
  } else {
    $('#pName').oninput = ev => { P.name = ev.target.value; $('#pArt').placeholder = safe(P.name || 'MyGame'); $('.tree', el).textContent = previewTree(); $('#pConnect').disabled = !(P.check?.ok && P.name.trim() && P.parent.trim()); };
    $('#pParent').onchange = ev => { P.parent = ev.target.value; $('#pConnect').disabled = !(P.check?.ok && P.name.trim() && P.parent.trim()); };
    $('#pArt').oninput = ev => { P.artName = ev.target.value; $('.tree', el).textContent = previewTree(); };
    $('#pCats').oninput = ev => { P.cats = ev.target.value; $('.tree', el).textContent = previewTree(); };
    $('#pConnect').onclick = connect;
  }
  $('#pLink').oninput = ev => { P.link = ev.target.value; $('#pLinkBtn').disabled = !P.link.trim(); };
  $$('[data-pick]', el).forEach(b => b.onclick = async () => {
    const which = b.dataset.pick;
    try {
      const r = await api.post('/api/pick_folder', { title: { engine: t('projects.pickEngine'), parent: t('projects.pickParent'), link: t('projects.pickLink') }[which], initial: P[which === 'parent' ? 'parent' : which === 'link' ? 'link' : 'engine'] || null });
      if (!r.path) return;
      P[which === 'parent' ? 'parent' : which === 'link' ? 'link' : 'engine'] = r.path;
      if (which === 'engine') await check(); else render();
    } catch (e) { toast(e.message); }
  });
  const doc = $('#doctorBtn'); if (doc) doc.onclick = runDoctor;
  const add = $('#mcpAdd'); if (add) add.onclick = addToClaude;
  $$('.mcp [data-copy]', el).forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast(t('ui.copied'), 'ok'), () => toast(b.dataset.copy)));
  $('#pLinkBtn').onclick = link;
}

async function check() {
  P.checking = true; P.check = null; render();
  try { P.check = await api.get('/api/projects/check', { engine_root: P.engine }); }
  catch (e) { P.check = { ok: false, message: e.message }; }
  P.checking = false;
  if (P.check.ok && !P.name) P.name = P.check.project_root.split(/[\\/]/).pop() || '';
  render();
}

async function connect() {
  P.busy = true; render();
  try {
    const r = await api.post('/api/projects/connect', { name: P.name.trim(), engine_root: P.engine, art_parent: P.parent, art_name: P.artName.trim() || null, categories: P.cats.split(',').map(s => s.trim()).filter(Boolean) });
    toast(t('projects.connectedToast', { root: r.art_root }), 'ok');
    await actions.loadProjects(); actions.switchProject(r.id); Object.assign(P, { engine: '', check: null, name: '', parent: '', artName: '' }); closeProjects();
  } catch (e) { toast(e.message); }
  finally { P.busy = false; if (isProjectsOpen()) render(); }
}

async function connectProject() {
  P.busy = true; render();
  try {
    const r = await api.post('/api/projects/connect_project', { engine_path: P.engine, name: P.name.trim() || null });
    toast(t('projects.connectedProjectToast', { id: r.id }), 'ok');
    await actions.loadProjects(); actions.switchProject(r.id); Object.assign(P, { engine: '', check: null, name: '' }); closeProjects();
  } catch (e) { toast(e.message); }
  finally { P.busy = false; if (isProjectsOpen()) render(); }
}

async function link() {
  try {
    const r = await api.post('/api/projects/link', { path: P.link.trim() });
    toast(t('projects.connectedToast', { root: r.art_root }), 'ok'); P.link = '';
    await actions.loadProjects(); actions.switchProject(r.id); closeProjects();
  } catch (e) { toast(e.message); }
}
