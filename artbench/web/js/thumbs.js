// Lazy thumbnails: /api/thumb answers 200 (PNG), 202 (Blender still rendering: retry) or 404 (placeholder tile).
// One shared cache of object URLs per model path; tiles load when they scroll into view.
import { api } from './api.js';
import { icon } from './icons.js';
import { esc } from './ui.js';
import { S } from './state.js';

const cache = new Map();       // path -> object URL; kept across project switches (a path names one file)
const tries = new Map();       // path -> retry count
const started = new Map();     // path -> when the first 202 came
// While Blender renders (202) the page asks again, less often as it waits, and only gives up after giveUpMs: a large
// project's first previews can take minutes, and a tile that gave up early stayed empty.
export const RETRY = { first: 3000, max: 15000, giveUpMs: 10 * 60 * 1000 };
const delay = n => Math.min(RETRY.max, RETRY.first * Math.pow(1.3, n - 1));
const keepTrying = path => { if (!started.has(path)) started.set(path, Date.now()); return Date.now() - started.get(path) < RETRY.giveUpMs; };

export const thumbHTML = (path, cls = '') => `<div class="thumb ${cls} ${path ? '' : 'none'}" data-thumb="${esc(path || '')}">${icon('box')}</div>`;

function show(el, url) {
  el.classList.remove('pending', 'failed');
  let img = el.querySelector('img');
  if (!img) { img = document.createElement('img'); img.alt = ''; el.prepend(img); }
  img.src = url;
}

async function load(el) {
  const path = el.dataset.thumb;
  if (!path) return;
  if (cache.has(path)) { show(el, cache.get(path)); return; }
  try {
    const r = await fetch(api.thumbURL(S.project, path));
    if (r.status === 200) {
      const url = URL.createObjectURL(await r.blob());
      cache.set(path, url);
      document.querySelectorAll(`.thumb[data-thumb="${CSS.escape(path)}"]`).forEach(e => show(e, url));
    } else if (r.status === 202) {
      el.classList.add('pending');
      const n = (tries.get(path) || 0) + 1;
      tries.set(path, n);
      if (keepTrying(path)) setTimeout(() => { if (el.isConnected) load(el); }, delay(n));
      else { el.classList.remove('pending'); el.classList.add('failed'); }
    } else { el.classList.remove('pending'); el.classList.add('failed'); }
  } catch { el.classList.add('failed'); }
}

const observer = new IntersectionObserver(entries => {
  for (const e of entries) if (e.isIntersecting) { observer.unobserve(e.target); load(e.target); }
}, { rootMargin: '160px' });

/** Call after inserting HTML that contains thumbHTML() tiles. */
export function observeThumbs(root = document) {
  root.querySelectorAll('.thumb[data-thumb]').forEach(el => {
    if (!el.dataset.thumb || el.querySelector('img')) return;
    if (cache.has(el.dataset.thumb)) show(el, cache.get(el.dataset.thumb)); else observer.observe(el);
  });
}
/** On a project switch: forget the waiting, keep the previews (each is keyed by its file's own path). */
export function clearThumbs() { tries.clear(); started.clear(); }

/** For canvas drawing: resolves to an Image or null (retries while Blender renders). */
export function thumbImage(path) {
  return new Promise(resolve => {
    const attempt = n => fetch(api.thumbURL(S.project, path)).then(r => {
      if (r.status === 200) return r.blob().then(b => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => resolve(null); img.src = URL.createObjectURL(b); });
      if (r.status === 202 && keepTrying(path)) setTimeout(() => attempt(n + 1), delay(n + 1)); else resolve(null);
    }).catch(() => resolve(null));
    attempt(0);
  });
}
