import { readVerifiedText } from './text-integrity.js';

// Refresh one entry before loading it. Retry a version mismatch only once,
// since the source can be replaced between metadata and text requests.
export async function readCurrentPage(initial, {catalogueURL, signal, fetcher = globalThis.fetch, crypto = globalThis.crypto}) {
  const base = new URL('.', catalogueURL);
  async function metadata(page) {
    if (!page.entryURL) return page;
    const url = new URL(page.entryURL, catalogueURL);
    if (url.origin !== catalogueURL.origin || url.pathname !== catalogueURL.pathname || url.searchParams.get('entry') !== page.id) throw new Error('Invalid page metadata URL.');
    const response = await fetcher(url, {signal, cache:'no-store'});
    if (!response.ok) throw new Error(`Page ${page.page} could not be refreshed (${response.status}).`);
    const fresh = await response.json();
    if (fresh.id !== page.id) throw new Error('The refreshed page identity did not match.');
    return fresh;
  }
  let page = await metadata(initial);
  for (let attempt = 0; attempt < 2; attempt++) {
    const url = new URL(page.url, catalogueURL);
    if (url.origin !== catalogueURL.origin || !url.pathname.startsWith(base.pathname) || !url.pathname.endsWith('.txt')) throw new Error('The selected page has an invalid text URL.');
    const response = await fetcher(url, {signal, cache:attempt ? 'reload':'default'});
    if (!response.ok) throw new Error(`Page ${page.page} could not be loaded (${response.status}).`);
    const verified = await readVerifiedText(await response.arrayBuffer(), page.textSha256, crypto);
    if (verified.interactionsAllowed || !page.entryURL || attempt === 1) return {page, verified};
    page = await metadata(page);
  }
}
