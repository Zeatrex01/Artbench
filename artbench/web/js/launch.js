// The opening: a pencil draws the mark, the A of the trestle (two legs, the bar) and then the board across it, lifts
// it off the paper, turns it level and lets it drop onto the board it drew; the name rises. Plays once per browser
// session when the page opens; any key or click skips it; never shown when the system asks for reduced motion. It
// lets clicks through, so the page underneath stays usable.
import { A_STROKES, BOARD, PENCIL_TIP, markSvg } from './icons.js';
import { t } from './i18n.js';

const SEEN = 'artbench.launched';
const LENGTH_MS = 3500;

// --- motion: a hand and a pencil, simulated (springs, gravity) so the timing is never mechanical -----------------
// Everything is in the mark's 48 grid. The plan says where the hand wants the lead to be; springs make the pencil
// follow it as a real one would (a little late, a little past the end of a line, leaning with the stroke).
const STROKES = [...A_STROKES, BOARD];
const HALF = 15;                                       // from the pencil's middle to its lead
const REST = [PENCIL_TIP[0] - HALF, PENCIL_TIP[1]];    // the resting pencil's middle, on the board
const WRITE = 128;                                     // degrees: held to write, lead down and to the left
const START = [64, 70];                                // where the hand comes from: low right, off the paper
const DT = 1 / 240;
// [ms, kind, stroke, lift]: move the lead to the stroke's start (lifted that high in between) or draw the stroke.
const PLAN = [[330, 'to', 0, 1], [270, 'draw', 0], [150, 'to', 1, .35], [250, 'draw', 1], [170, 'to', 2, .4],
  [190, 'draw', 2], [190, 'to', 3, .5], [330, 'draw', 3]];
const RISE_MS = 330, HANG_MS = 60, SETTLE_MS = 700;   // lift and turn level, a beat in the air, then the drop

const smooth = x => x * x * (3 - 2 * x);             // a hand: slow off, fast through, slow in
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const rad = d => d * Math.PI / 180;
const strokeLength = ([x0, y0, x1, y1]) => Math.hypot(x1 - x0, y1 - y0);
function spring(s, key, target, k, zeta) {           // semi-implicit Euler, one DT
  const v = s[key + 'V'] + (k * (target - s[key]) - 2 * zeta * Math.sqrt(k) * s[key + 'V']) * DT;
  s[key + 'V'] = v; s[key] += v * DT;
}
function along(st, [x, y]) {                         // how far along a stroke a point is, 0..1
  const dx = st[2] - st[0], dy = st[3] - st[1];
  return clamp(((x - st[0]) * dx + (y - st[1]) * dy) / (dx * dx + dy * dy));
}

/** The hand's plan at `ms`: where the lead should be, how high it is lifted, which stroke is being drawn. */
function plan(ms) {
  let at = 0, from = START;
  for (const [n, [len, kind, i, lift]] of PLAN.entries()) {
    const st = STROKES[i], to = kind === 'draw' ? [st[2], st[3]] : [st[0], st[1]];
    if (ms < at + len) {
      const x = smooth((ms - at) / len);
      const h = kind === 'draw' ? 0 : i === 0 ? 1 - x : lift * Math.sin(Math.PI * x);
      return { tip: [from[0] + (to[0] - from[0]) * x, from[1] + (to[1] - from[1]) * x], h, drawing: kind === 'draw' ? i : -1, index: n };
    }
    at += len; from = to;
  }
  return { tip: from, h: 0, drawing: -1, index: PLAN.length };
}
const DRAWN_MS = PLAN.reduce((a, p) => a + p[0], 0);

/** Steps the pencil to `ms` (forward only; a step back starts again) and returns what to draw, or null once it rests. */
export function makeMotion() {
  let s = null;
  const reset = () => ({ ms: 0, x: START[0], xV: 0, y: START[1], yV: 0, a: WRITE + 14, aV: 0, h: 1, hV: 0, sq: 0, sqV: 0,
    drawn: STROKES.map(() => 0), body: false, falling: false, landed: 0 });
  function step() {
    const ms = s.ms, p = plan(ms);
    if (ms < DRAWN_MS) {                               // writing: the lead follows the hand, the body leans with it
      spring(s, 'x', p.tip[0], 2600, .82); spring(s, 'y', p.tip[1], 2600, .82); spring(s, 'h', p.h, 900, .9);
      const lean = clamp(-s.xV * .05, -16, 16) + Math.sin(ms / 1000 * 2 * Math.PI * 2.6) * 1.3;
      spring(s, 'a', WRITE + lean, 340, .55);
      if (p.drawing >= 0) s.drawn[p.drawing] = Math.max(s.drawn[p.drawing], along(STROKES[p.drawing], [s.x, s.y]));
      PLAN.forEach(([, kind, i], n) => { if (kind === 'draw' && n < p.index) s.drawn[i] = 1; });   // a finished line stays whole
    } else {
      if (!s.body) {                                   // from the lead to the middle: the pencil is picked up
        s.body = true; s.drawn = STROKES.map(() => 1);
        const c = [s.x - HALF * Math.cos(rad(s.a)), s.y - HALF * Math.sin(rad(s.a))];
        s.x = c[0]; s.y = c[1]; s.xV = 0; s.yV = 0;
      }
      const tt = ms - DRAWN_MS;
      if (tt < RISE_MS + HANG_MS) {                    // up, and turned almost level: the eraser end a little low
        spring(s, 'x', REST[0] + 1.5, 150, .72); spring(s, 'y', REST[1] - 11, 170, .7);
        spring(s, 'a', -7, 120, .62); spring(s, 'h', .3, 200, .8);
      } else {                                         // let go: it falls, lands, bounces a little and rocks level
        if (!s.falling) { s.falling = true; s.yV = Math.max(s.yV, 0); }
        s.yV += 1150 * DT; s.y += s.yV * DT;
        if (s.y >= REST[1]) {
          if (s.yV > 6) { s.sqV += s.yV * (s.landed ? .006 : .016); s.aV += s.landed ? 0 : 160; s.landed++; }
          s.y = REST[1]; s.yV = s.yV > 6 ? -s.yV * .26 : 0;
        }
        spring(s, 'x', REST[0], 220, .8); spring(s, 'h', 0, 500, .9);
        spring(s, 'a', 0, s.landed ? 950 : 120, s.landed ? .3 : .62);
      }
      spring(s, 'sq', 0, 1500, .32);
    }
    s.ms += DT * 1000;
  }
  return ms => {
    if (!s || ms < s.ms - 1) s = reset();
    while (s.ms < ms) step();
    if (ms >= DRAWN_MS + RISE_MS + HANG_MS + SETTLE_MS) return null;
    const tip = s.body ? [s.x + HALF * Math.cos(rad(s.a)), s.y + HALF * Math.sin(rad(s.a))] : [s.x, s.y];
    return { tip, angle: s.a, lift: s.h, squash: s.sq, drawn: s.drawn.slice() };
  };
}

/** Puts a motion frame on a mark (the strokes drawn so far, the pencil, its shadow, the board giving); null: at rest. */
export function show(mark, p) {
  const pencil = mark.querySelector('.lp'), lines = mark.querySelectorAll('.la, .lb');
  let shadow = mark.querySelector('.lps');
  if (!shadow) {
    mark.insertAdjacentHTML('afterbegin', '<defs><filter id="lpblur" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="1.1"/></filter></defs>');
    shadow = pencil.cloneNode(true);
    shadow.setAttribute('class', 'lps');
    Object.assign(shadow.style, { color: '#000', filter: 'url(#lpblur)' });
    pencil.before(shadow);
  }
  lines.forEach((el, i) => {
    const len = strokeLength(STROKES[i]);
    el.style.strokeDasharray = `${len} ${len + 1}`;
    el.style.strokeDashoffset = `${p ? len * (1 - p.drawn[i]) : 0}`;
  });
  if (!p) { pencil.removeAttribute('transform'); shadow.style.opacity = 0; mark.style.transform = ''; return; }
  const place = (dx, dy, scale) => `translate(${p.tip[0] + dx} ${p.tip[1] + dy}) rotate(${p.angle}) scale(${scale}) translate(${-PENCIL_TIP[0]} ${-PENCIL_TIP[1]})`;
  pencil.setAttribute('transform', place(0, 0, 1 + .13 * p.lift));
  shadow.setAttribute('transform', place(1 + 3.2 * p.lift, 1.4 + 4.2 * p.lift, 1));
  shadow.style.opacity = String(.32 * clamp(p.lift * 2.5) * (1 - .35 * p.lift));
  mark.style.transform = p.squash ? `scale(${1 + p.squash * .55}, ${1 - p.squash})` : '';
}

// --- the page -------------------------------------------------------------------------------------------------------

function seen() {
  try { if (sessionStorage.getItem(SEEN)) return true; sessionStorage.setItem(SEEN, '1'); } catch (e) { /* storage off */ }
  return false;
}

export function playLaunch() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || seen()) return;
  const el = document.createElement('div');
  el.id = 'launch';
  el.setAttribute('aria-hidden', 'true');
  el.innerHTML = `<div class="ln-lock">${markSvg('ln-mark')}<span class="ln-word">${[...'Artbench'].map((c, i) => `<i style="--i:${i}">${c}</i>`).join('')}</span></div>
    <p class="ln-tag"><span>${t('launch.tagline')}</span></p>`;
  const mark = el.querySelector('.ln-mark'), motion = makeMotion();
  show(mark, motion(0));
  document.body.appendChild(el);
  const t0 = performance.now();
  let done = false, frame = 0;
  const tick = now => {
    if (done) return;
    const p = motion(now - t0);
    show(mark, p);
    if (p) frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  const leave = () => {
    if (done) return;
    done = true;
    cancelAnimationFrame(frame);
    removeEventListener('keydown', leave, true);
    removeEventListener('pointerdown', leave, true);
    el.classList.add('out');
    setTimeout(() => el.remove(), 400);
  };
  addEventListener('keydown', leave, true);
  addEventListener('pointerdown', leave, true);
  setTimeout(leave, LENGTH_MS);
}
