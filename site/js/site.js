// The download page's motion. The logo is drawn by the app's own pencil simulation (app/launch.js, copied in by
// tools/build_site.py); everything below it moves with the scroll: the hero drifts away, sections rise and slide in as
// they come up (and back as they go), the tour is pinned while the page scrolls through its six questions, a pencil
// line along the top bar follows the reader, and the terminal types an MCP exchange. Without this script, or under
// reduced motion, the page is simply all there.
import { makeMotion, show } from './app/launch.js';
import { markSvg } from './app/icons.js';

window.__artbench = true;                                     // the page's fallback in index.html stands down
const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const frame = () => new Promise(r => requestAnimationFrame(r));
const sleep = ms => new Promise(r => setTimeout(r, ms));

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

// --- once: the hero's text rises, the terminal starts typing, the rule's checks are drawn ----------------------------
const seen = new IntersectionObserver(entries => entries.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.classList.add('in');
  seen.unobserve(e.target);
  if (e.target.id === 'ai') typeTerminal();
}), { threshold: .18 });
$$('.hero, .sc').forEach(el => seen.observe(el));

// --- scroll: every section moves with the page, both ways --------------------------------------------------------------
// --e on a section: 0 while its top is at the bottom of the window, 1 once it is two thirds up; --s on the hero: how far
// it has scrolled away; --pg on the page: how far down the reader is (the pencil line under the bar).
const root = document.documentElement, hero = $('.hero'), moving = $$('.sc');
const clamp01 = x => Math.max(0, Math.min(1, x));
let queued = false;
function onScroll() {
  queued = false;
  const vh = innerHeight;
  root.style.setProperty('--pg', (scrollY / Math.max(1, root.scrollHeight - vh)).toFixed(4));
  hero.style.setProperty('--s', clamp01(scrollY / hero.offsetHeight).toFixed(4));
  for (const el of moving) el.style.setProperty('--e', clamp01((vh - el.getBoundingClientRect().top) / (vh * .66)).toFixed(4));
  scrollTour();
}
const queue = () => { if (!queued) { queued = true; requestAnimationFrame(onScroll); } };

// --- the tour: pinned while the page scrolls through it; each stretch asks a question and shows its answer ---------
const tour = $('#tour'), pin = $('.tour-pin'), tabs = $$('.tabs button'), views = $$('.view'), typed = $('.typed'), win = $('.window');
let current = -1, token = 0;

function markTab(i) { tabs.forEach((b, j) => { b.setAttribute('aria-selected', String(j === i)); b.tabIndex = j === i ? 0 : -1; }); }
function showView(i) {
  views.forEach((v, j) => { v.classList.toggle('on', j === i); v.classList.remove('tags'); });
  win.classList.remove('asking');
  setTimeout(() => { if (current === i) views[i].classList.add('tags'); }, calm ? 0 : 260);
}
async function ask(i) {                                        // type the question, then show the view that answers it
  const me = ++token, text = tabs[i].dataset.q;
  current = i;
  markTab(i);
  if (calm) { typed.textContent = text; showView(i); return; }
  win.classList.add('asking');
  while (typed.textContent.length) { typed.textContent = typed.textContent.slice(0, -3); await sleep(8); if (me !== token) return; }
  for (let n = 1; n <= text.length; n++) { typed.textContent = text.slice(0, n); await sleep(16); if (me !== token) return; }
  showView(i);
}
function stretch() {                                           // the scroll range the tour stays pinned for, per view
  const top = tour.getBoundingClientRect().top + scrollY - 64;
  return { top, each: Math.max(1, (tour.offsetHeight - pin.offsetHeight) / tabs.length) };
}
function scrollTour() {
  const { top, each } = stretch(), into = scrollY - top;
  const i = Math.max(0, Math.min(tabs.length - 1, Math.floor(into / each)));
  tabs.forEach((b, j) => b.querySelector('i').style.setProperty('--p', j === i ? clamp01((into - j * each) / each).toFixed(3) : 0));
  if (i !== current) ask(i);
}
tabs.forEach((b, i) => b.addEventListener('click', () => {    // a tab scrolls the page to its stretch
  if (calm) { ask(i); return; }
  const { top, each } = stretch();
  scrollTo({ top: top + i * each + 2, behavior: 'smooth' });
}));
$('.tabs').addEventListener('keydown', e => {
  const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (!d) return;
  const n = Math.max(0, Math.min(tabs.length - 1, current + d));
  tabs[n].focus();
  tabs[n].click();
});
if (calm) ask(0);
else { typed.textContent = ''; addEventListener('scroll', queue, { passive: true }); addEventListener('resize', queue); onScroll(); }

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
