import { FONT_SIZE, WEIGHTS, PAGE_TYPES, preferences, countGrid, geometry, anchoredScroll, resolvePage, clamp, sentenceCase, pageCaption, adjacentPage, pageGroup, groupedPages, pageGroups, pageCode, pageTitle } from './geometry.js';
import { createInteractions, readSelection } from './interactions.js';
import { readVerifiedText } from './text-integrity.js';

const $ = id => document.getElementById(id);
const catalogueSetting = document.querySelector('meta[name="ald-catalogue"]')?.content;
const catalogueURL = catalogueSetting ? new URL(catalogueSetting, document.baseURI) : new URL('../data/catalogue.json', import.meta.url);
const viewport = $('viewport');
const storageKey = 'vaxbarn.ALDbrowser.appearance.v1';
let saved = {};
try { saved = JSON.parse(localStorage.getItem(storageKey) || '{}'); } catch { /* Browser-local persistence is optional. */ }
const state = { pages: [], page: null, metrics: null, view: { ...preferences(saved), zoom: 1, mode: 'fit-width' }, request: null, fontRequest: 0, fontAdvance: new Map(), pan: null, space: false };
const interactionView = createInteractions({
  pre:$('ald-text'),viewport,inner:$('sheet-inner'),getMetrics:()=>state.metrics,
  getPage:()=>state.page,getPages:()=>state.pages,catalogueURL,
  navigate:(page,selection)=>loadPage(page,'push',selection),
});

function notify(message, error = false, retry = null) {
  $('notice').hidden = !message;
  $('notice-text').textContent = message;
  $('notice').setAttribute('role', error ? 'alert' : 'status');
  $('retry').hidden = !retry;
  $('retry').onclick = retry;
}

function remember() {
  try { localStorage.setItem(storageKey, JSON.stringify(preferences(state.view))); } catch { /* Viewing works without local storage. */ }
}

async function ensureFont(weight) {
  const font = `${weight} ${FONT_SIZE}px "ALD JuliaMono"`;
  const loaded = await document.fonts.load(font, 'M─│┼◇◺');
  if (!loaded.length || !document.fonts.check(font, 'M─│┼◇◺')) throw new Error('JuliaMono could not be loaded. Check the font files and try again.');
  if (!state.fontAdvance.has(weight)) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = font;
    state.fontAdvance.set(weight, context.measureText('M'.repeat(64)).width / 64);
  }
}

function updateAppearanceControls() {
  $('weight').value = String(state.view.weight);
  $('stretch-x').value = String(Math.round(state.view.stretchX * 100));
  $('stretch-y').value = String(Math.round(state.view.stretchY * 100));
  $('stretch-x-value').value = `${Math.round(state.view.stretchX * 100)}%`;
  $('stretch-y-value').value = `${Math.round(state.view.stretchY * 100)}%`;
  const original = state.view.stretchX === 1 && state.view.stretchY === 1;
  $('view-summary').textContent = `JuliaMono ${state.view.weight} · ${original ? 'Original proportions' : `${Math.round(state.view.stretchX * 100)}% wide / ${Math.round(state.view.stretchY * 100)}% high`}`;
}

function layout({ anchor = null, reset = false } = {}) {
  if (!state.page) return;
  const old = state.metrics;
  const point = anchor || { x: viewport.clientWidth / 2, y: viewport.clientHeight / 2 };
  const scroll = { left: viewport.scrollLeft, top: viewport.scrollTop };
  const next = geometry(state.page, state.view, { width: viewport.clientWidth, height: viewport.clientHeight });
  state.metrics = next;
  state.view.zoom = next.zoom;
  const sheet = $('sheet');
  sheet.style.width = `${next.width}px`;
  sheet.style.height = `${next.height}px`;
  sheet.style.left = `${next.left}px`;
  sheet.style.top = `${next.top}px`;
  const inner = $('sheet-inner');
  inner.style.width = `${next.baseWidth}px`;
  inner.style.height = `${next.baseHeight}px`;
  inner.style.transform = `scale(${next.scaleX}, ${next.scaleY})`;
  const pre = $('ald-text');
  pre.style.fontWeight = String(state.view.weight);
  pre.style.lineHeight = `${next.rowPitch}px`;
  pre.style.transform = `scaleX(${next.columnPitch / state.fontAdvance.get(state.view.weight)})`;
  $('stage').style.setProperty('--stage-width', `${next.stageWidth}px`);
  $('stage').style.setProperty('--stage-height', `${next.stageHeight}px`);
  $('zoom').options[0].textContent = `${Math.round(next.zoom * 100)}%${state.view.mode === 'fit-width' ? ' · width' : state.view.mode === 'fit-page' ? ' · page' : ''}`;
  $('zoom').value = 'current';
  $('zoom-out').disabled = next.zoom <= 0.05001;
  $('zoom-in').disabled = next.zoom >= 5.99999;
  const position = reset ? { left: 0, top: 0 } : anchoredScroll(old, next, scroll, point);
  viewport.scrollTo(position.left, position.top);
  updateAppearanceControls();
}

function zoomBy(factor, anchor) {
  if (!state.page) return;
  state.view.zoom = clamp(state.view.zoom * factor, 0.05, 6);
  state.view.mode = 'manual';
  layout({ anchor });
}

function fit(mode) {
  state.view.mode = mode;
  layout({ reset: true });
}

function sourceURL(page) {
  const url = new URL(page.url, catalogueURL);
  if (url.origin !== location.origin || !url.pathname.startsWith(new URL('.', catalogueURL).pathname) || !url.pathname.endsWith('.txt')) throw new Error('The selected page has an invalid text URL.');
  return url;
}

function bookmark(page) {
  return state.pages.filter(item => pageCode(item) === pageCode(page)).length === 1 ? pageCode(page) : page.id;
}

function setOptions(select, options, selected) {
  select.replaceChildren(...options.map(([value,label]) => new Option(label, value)));
  if (selected !== undefined) select.value = selected;
  select.disabled = !options.length;
}

function updatePageSelectors(page) {
  setOptions($('page-type'), PAGE_TYPES.filter(([type]) => state.pages.some(item => item.type === type)), page.type);
  const card = page.type === 'card-ald';
  $('section-label').textContent = card ? 'Card type' : 'Section';
  $('page-label').textContent = card ? 'Notation variant' : 'Page';
  setOptions($('page-section'), pageGroups(state.pages,page.type).map(group => [group,group]),pageGroup(page));
  setOptions($('page-select'), groupedPages(state.pages,page.type,pageGroup(page)).map(item =>
    [item.id, card ? (item.variant ? `Variant ${item.variant}` : 'Canonical') : `${pageCode(item)} ${pageTitle(item)}`]),page.id);
}

function updateDownloads(page) {
  for (const [kind,relative,name] of [['txt',page.url,page.txtDownloadName],['json',page.jsonURL,page.jsonDownloadName]]) {
    const link=$(`download-${kind}`);
    const url=relative ? new URL(relative,catalogueURL) : null;
    const valid=url && url.origin===location.origin && url.pathname.startsWith(new URL('.',catalogueURL).pathname) && url.pathname.endsWith(`.${kind}`);
    link.setAttribute('aria-disabled',String(!valid));link.tabIndex=valid?0:-1;
    if(valid) {
      link.href=url.href;link.download=name || `${pageCode(page)}.${kind}`;
      link.title=`Download ${link.download}${page.type==='card-ald' && kind==='json' ? ' (card definition, including variants)' : ''}`;
    } else { link.removeAttribute('href');link.removeAttribute('download');link.title='No published JSON definition is available for this page.'; }
  }
}

async function loadPage(page, historyMode = 'push', selection = null) {
  state.request?.abort();
  interactionView.reset();
  updatePageSelectors(page);
  const request = new AbortController();
  state.request = request;
  $('choose-page').setAttribute('aria-busy', 'true');
  notify(`Opening ${page.page}…`);
  try {
    const [response] = await Promise.all([fetch(sourceURL(page), { signal: request.signal }), ensureFont(state.view.weight)]);
    if (!response.ok) throw new Error(`Page ${page.page} could not be loaded (${response.status}).`);
    const verified = await readVerifiedText(await response.arrayBuffer(), page.textSha256);
    const text = verified.text;
    if (state.request !== request) return;
    // This is deliberately a text node: no SVG, bitmap, HTML interpretation,
    // per-character spans or changes to the ALD's spaces and Unicode glyphs.
    $('ald-text').textContent = text;
    const grid = countGrid(text);
    state.page = { ...page, ...grid };
    state.metrics = null;
    $('sheet').hidden = false;
    $('sheet').setAttribute('aria-label', `${pageCode(page)} — ${page.title}`);
    $('ald-text').setAttribute('aria-label', `${pageCode(page)} diagram text`);
    $('empty-state').hidden = true;
    $('current-page').textContent = pageCode(page);
    $('current-title').textContent = pageTitle(page);
    $('current-section').textContent = pageCaption(page);
    $('current-section').title = pageCaption(page);
    updatePageSelectors(page);
    updateDownloads(page);
    for (const [id, offset] of [['previous-page', -1], ['next-page', 1]]) {
      const neighbour = adjacentPage(groupedPages(state.pages,page.type), page.id, offset);
      $(id).disabled = !neighbour;
      $(id).title = neighbour ? `${offset < 0 ? 'Previous' : 'Next'} page: ${pageCode(neighbour)} ${pageTitle(neighbour)}` : `${offset < 0 ? 'Previous' : 'Next'} page`;
    }
    $('choose-page').title = `${pageCode(page)} — ${pageTitle(page)} · Choose a page (P)`;
    document.title = `${pageCode(page)} · ALDbrowser · VAXBARN`;
    layout({ reset: true });
    if (historyMode !== 'none') {
      const url = new URL(location.href);
      url.searchParams.set('page', bookmark(page));
      if(selection)url.searchParams.set('selection',JSON.stringify(selection));else url.searchParams.delete('selection');
      history[historyMode === 'replace' ? 'replaceState' : 'pushState']({ page: page.id,selection }, '', url);
    }
    if (verified.interactionsAllowed) await interactionView.load(page,text,selection);
    if(state.request === request)notify(verified.notice);
  } catch (error) {
    if (error.name !== 'AbortError' && state.request === request) {
      if (state.page) updatePageSelectors(state.page);
      $('empty-state').querySelector('p').textContent = 'Choose a page from the menu to begin.';
      notify(error.message, true, () => loadPage(page, historyMode, selection));
    }
  } finally {
    if (state.request === request) $('choose-page').removeAttribute('aria-busy');
  }
}

function filterPages() {
  const needle = $('page-search').value.trim().toLocaleLowerCase();
  const terms = needle.split(/\s+/).filter(Boolean);
  const section = $('section-filter').value;
  const results = state.pages.filter(page => (!section || page.section === section) && terms.every(term => `${page.page} ${pageCode(page)} ${pageTitle(page)} ${page.section}`.toLocaleLowerCase().includes(term)));
  $('result-count').textContent = `${results.length.toLocaleString()} ${results.length === 1 ? 'page' : 'pages'}`;
  const fragment = document.createDocumentFragment();
  for (const page of results) {
    const button = document.createElement('button');
    button.className = 'result-button';
    button.type = 'button';
    button.dataset.pageId = page.id;
    if (state.page?.id === page.id) button.setAttribute('aria-current', 'page');
    const code = document.createElement('strong');code.textContent = pageCode(page);
    const title = document.createElement('span');title.className = 'result-title';title.textContent = pageTitle(page);
    const sectionText = document.createElement('span');sectionText.className = 'result-section';sectionText.textContent = page.section;
    button.append(code, title, sectionText);
    button.addEventListener('click', () => { $('page-dialog').close(); loadPage(page); });
    fragment.append(button);
  }
  if (!results.length) {
    const empty = document.createElement('p');empty.className = 'no-results';empty.textContent = 'No pages match. Try another page number or section.';fragment.append(empty);
  }
  $('page-results').replaceChildren(fragment);
  $('page-results').scrollTop = 0;
}

function choosePage(query = '') {
  $('page-search').value = query;
  if (query) $('section-filter').value = '';
  filterPages();
  if (!$('page-dialog').open) $('page-dialog').showModal();
  $('page-search').focus();
  $('page-search').select();
}

async function setWeight(value) {
  const weight = Number(value);
  if (!WEIGHTS.includes(weight)) return;
  const request = ++state.fontRequest;
  $('weight').disabled = true;
  try {
    await ensureFont(weight);
    if (request !== state.fontRequest) return;
    state.view.weight = weight;
    layout();remember();
  } catch (error) {
    if (request === state.fontRequest) { $('weight').value = String(state.view.weight);notify(error.message, true, () => setWeight(weight)); }
  } finally { if (request === state.fontRequest) $('weight').disabled = false; }
}

function editable(target) {
  return target instanceof Element && Boolean(target.closest('input, select, textarea, button, a, [contenteditable="true"]'));
}

$('page-type').addEventListener('change', event => {
  const page = groupedPages(state.pages,event.target.value)[0];
  if (page) loadPage(page);
});
$('page-section').addEventListener('change', event => {
  const page = groupedPages(state.pages,$('page-type').value,event.target.value)[0];
  if (page) loadPage(page);
});
$('page-select').addEventListener('change', event => {
  const page = state.pages.find(item => item.id === event.target.value);
  if (page) loadPage(page);
});
for (const [id, offset] of [['previous-page', -1], ['next-page', 1]]) $(id).addEventListener('click', () => {
  const page = adjacentPage(groupedPages(state.pages,state.page?.type), state.page?.id, offset);
  if (page) loadPage(page);
});
$('page-search').addEventListener('input', filterPages);
$('section-filter').addEventListener('change', filterPages);
$('page-search').addEventListener('keydown', event => {
  if (event.key === 'ArrowDown') { event.preventDefault();$('page-results').querySelector('button')?.focus(); }
  if (event.key === 'Enter') { event.preventDefault();$('page-results').querySelector('button')?.click(); }
});
$('page-results').addEventListener('keydown', event => {
  if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
  const buttons = [...$('page-results').querySelectorAll('button')];
  const index = buttons.indexOf(document.activeElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : clamp(index + (event.key === 'ArrowDown' ? 1 : -1), 0, buttons.length - 1);
  buttons[next]?.focus();event.preventDefault();
});
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => $(button.dataset.close).close());
for (const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click', event => {
  const box = dialog.getBoundingClientRect();
  if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
});
$('zoom-in').addEventListener('click', () => zoomBy(1.25));
$('zoom-out').addEventListener('click', () => zoomBy(1 / 1.25));
$('fit-width').addEventListener('click', () => fit('fit-width'));
$('zoom').addEventListener('change', event => {
  const value = event.target.value;
  if (value.startsWith('fit-')) fit(value);
  else { state.view.mode = 'manual';state.view.zoom = Number(value);layout(); }
});
$('appearance').addEventListener('click', () => { updateAppearanceControls();$('appearance-dialog').showModal(); });
$('weight').addEventListener('change', event => setWeight(event.target.value));
for (const [id,key] of [['stretch-x','stretchX'],['stretch-y','stretchY']]) $(id).addEventListener('input', event => {
  state.view[key] = Number(event.target.value) / 100;
  layout();remember();
});
$('reset-appearance').addEventListener('click', async () => {
  state.view.stretchX = state.view.stretchY = 1;
  await setWeight(800);layout();remember();
});
viewport.addEventListener('wheel', event => {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  const rect = viewport.getBoundingClientRect();
  zoomBy(Math.exp(-event.deltaY * 0.002), { x: event.clientX - rect.left, y: event.clientY - rect.top });
}, { passive: false });
viewport.addEventListener('pointerdown', event => {
  if (event.button !== 1 && !(event.button === 0 && state.space)) return;
  event.preventDefault();
  state.pan = { pointer: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
  viewport.setPointerCapture(event.pointerId);viewport.classList.add('panning');
});
viewport.addEventListener('pointermove', event => {
  if (state.pan?.pointer === event.pointerId) viewport.scrollTo(state.pan.left - event.clientX + state.pan.x, state.pan.top - event.clientY + state.pan.y);
});
const endPan = () => { state.pan = null;viewport.classList.remove('panning'); };
viewport.addEventListener('pointerup', endPan);viewport.addEventListener('pointercancel', endPan);viewport.addEventListener('lostpointercapture', endPan);
document.addEventListener('keydown', event => {
  if (editable(event.target) || document.querySelector('dialog[open]')) return;
  if (event.key === ' ' && !event.repeat) { state.space = true;viewport.classList.add('can-pan');event.preventDefault(); }
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  if (['+','='].includes(event.key)) { event.preventDefault();zoomBy(1.25); }
  if (event.key === '-') { event.preventDefault();zoomBy(1 / 1.25); }
  if (event.key === '0') { event.preventDefault();fit('fit-width'); }
  if (event.key === '1') { state.view.mode = 'manual';state.view.zoom = 1;layout(); }
  if (['p','P','/'].includes(event.key)) { event.preventDefault();choosePage(); }
});
document.addEventListener('keyup', event => { if (event.key === ' ') { state.space = false;viewport.classList.remove('can-pan'); } });
window.addEventListener('blur', () => { state.space = false;viewport.classList.remove('can-pan');endPan(); });
let resizePending = false;
new ResizeObserver(() => {
  if (resizePending) return;
  resizePending = true;requestAnimationFrame(() => { resizePending = false;layout(); });
}).observe(viewport);
window.addEventListener('popstate', () => {
  const query = new URL(location.href).searchParams.get('page');
  const page = resolvePage(state.pages, query);
  if (page) loadPage(page, 'none',readSelection());else choosePage(query || '');
});

async function start() {
  updateAppearanceControls();
  try {
    const response = await fetch(catalogueURL, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`The page catalogue could not be loaded (${response.status}).`);
    const catalogue = await response.json();
    if (!Array.isArray(catalogue.pages) || !catalogue.pages.length) throw new Error('The page catalogue is empty.');
    state.pages = catalogue.pages;
    const sections = [...new Set(state.pages.map(page => page.section))].sort((a,b) => a.localeCompare(b, undefined, { numeric: true }));
    for (const section of sections) { const option = document.createElement('option');option.value = section;option.textContent = section;$('section-filter').append(option); }
    const query = new URL(location.href).searchParams.get('page');
    const initial = resolvePage(state.pages, query) || resolvePage(state.pages, catalogue.defaultPage || catalogue.default_page || 'AP154') || state.pages[0];
    await loadPage(initial, 'replace',readSelection());
    if (query && !resolvePage(state.pages, query)) choosePage(query);
  } catch (error) {
    $('empty-state').querySelector('p').textContent = 'The diagram collection could not be opened.';
    notify(error.message, true, () => location.reload());
  }
}
start();
