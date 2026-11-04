// Reference graph on a canvas: focus node + 2 hops (or every unused asset), force layout, kind colours,
// arrows referrer -> referenced, dashed ring = unused, white dot = has desktop copy, thumbnails inside model nodes.
import { api } from './api.js';
import { t } from './i18n.js';
import { icon } from './icons.js';
import { $, $$, esc, toast, emptyState } from './ui.js';
import { thumbImage } from './thumbs.js';
import { S, KIND, actions, enginePathAbs } from './state.js';

const MAX_NODES = 160, HOPS = 2, DENSE = 40, UNUSED_KINDS = new Set(['model', 'mesh', 'texture', 'material']);
const G = { nodes: [], edges: [], byId: new Map(), pos: new Map(), vel: new Map(), images: new Map(), mode: 'hood', query: '',
  zoom: 1, panX: 0, panY: 0, hover: null, raf: 0, heat: 0, canvas: null, ctx: null, ro: null };

export function viewGraph() {
  return `<div class="graphwrap">
    <div class="card gside"><div class="search" style="width:auto">${icon('search')}<input type="text" id="gq" placeholder="${t('graph.search')}" value="${esc(G.query)}"></div>
      <div class="seg"><button class="${G.mode === 'hood' ? 'on' : ''}" data-gmode="hood">${t('graph.hood')}</button><button class="${G.mode === 'unused' ? 'on' : ''}" data-gmode="unused">${t('graph.unused')}</button></div>
      <div class="results" id="gres"></div><div class="dim" style="font-size:11px" id="gcount"></div></div>
    <div class="card gcanvas" id="gc"><canvas id="gcv"></canvas><div class="legend" id="glegend"></div><div class="gtip" id="gtip"></div>
      <div class="ghint">${t('graph.hint')}</div></div></div>`;
}

export async function initGraph() {
  if (!S.graph) {
    try { S.graph = await api.get('/api/graph', { project: S.project }); } catch (e) { toast(e.message); return; }
    if (S.view !== 'graph') return;
  }
  G.byId = new Map(S.graph.nodes.map(n => [n.id, n]));
  G.out = new Map(); G.in = new Map();
  for (const e of S.graph.edges) { (G.out.get(e.from) || G.out.set(e.from, []).get(e.from)).push(e.to); (G.in.get(e.to) || G.in.set(e.to, []).get(e.to)).push(e.from); }
  if (!S.graphFocus || !G.byId.has(S.graphFocus)) S.graphFocus = defaultFocus();
  $('#gq').oninput = ev => { G.query = ev.target.value; renderResults(); };
  $$('[data-gmode]').forEach(b => b.onclick = () => { G.mode = b.dataset.gmode; $$('[data-gmode]').forEach(x => x.classList.toggle('on', x === b)); build(); });
  renderResults(); renderLegend(); setupCanvas(); build();
}

function defaultFocus() {
  const models = S.graph.nodes.filter(n => n.inside && n.kind === 'model');
  return (models.sort((a, b) => b.in - a.in)[0] || S.graph.nodes[0])?.id || null;
}

function renderResults() {
  const q = G.query.toLowerCase().trim();
  const list = S.graph.nodes.filter(n => n.inside && (!q || n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)))
    .sort((a, b) => (b.in + b.out) - (a.in + a.out)).slice(0, 80);
  $('#gres').innerHTML = list.map(n => `<div class="gres ${n.id === S.graphFocus ? 'on' : ''}" data-gid="${esc(n.id)}" title="${esc(n.id)}"><span class="k" style="background:${color(n)}"></span><span class="ellip">${esc(n.name)}</span><span class="n">${n.in}↙ ${n.out}↗</span></div>`).join('') || emptyState('search', t('graph.noMatch'));
  $$('.gres').forEach(r => r.onclick = () => focus(r.dataset.gid));
  $('#gcount').textContent = t('graph.count', { nodes: S.graph.nodes.length, edges: S.graph.edges.length });
}
function renderLegend() {
  const kinds = [...new Set(S.graph.nodes.map(n => n.kind))].filter(k => KIND[k]);
  $('#glegend').innerHTML = kinds.map(k => `<span class="chip nodot" style="color:${KIND[k].color}">${KIND[k].label}</span>`).join('');
}
const color = n => KIND[n.kind]?.color || KIND.other.color;

function focus(id) { S.graphFocus = id; G.mode = 'hood'; $$('[data-gmode]').forEach(x => x.classList.toggle('on', x.dataset.gmode === 'hood')); renderResults(); build(); }

/** Picks the visible subgraph and seeds the layout. */
function build() {
  let ids = new Set();
  if (G.mode === 'unused') {
    S.graph.nodes.filter(n => n.inside && n.in === 0 && UNUSED_KINDS.has(n.kind)).slice(0, MAX_NODES).forEach(n => ids.add(n.id));
  } else if (S.graphFocus) {
    ids.add(S.graphFocus);
    let frontier = [S.graphFocus];
    for (let h = 0; h < HOPS && ids.size < MAX_NODES; h++) {
      if (h > 0 && ids.size > DENSE) break;              // a busy hub gets one hop only, the picture stays readable
      const next = [];
      for (const id of frontier) for (const nb of [...(G.out.get(id) || []), ...(G.in.get(id) || [])]) if (!ids.has(nb) && ids.size < MAX_NODES) { ids.add(nb); next.push(nb); }
      frontier = next;
    }
  }
  G.nodes = [...ids].map(id => G.byId.get(id)).filter(Boolean);
  G.edges = S.graph.edges.filter(e => ids.has(e.from) && ids.has(e.to));
  const w = G.canvas?.clientWidth || 800, h = G.canvas?.clientHeight || 600;
  const kept = new Map();
  G.nodes.forEach((n, i) => {
    const p = G.pos.get(n.id); const a = (i / Math.max(1, G.nodes.length)) * Math.PI * 2, r = Math.min(w, h) * 0.32;
    kept.set(n.id, p || { x: w / 2 + Math.cos(a) * r + (Math.random() - .5) * 40, y: h / 2 + Math.sin(a) * r + (Math.random() - .5) * 40 });
    if (n.id === S.graphFocus && G.mode === 'hood') kept.set(n.id, { x: w / 2, y: h / 2 });
  });
  G.pos = kept; G.vel = new Map(G.nodes.map(n => [n.id, { x: 0, y: 0 }]));
  G.zoom = 1; G.panX = 0; G.panY = 0; G.heat = 1;
  for (const n of G.nodes) if (n.kind === 'model' && !G.images.has(n.id)) { G.images.set(n.id, null); thumbImage(enginePathAbs(n.id)).then(img => { G.images.set(n.id, img); }); }
  loop();
}

function radius(n) { return n.id === S.graphFocus ? 26 : n.kind === 'model' ? 20 : 8 + Math.min(10, Math.sqrt(n.in + n.out) * 2); }

function tick() {
  const w = G.canvas.clientWidth, h = G.canvas.clientHeight, ns = G.nodes, k = 0.015 * G.heat;
  for (let i = 0; i < ns.length; i++) {
    const a = G.pos.get(ns[i].id), va = G.vel.get(ns[i].id);
    for (let j = i + 1; j < ns.length; j++) {
      const b = G.pos.get(ns[j].id), vb = G.vel.get(ns[j].id);
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
      const f = Math.min(8, 2600 / d2) * G.heat; dx /= d; dy /= d;
      va.x += dx * f; va.y += dy * f; vb.x -= dx * f; vb.y -= dy * f;
    }
    va.x += (w / 2 - a.x) * k * 0.6; va.y += (h / 2 - a.y) * k * 0.6;
  }
  for (const e of G.edges) {
    const a = G.pos.get(e.from), b = G.pos.get(e.to), va = G.vel.get(e.from), vb = G.vel.get(e.to);
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) + 0.01, f = (d - 90) * 0.02 * G.heat;
    va.x += dx / d * f; va.y += dy / d * f; vb.x -= dx / d * f; vb.y -= dy / d * f;
  }
  for (const n of ns) {
    const p = G.pos.get(n.id), v = G.vel.get(n.id);
    if (n.id === S.graphFocus && G.mode === 'hood') { v.x = v.y = 0; continue; }
    v.x *= 0.82; v.y *= 0.82; p.x += v.x; p.y += v.y;
  }
  G.heat = Math.max(0, G.heat - 0.004);
}

function draw() {
  const c = G.canvas, ctx = G.ctx, dpr = devicePixelRatio || 1;
  if (c.width !== c.clientWidth * dpr || c.height !== c.clientHeight * dpr) { c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, c.clientWidth, c.clientHeight);
  ctx.translate(G.panX, G.panY); ctx.scale(G.zoom, G.zoom);
  if (!G.nodes.length) { ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = '#646c7a'; ctx.font = '13px Inter, system-ui'; ctx.textAlign = 'center'; ctx.fillText(G.mode === 'unused' ? t('graph.noUnused') : t('graph.pick'), c.clientWidth / 2, c.clientHeight / 2); return; }
  ctx.lineWidth = 1;
  for (const e of G.edges) {
    const a = G.pos.get(e.from), b = G.pos.get(e.to), hot = G.hover && (e.from === G.hover || e.to === G.hover);
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / d, uy = dy / d, rb = radius(G.byId.get(e.to)) + 3;
    const ex = b.x - ux * rb, ey = b.y - uy * rb;
    ctx.strokeStyle = hot ? 'rgba(135,147,255,.9)' : 'rgba(255,255,255,.14)'; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(ex, ey); ctx.stroke();
    ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - ux * 7 - uy * 3.5, ey - uy * 7 + ux * 3.5); ctx.lineTo(ex - ux * 7 + uy * 3.5, ey - uy * 7 - ux * 3.5); ctx.closePath(); ctx.fill();
  }
  ctx.font = '11px Inter, system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  for (const n of G.nodes) {
    const p = G.pos.get(n.id), r = radius(n), col = color(n), img = G.images.get(n.id);
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fillStyle = img ? '#1a1e26' : col + (n.id === G.hover || n.id === S.graphFocus ? 'ff' : 'cc'); ctx.fill();
    if (img) { ctx.save(); ctx.clip(); const s = r * 1.9; ctx.drawImage(img, p.x - s / 2, p.y - s / 2, s, s); ctx.restore(); ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.stroke(); }
    if (n.inside && n.in === 0 && UNUSED_KINDS.has(n.kind)) { ctx.setLineDash([3, 3]); ctx.strokeStyle = '#f5b942'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(p.x, p.y, r + 4, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]); }
    if (n.id === S.graphFocus) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, r + 2, 0, Math.PI * 2); ctx.stroke(); }
    if (n.desktop_id) { ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(p.x + r * 0.72, p.y - r * 0.72, 3.5, 0, Math.PI * 2); ctx.fill(); }
    const dense = G.nodes.length > 60;
    if (n.id === G.hover || n.id === S.graphFocus || G.zoom > 1.4 || (!dense && r >= 12)) { ctx.fillStyle = n.id === G.hover ? '#fff' : '#9aa3b2'; ctx.fillText(n.name.length > 26 ? n.name.slice(0, 24) + '…' : n.name, p.x, p.y + r + 5); }
  }
}

function loop() {
  cancelAnimationFrame(G.raf);
  const step = () => { if (!G.canvas?.isConnected) return; if (G.heat > 0) tick(); draw(); G.raf = requestAnimationFrame(step); };
  step();
}

function hit(mx, my) {
  const x = (mx - G.panX) / G.zoom, y = (my - G.panY) / G.zoom;
  for (let i = G.nodes.length - 1; i >= 0; i--) { const n = G.nodes[i], p = G.pos.get(n.id), r = radius(n) + 3; if ((p.x - x) ** 2 + (p.y - y) ** 2 <= r * r) return n; }
  return null;
}

function setupCanvas() {
  const c = $('#gcv'), tip = $('#gtip'), wrap = $('#gc');
  G.canvas = c; G.ctx = c.getContext('2d');
  if (G.ro) G.ro.disconnect();
  G.ro = new ResizeObserver(() => draw()); G.ro.observe(wrap);
  let drag = null, moved = false;
  c.onmousedown = ev => { drag = { x: ev.clientX, y: ev.clientY, px: G.panX, py: G.panY }; moved = false; c.style.cursor = 'grabbing'; };
  window.addEventListener('mouseup', () => { drag = null; if (c.isConnected) c.style.cursor = 'grab'; });
  c.onmousemove = ev => {
    const rect = c.getBoundingClientRect(), mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    if (drag) { G.panX = drag.px + ev.clientX - drag.x; G.panY = drag.py + ev.clientY - drag.y; if (Math.abs(ev.clientX - drag.x) + Math.abs(ev.clientY - drag.y) > 3) moved = true; return; }
    const n = hit(mx, my); G.hover = n?.id || null; c.style.cursor = n ? 'pointer' : 'grab';
    if (n) { tip.style.display = 'block'; tip.style.left = Math.min(mx + 14, c.clientWidth - 330) + 'px'; tip.style.top = (my + 14) + 'px';
      tip.innerHTML = `<b style="color:${color(n)}">${esc(n.name)}</b><span class="mono">${esc(n.id)}</span><div class="muted" style="margin-top:4px">${KIND[n.kind]?.label || n.kind} · ${t('graph.tip', { n: n.in, m: n.out })}${n.desktop_id ? t('graph.onDesktop') : ''}${n.inside && n.in === 0 && UNUSED_KINDS.has(n.kind) ? ` · <span style="color:var(--warn)">${t('graph.unusedTip')}</span>` : ''}</div>`; }
    else tip.style.display = 'none';
  };
  c.onmouseleave = () => { G.hover = null; tip.style.display = 'none'; };
  c.onclick = ev => { if (moved) return; const rect = c.getBoundingClientRect(); const n = hit(ev.clientX - rect.left, ev.clientY - rect.top); if (n) focus(n.id); };
  c.ondblclick = ev => { const rect = c.getBoundingClientRect(); const n = hit(ev.clientX - rect.left, ev.clientY - rect.top); if (!n) return; const id = n.desktop_id || n.engine_id; if (id) actions.select(id, true); };
  c.onwheel = ev => { ev.preventDefault(); const rect = c.getBoundingClientRect(), mx = ev.clientX - rect.left, my = ev.clientY - rect.top; const z = Math.min(4, Math.max(0.3, G.zoom * (ev.deltaY < 0 ? 1.12 : 0.89)));
    G.panX = mx - (mx - G.panX) * z / G.zoom; G.panY = my - (my - G.panY) * z / G.zoom; G.zoom = z; };
}
