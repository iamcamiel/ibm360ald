export const FONT_SIZE = 34;
export const PAPER_PADDING = 48;
export const STAGE_PADDING = 24;
export const WEIGHTS = [300, 400, 500, 600, 700, 800, 900];
export const PAGE_TYPES = [
  ['ald','ALD'], ['socket-listing','Socket Listing'], ['cas','CAS'],
  ['ros-listing','ROS Listing'], ['card-ald','SLT Card Diagram'], ['miscellaneous','Miscellaneous'],
];
export const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

export function sentenceCase(value = '') {
  return value.toLocaleLowerCase('en').replace(/\p{L}/u, letter => letter.toLocaleUpperCase('en'));
}
export const pageCode = page => page.displayPage || page.page;
export const pageTitle = page => sentenceCase(page.displayTitle || page.title);

export function pageCaption(page) {
  const section = page.section === 'Card ALD' ? page.section : page.section.replace(/^(\S+\s+)(.*)$/u, (_, prefix, title) => prefix + sentenceCase(title));
  return `${section} :: ${pageCode(page)} ${pageTitle(page)}`;
}

export const pageGroup = page => page.type === 'card-ald' ? page.cardType : page.section;

export function groupedPages(pages, type, group) {
  return pages.filter(page => page.type === type && (group === undefined || pageGroup(page) === group));
}

export function pageGroups(pages, type) {
  return [...new Set(groupedPages(pages, type).map(pageGroup))]
    .sort((a,b) => a.localeCompare(b,'en',{numeric:true}));
}

export function adjacentPage(pages, currentID, offset) {
  const index = pages.findIndex(page => page.id === currentID);
  return index < 0 ? null : pages[index + offset] || null;
}

export function preferences(value = {}) {
  if (!value || typeof value !== 'object') value = {};
  const number = (v, fallback) => v !== null && Number.isFinite(Number(v)) ? Number(v) : fallback;
  return {
    weight: WEIGHTS.includes(Number(value.weight)) ? Number(value.weight) : 800,
    stretchX: clamp(number(value.stretchX, 1), 0.6, 1.6),
    stretchY: clamp(number(value.stretchY, 1), 0.6, 1.6),
  };
}

export function countGrid(text) {
  const lines = text.replace(/^\uFEFF/, '').split(/\r\n|\n|\r/);
  if (lines.at(-1) === '') lines.pop();
  return { rows: Math.max(1, lines.length), columns: Math.max(1, ...lines.map(line => [...line].length)) };
}

export function geometry(page, view, viewport) {
  const columnPitch = Number(page.grid?.columnPitch) || 20;
  const rowPitch = Number(page.grid?.rowPitch) || 30;
  const baseWidth = page.columns * columnPitch + 2 * PAPER_PADDING;
  const baseHeight = page.rows * rowPitch + 2 * PAPER_PADDING;
  let zoom = view.zoom;
  const widthZoom = (viewport.width - 2 * STAGE_PADDING) / (baseWidth * view.stretchX);
  const heightZoom = (viewport.height - 2 * STAGE_PADDING) / (baseHeight * view.stretchY);
  if (view.mode === 'fit-width') zoom = widthZoom;
  if (view.mode === 'fit-page') zoom = Math.min(widthZoom, heightZoom);
  zoom = clamp(zoom, 0.05, 6);
  const scaleX = zoom * view.stretchX;
  const scaleY = zoom * view.stretchY;
  const width = baseWidth * scaleX;
  const height = baseHeight * scaleY;
  const stageWidth = Math.max(viewport.width, width + 2 * STAGE_PADDING);
  const stageHeight = Math.max(viewport.height, height + 2 * STAGE_PADDING);
  return { zoom, columnPitch, rowPitch, baseWidth, baseHeight, scaleX, scaleY, width, height, stageWidth, stageHeight, left: (stageWidth - width) / 2, top: STAGE_PADDING };
}

export function anchoredScroll(old, next, scroll, anchor) {
  if (!old) return { left: 0, top: 0 };
  const x = (scroll.left + anchor.x - old.left) / old.scaleX;
  const y = (scroll.top + anchor.y - old.top) / old.scaleY;
  return { left: Math.max(0, x * next.scaleX + next.left - anchor.x), top: Math.max(0, y * next.scaleY + next.top - anchor.y) };
}

export function resolvePage(pages, query) {
  if (!query) return null;
  const byID = pages.find(page => page.id === query);
  if (byID) return byID;
  const qualified = pages.filter(page => pageCode(page).toUpperCase() === query.toUpperCase());
  if (qualified.length === 1) return qualified[0];
  const matches = pages.filter(page => page.page.toUpperCase() === query.toUpperCase());
  return matches.length === 1 ? matches[0] : null;
}
