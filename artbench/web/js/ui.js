// Small UI helpers shared by every view: escaping, formatting, local storage, toasts, modal dialog.
import { icon } from './icons.js';
import { t, locale } from './i18n.js';

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const base = p => (p || '').split(/[\\/]/).pop();
export const fmtTime = ts => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
/** Day and month; the year is added when it is not this year, so an old file never looks recent. */
const yearIfOld = d => d.getFullYear() === new Date().getFullYear() ? {} : { year: 'numeric' };
export const fmtDate = ts => { const d = new Date(ts * 1000); return d.toLocaleDateString(locale(), { day: '2-digit', month: 'short', ...yearIfOld(d) }); };
export const fmtDateTime = ts => { const d = new Date(ts * 1000); return d.toLocaleString(locale(), { day: '2-digit', month: 'short', ...yearIfOld(d), hour: '2-digit', minute: '2-digit' }); };
/** 'YYYY-MM-DD HH:MM:SS' (history / sync base stamps) -> '25 Eki 14:02'. */
export const fmtStamp = s => { const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(s || ''); return m ? fmtDateTime(new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5]).getTime() / 1000) : ''; };
export const fmtCount = n => Number(n).toLocaleString(locale());
export const fmtSize = b => b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
export const hashOf = o => { const s = JSON.stringify(o); let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; };

export const prefs = {
  get(key, fallback) { try { const v = localStorage.getItem('artbench.' + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem('artbench.' + key, JSON.stringify(value)); } catch { /* private window */ } },
};

export function toast(message, kind = 'bad') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.innerHTML = `${icon(kind === 'ok' ? 'check' : 'alert')}<div class="m">${esc(message)}</div><button class="btn ghost icon sm" title="${t('ui.close')}">${icon('x')}</button>`;
  el.querySelector('button').onclick = () => el.remove();
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'ok' ? 4000 : 9000);
}

/** Confirmation dialog. Resolves true on the primary button, false otherwise. */
/** Confirmation dialog. With `checks` ([{id, label, note?, checked}]) it shows one checkbox per entry and resolves
 *  to the ticked ids (or false on cancel); otherwise it resolves true / false. */
/** A confirmation dialog. With `checks` it resolves to the ticked ids; with `field` ({label, value, options}) to the
 * typed text (a list to pick from, or a new value); false when cancelled. */
export function modal({ title, body = '', items = [], checks = null, checksTitle = '', field = null, ok = t('ui.ok'), cancel = t('ui.cancel'), danger = false }) {
  return new Promise(resolve => {
    const m = $('#modal');
    const boxes = checks ? `<div class="checks">${checksTitle ? `<div class="label">${esc(checksTitle)}</div>` : ''}${checks.map((c, n) =>
      `<label class="check"><input type="checkbox" data-check="${n}" ${c.checked ? 'checked' : ''}><span>${esc(c.label)}${c.note ? ` <em>${esc(c.note)}</em>` : ''}</span></label>`).join('')}</div>` : '';
    const input = field ? `<div class="field" style="margin-top:12px"><label>${esc(field.label)}</label><input type="text" id="dlgField" list="dlgFieldList" value="${esc(field.value || '')}" spellcheck="false" autocomplete="off">`
      + `<datalist id="dlgFieldList">${(field.options || []).map(o => `<option value="${esc(o)}">`).join('')}</datalist></div>` : '';
    m.innerHTML = `<div class="card dlg"><h3>${esc(title)}</h3>
      <div class="body">${esc(body)}${boxes}${input}${items.length ? '<ul>' + items.map(i => `<li>${esc(i)}</li>`).join('') + '</ul>' : ''}</div>
      <div class="foot"><button class="btn" data-r="0">${esc(cancel)}</button><button class="btn ${danger ? 'danger' : 'primary'}" data-r="1">${esc(ok)}</button></div></div>`;
    m.hidden = false;
    const ticked = () => $$('[data-check]', m).filter(x => x.checked).map(x => checks[+x.dataset.check].id);
    const typed = () => ($('#dlgField', m)?.value || '').trim();
    const done = value => {
      const r = value && checks && field ? { field: typed(), checks: ticked() } : value && checks ? ticked()
        : field?.allowEmpty ? (value ? typed() : null) : value && field ? (typed() || false) : value;
      m.hidden = true; m.innerHTML = ''; resolve(r);
    };
    $$('button', m).forEach(b => b.onclick = () => done(b.dataset.r === '1'));
    m.onclick = e => { if (e.target === m) done(false); };
    m.onkeydown = e => { if (e.key === 'Escape') done(false); if (e.key === 'Enter' && field && e.target.id === 'dlgField') done(true); };
    if (field) { const f = $('#dlgField', m); f.focus(); f.select(); } else $('[data-r="1"]', m).focus();
  });
}

export const emptyState = (ic, text, sub = '') =>
  `<div class="empty">${icon(ic)}<b>${esc(text)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}</div>`;

export const callout = (kind, html, ic) =>
  `<div class="callout ${kind}">${icon(ic || (kind === 'ok' ? 'check' : kind === 'warn' || kind === 'bad' ? 'alert' : 'info'))}<div>${html}</div></div>`;
