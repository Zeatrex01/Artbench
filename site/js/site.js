// The download page's motion. The logo is drawn by the app's own pencil simulation (app/launch.js, copied in by
// tools/build_site.py), the tour types a question and shows the view that answers it, sections slide in once, and the
// terminal types an MCP exchange. Without this script, or under reduced motion, the page is simply all there.
import { makeMotion, show } from './app/launch.js';
import { markSvg } from './app/icons.js';

window.__artbench = true;                                     // the page's fallback in index.html stands down
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const frame = () => new Promise(r => requestAnimationFrame(r));

// --- the logo: a pencil draws the trestle, lies down on it, and the name rises --------------------------------------
const lock = $('.lock');
lock.querySelector('.mark').outerHTML = markSvg('mark');
const mark = lock.querySelector('.mark');
let drawing = 0;
async function draw() {
  const me = ++drawing, motion = makeMotion();
  lock.classList.remove('play');
  void lock.offsetWidth;                                       // restart the letters' rise
  lock.classList.add('play');
  const t0 = performance.now();
  for (;;) {
    const p = motion(performance.now() - t0);
    if (me !== drawing) return;
    show(mark, p);
    if (!p) return;
    await frame();
  }
}
if (calm) show(mark, null); else { show(mark, makeMotion()(0)); draw(); }
lock.addEventListener('click', () => { if (!calm) draw(); });

// --- sections come in once ------------------------------------------------------------------------------------------
const seen = new IntersectionObserver(entries => entries.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.classList.add('in');
  seen.unobserve(e.target);
  if (e.target.id === 'ai') typeTerminal();
}), { threshold: .18 });
$$('.hero, .reveal').forEach(el => seen.observe(el));

// --- the tour: ask, then show where Artbench answers it --------------------------------------------------------------
const tabs = $$('.tabs button'), views = $$('.view'), typed = $('.typed'), win = $('.window');
const HOLD_MS = 6000;
let current = 0, token = 0, paused = false, visible = true;

function select(i) {
  current = i;
  tabs.forEach((b, j) => { b.setAttribute('aria-selected', String(j === i)); b.tabIndex = j === i ? 0 : -1; });
  views.forEach((v, j) => { v.classList.toggle('on', j === i); v.classList.remove('tags'); });
  win.classList.remove('asking');
  setTimeout(() => views[i].classList.add('tags'), calm ? 0 : 280);
}
async function wait(ms, me, progress) {                        // a pause that stops while the tour is out of sight
  let t = 0, last = performance.now();
  while (t < ms) {
    await frame();
    if (me !== token) throw me;
    const now = performance.now();
    if (!paused && visible) t += now - last;
    last = now;
    if (progress) progress(Math.min(1, t / ms));
  }
}
async function type(text, me) {
  while (typed.textContent.length) { typed.textContent = typed.textContent.slice(0, -2); await wait(9, me); }
  for (let n = 1; n <= text.length; n++) { typed.textContent = text.slice(0, n); await wait(text[n - 1] === ' ' ? 45 : 26, me); }
}
async function tour(start, skipTyping) {
  const me = ++token;
  let i = start;
  try {
    for (;;) {
      if (skipTyping) skipTyping = false; else { win.classList.add('asking'); await type(tabs[i].dataset.q, me); }
      select(i);
      const bar = tabs[i].querySelector('i');
      await wait(HOLD_MS, me, p => bar.style.setProperty('--p', p));
      i = (i + 1) % tabs.length;
      if (calm) { typed.textContent = tabs[i].dataset.q; skipTyping = true; }
    }
  } catch (e) { /* a newer run took over */ }
}
tabs.forEach((b, i) => b.addEventListener('click', () => {
  typed.textContent = b.dataset.q;
  tabs[i].querySelector('i').style.setProperty('--p', 0);
  if (calm) { select(i); return; }
  select(i);
  tour(i, true);
}));
$('.tabs').addEventListener('keydown', e => {
  const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (!d) return;
  const n = (current + d + tabs.length) % tabs.length;
  tabs[n].focus();
  tabs[n].click();
});
win.addEventListener('pointerenter', () => { paused = true; });
win.addEventListener('pointerleave', () => { paused = false; });
new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: .08 }).observe($('#tour'));
select(0);
if (calm) tabs.forEach(b => b.querySelector('i').style.setProperty('--p', 1));
else { typed.textContent = ''; tour(0); }

// --- the terminal: an AI tool asks Artbench --------------------------------------------------------------------------
const out = $('.term-out'), script = out.textContent.split('\n');
const esc = s => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
const paint = line => line.startsWith('>') ? `<span class="u">${esc(line)}</span>`
  : line.includes('artbench ·') ? `<span class="k">${esc(line)}</span>`
  : line.includes('✓') ? `<span class="ok">${esc(line)}</span>` : esc(line);
out.innerHTML = script.map(paint).join('\n');
let typing = false;
async function typeTerminal() {
  if (calm || typing) return;
  typing = true;
  const done = [];
  const render = (extra = '') => { out.innerHTML = done.map(paint).join('\n') + (done.length ? '\n' : '') + extra + '<span class="cur"></span>'; };
  for (const line of script) {
    if (line.startsWith('>')) {
      for (let n = 1; n <= line.length; n++) { render(`<span class="u">${esc(line.slice(0, n))}</span>`); await sleep(24); }
      await sleep(420);
    } else await sleep(line.trim() ? 110 : 0);
    done.push(line);
    render();
  }
  typing = false;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
