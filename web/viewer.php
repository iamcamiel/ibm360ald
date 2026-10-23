<?php
declare(strict_types=1);
$aldAssetPrefix = $aldAssetPrefix ?? 'assets/';
$aldCatalogue = $aldCatalogue ?? 'data/catalogue.json';
$aldAssetPrefixHtml = htmlspecialchars($aldAssetPrefix, ENT_QUOTES, 'UTF-8');
$aldStyleVersion = hash_file('sha256', __DIR__ . '/assets/browser.css');
header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'");
header('Cache-Control: no-cache');
?>
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Explore IBM System/360 Automated Logic Diagrams as selectable, searchable UTF-8 text.">
  <meta name="theme-color" content="#182732">
  <meta name="ald-catalogue" content="<?= htmlspecialchars($aldCatalogue, ENT_QUOTES, 'UTF-8') ?>">
  <title>ALDbrowser · VAXBARN</title>
  <link rel="preload" href="<?= $aldAssetPrefixHtml ?>fonts/JuliaMono-ExtraBold.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="<?= $aldAssetPrefixHtml ?>browser.css?v=<?= $aldStyleVersion ?>">
  <script type="module" src="<?= $aldAssetPrefixHtml ?>module.php?file=browser.js"></script>
</head>
<body>
  <header class="ribbon">
    <a class="brand" href="https://www.vaxbarn.com/" title="VAXBARN home" aria-label="VAXBARN home"><img src="<?= $aldAssetPrefixHtml ?>vaxbarn.svg" alt="VAXBARN" width="149" height="22"></a>
    <div class="app-name">ALD<span>browser</span></div>
    <span class="ribbon-divider" aria-hidden="true"></span>
    <div class="page-navigation" aria-label="Page navigation">
      <button id="previous-page" class="icon-button" title="Previous page" aria-label="Previous page" disabled><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12 4-6 6 6 6"/></svg></button>
      <button id="next-page" class="icon-button" title="Next page" aria-label="Next page" disabled><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 4 6 6-6 6"/></svg></button>
    </div>
    <div id="choose-page" class="page-selectors" role="group" aria-label="Choose a page">
      <label>Page type<select id="page-type" aria-label="Page type" disabled><option>Loading…</option></select></label>
      <label><span id="section-label">Section</span><select id="page-section" aria-labelledby="section-label" disabled><option>Loading…</option></select></label>
      <label><span id="page-label">Page</span><select id="page-select" aria-labelledby="page-label" disabled><option>Loading…</option></select></label>
      <span id="current-page" hidden>Choose a page</span><span id="current-title" hidden></span>
    </div>
    <span id="page-approved" class="approval-mark" hidden role="img" aria-label="Approved by you" title="Approved by you">✓</span>
    <div class="view-tools" aria-label="Page zoom">
      <button id="zoom-out" class="icon-button" title="Zoom out (−)" aria-label="Zoom out"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12"/></svg></button>
      <select id="zoom" aria-label="Zoom level">
        <option value="current" disabled>Fit width</option>
        <option value="fit-width">Fit width</option>
        <option value="fit-page">Fit page</option>
        <option value="0.25">25%</option><option value="0.5">50%</option><option value="0.75">75%</option>
        <option value="1">100%</option><option value="1.5">150%</option><option value="2">200%</option><option value="3">300%</option><option value="4">400%</option>
      </select>
      <button id="zoom-in" class="icon-button" title="Zoom in (+)" aria-label="Zoom in"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10h12M10 4v12"/></svg></button>
      <button id="fit-width" class="fit-button" title="Fit page width (0)">Fit width</button>
    </div>
    <div class="download-tools" aria-label="Download current page">
      <a id="download-txt" role="link" aria-label="Download TXT" aria-disabled="true" tabindex="-1">.TXT</a>
      <a id="download-json" role="link" aria-label="Download JSON" aria-disabled="true" tabindex="-1">.JSON</a>
    </div>
    <span class="ribbon-divider tool-divider" aria-hidden="true"></span>
    <button id="appearance" class="appearance-button" aria-haspopup="dialog" title="Font weight and proportions"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M3 15h14M7 2v6M13 12v6M3 10h14M13 7v6"/></svg><span>Appearance</span></button>
  </header>

  <div class="page-context"><span id="current-section">IBM System/360</span><button id="clear-selection" class="selection-chip" hidden><span id="selection-name"></span><span aria-hidden="true"> ×</span></button><span class="context-rule"></span><span id="view-summary">JuliaMono ExtraBold</span></div>
  <main id="viewport" tabindex="0" aria-label="ALD page viewer; scroll to explore the page">
    <div id="stage">
      <article id="sheet" aria-label="ALD text page" hidden><div id="sheet-inner"><div id="selection-overlay" aria-hidden="true"></div><pre id="ald-text" translate="no" aria-label="Diagram text"></pre></div></article>
    </div>
    <div id="empty-state"><span class="empty-monogram" aria-hidden="true">ALD</span><p>Opening the diagram collection…</p></div>
  </main>
  <div id="notice" class="notice" role="status" aria-live="polite" hidden><span id="notice-text"></span><button id="retry" hidden>Try again</button></div>
  <div id="selection-menu" class="selection-menu" role="menu" aria-label="Diagram links" tabindex="-1" hidden></div>

  <dialog id="page-dialog" aria-labelledby="page-dialog-title">
    <div class="dialog-heading"><div><span class="eyebrow">VAXBARN / SYSTEM·360</span><h1 id="page-dialog-title">Choose a page</h1></div><button class="close-dialog icon-button" aria-label="Close page menu" data-close="page-dialog">×</button></div>
    <div class="page-filters"><label class="search-field"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg><input id="page-search" type="search" placeholder="Page number, title or section" aria-label="Search pages" autocomplete="off" spellcheck="false"></label><select id="section-filter" aria-label="Filter by section"><option value="">All sections</option></select></div>
    <div class="results-heading"><span id="result-count"></span><span>↑ ↓ to browse · Enter to open</span></div>
    <div id="page-results" role="region" aria-label="Matching pages"></div>
  </dialog>

  <dialog id="appearance-dialog" aria-labelledby="appearance-title">
    <div class="dialog-heading"><div><span class="eyebrow">MAKE YOURSELF COMFORTABLE</span><h2 id="appearance-title">Type &amp; proportions</h2></div><button class="close-dialog icon-button" aria-label="Close appearance settings" data-close="appearance-dialog">×</button></div>
    <label class="setting-row"><span>Font weight</span><select id="weight"><option value="300">300 · Light</option><option value="400">400 · Regular</option><option value="500">500 · Medium</option><option value="600">600 · Semibold</option><option value="700">700 · Bold</option><option value="800" selected>800 · ExtraBold</option><option value="900">900 · Black</option></select></label>
    <div class="setting-slider"><label for="stretch-x">Width <output id="stretch-x-value" for="stretch-x">100%</output></label><input id="stretch-x" type="range" min="60" max="160" step="1" value="100"></div>
    <div class="setting-slider"><label for="stretch-y">Height <output id="stretch-y-value" for="stretch-y">100%</output></label><input id="stretch-y" type="range" min="60" max="160" step="1" value="100"></div>
    <p class="setting-note">100% uses the original ALD proportions. Your preferences are remembered in this browser.</p>
    <button id="reset-appearance" class="reset-button">Restore original proportions &amp; weight</button>
  </dialog>
  <noscript>Enable JavaScript to choose, zoom and scroll the UTF-8 pages in ALDbrowser.</noscript>
</body>
</html>
