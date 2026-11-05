// Library view: stat tiles, then groups (state -> category -> set) as a card grid or a row list.
import { ICONS, icon } from './icons.js';
import { t } from './i18n.js';
import { $$, esc, prefs, emptyState, callout } from './ui.js';
import { thumbHTML } from './thumbs.js';
import { markBadges, pickBox } from './marks.js';
import { S, STATE_LABEL, STATE_CLS, STATE_ORDER, SYNC, USAGE, actions, counts, filteredItems, setOf, setLabel, bySet, chipsFor, engineUnreachable, syncOf } from './state.js';

/** Card for a desktop or engine-only entry; `path` is the file the thumbnail is rendered from. */
export function tile(i, path) {
  const open = S.tasks.filter(t => t.asset === i.id && t.status !== 'done').length;
  return `<div class="tile ${S.selected === i.id ? 'on' : ''}" data-id="${esc(i.id)}">${pickBox(i.id)}${thumbHTML(path)}
    <div class="meta"><div class="name ellip" title="${esc(i.name)}">${esc(i.name)}</div>
      <div class="chips">${markBadges(i.id)}${chipsFor(i)}${open ? `<span class="chip accent nodot">${t('lib.openTasks', { n: open })}</span>` : ''}${i.textures?.length ? `<span class="tex">${icon('image')}${i.textures.length}</span>` : ''}</div>
      ${i.note ? `<div class="cap ellip">${esc(i.note)}</div>` : ''}</div></div>`;
}
export function lrow(i, path, sub = '') {
  return `<div class="lrow ${S.selected === i.id ? 'on' : ''}" data-id="${esc(i.id)}">${pickBox(i.id)}${thumbHTML(path, 'sq')}
    <div class="ellip"><span class="name">${esc(i.name)}</span> <span class="sub">${esc(sub || i.id)}</span>${i.note ? `<div class="sub ellip">${esc(i.note)}</div>` : ''}</div>
    <div class="meta">${markBadges(i.id)}${chipsFor(i)}</div><div class="r">${syncOf(i) === 'conflict' ? '' : syncOf(i) ? `<span class="synclabel ${SYNC[syncOf(i)][0]} ${i.basis === 'mtime' ? 'provisional' : ''}" title="${i.basis === 'mtime' ? t('lib.provisionalTitle') : ''}">${SYNC[syncOf(i)][1]}</span>` : (i.usage ? USAGE[i.usage][1] : '')}</div><div class="r">${i.textures?.length ? t('lib.textures', { n: i.textures.length }) : ''}</div></div>`;
}
export function groupHead(title, cat, n, extra = '', collapsible = true) {
  return `<div class="ghead">${collapsible ? `<svg class="i chev" viewBox="0 0 24 24">${ICONS.chevron}</svg>` : ''}<h3>${esc(title)}${cat ? ` <span class="cat">· ${esc(cat)}</span>` : ''}</h3><span class="cnt">${n}</span>${extra}<div class="line"></div></div>`;
}

function stat(v, label, color, sub, filter) {
  const on = filter && S.filters[filter[0]] === filter[1];
  return `<div class="stat ${on ? 'on' : ''} ${filter ? '' : 'static'}" style="--c:${color}" data-stat="${filter ? filter.join(':') : ''}"><div class="v">${v}</div><div class="l">${label}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
}

export function viewLibrary() {
  const c = counts(), items = filteredItems();
  const conflictStat = stat(c.conflict, t('lib.stat.conflict'), 'var(--bad)', c.conflict ? t('lib.stat.conflictSub') : t('lib.stat.noConflict'), c.conflict ? ['sync', 'conflict'] : null);
  const engineWarn = !S.data.engine_root ? callout('warn', t('lib.noEngineRoot'))
    : engineUnreachable() ? callout('warn', t('lib.engineUnreachable', { root: esc(S.data.engine_root) })) : '';
  const stats = engineWarn + `<div class="stats">
    ${c.conflict ? conflictStat : ''}
    ${stat(c.models, t('lib.stat.models'), 'var(--accent)', t('lib.stat.blends', { n: c.blends }), null)}
    ${stat(c.ingame, t('lib.stat.ingame'), 'var(--ok)', t('lib.stat.inUse', { n: c.used }), ['state', 'ingame'])}
    ${stat(c.stock, t('lib.stat.stock'), 'var(--dim)', t('lib.stat.outbox', { n: c.outbox }), ['state', 'stock'])}
    ${stat(c.unused, t('lib.stat.unused'), 'var(--warn)', t('lib.stat.unusedSub'), ['usage', 'unused'])}
    ${stat(c.desktopNewer, t('lib.stat.desktopNewer'), 'var(--warn)', t('lib.stat.engineNewer', { n: c.engineNewer }), ['sync', 'desktop_newer'])}
    ${stat(c.missing, t('lib.stat.missing'), 'var(--bad)', t('lib.stat.engineOnly', { n: c.engine }), ['sync', 'missing_in_engine'])}
    ${c.conflict ? '' : conflictStat.replace('class="stat ', 'class="stat quiet ')}
  </div>`;
  if (!items.length) return stats + emptyState('search', t('lib.empty'), t('lib.emptySub'));
  const groups = {};
  for (const i of items) { const k = `${i.state}|${i.category}|${setOf(i)}`; (groups[k] ||= { state: i.state, category: i.category, set: setOf(i), items: [] }).items.push(i); }
  const ordered = Object.entries(groups).sort((a, b) => (STATE_ORDER[a[1].state] - STATE_ORDER[b[1].state]) || a[1].category.localeCompare(b[1].category) || bySet(a[1].set, b[1].set));
  return stats + ordered.map(([k, g]) => {
    const closed = S.closedGroups[k] ?? (g.state === 'archive');
    const used = g.items.filter(i => i.usage === 'used').length, un = g.items.filter(i => i.usage === 'unused').length;
    const extra = `<span class="chip ${STATE_CLS[g.state]} nodot">${STATE_LABEL[g.state]}</span><span class="dots">${used ? `<span class="dot ok" title="${t('lib.used', { n: used })}"></span>` : ''}${un ? `<span class="dot warn" title="${t('lib.unused', { n: un })}"></span>` : ''}</span>`;
    return `<div class="group ${closed ? 'closed' : ''}" data-group="${esc(k)}">${groupHead(setLabel(g.set), g.category, g.items.length, extra)}
      ${S.listMode === 'grid' ? `<div class="grid">${g.items.map(i => tile(i, i.path)).join('')}</div>` : `<div class="list">${g.items.map(i => lrow(i, i.path, setLabel(setOf(i)))).join('')}</div>`}</div>`;
  }).join('');
}

/** Shared bindings for any view that renders tiles/rows/groups/stat tiles. */
export function bindCommon(el) {
  $$('[data-id]', el).forEach(n => n.onclick = () => actions.select(n.dataset.id));
  $$('[data-stat]', el).forEach(n => n.onclick = () => { const [k, v] = n.dataset.stat.split(':'); if (!k) return; S.filters[k] = S.filters[k] === v ? null : v; actions.render(); });
  $$('.group .ghead', el).forEach(h => h.onclick = () => {
    const g = h.parentElement, k = g.dataset.group; if (!k) return;
    const closed = !g.classList.contains('closed'); S.closedGroups[k] = closed; prefs.set('closedGroups', S.closedGroups); g.classList.toggle('closed', closed);
  });
}
