#!/usr/bin/env node
/** Node test runner for dashboard/search-match.js against document_catalog.json */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const SearchMatch = require(path.join(ROOT, 'dashboard', 'search-match.js'));

function loadCatalog() {
  const catalogPath = path.join(ROOT, 'dashboard', 'data', 'document_catalog.json');
  return JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
}

function countMatches(query, catalog) {
  const known = SearchMatch.catalogKnownTickers(catalog);
  const docs = catalog.documents || [];
  const matches = docs.filter(d => SearchMatch.matchDocumentCatalogRow(d, query, known));
  return {
    total: matches.length,
    tpl: matches.filter(d => String(d.ticker || '').toUpperCase() === 'TPL').length,
    jpx_false_positive: matches.filter(d => String(d.ticker || '') === '8697.T' && query === 'tpl').length,
    tickers: [...new Set(matches.map(d => d.ticker).filter(Boolean))].sort(),
  };
}

function topRanked(query, catalog) {
  const known = SearchMatch.catalogKnownTickers(catalog);
  const rows = (catalog.documents || []).filter(d => SearchMatch.matchDocumentCatalogRow(d, query, known));
  rows.sort((a, b) => SearchMatch.documentCatalogMatchScore(b, query, known)
    - SearchMatch.documentCatalogMatchScore(a, query, known));
  const top = rows[0] || null;
  return {
    top_ticker: top?.ticker || null,
    top_score: top ? SearchMatch.documentCatalogMatchScore(top, query, known) : 0,
  };
}

function main() {
  const action = process.argv[2] || 'count';
  const query = process.argv[3] || '';
  const catalog = loadCatalog();
  if (action === 'known') {
    console.log(JSON.stringify(SearchMatch.catalogKnownTickers(catalog)));
    return;
  }
  if (action === 'rank') {
    console.log(JSON.stringify(topRanked(query, catalog)));
    return;
  }
  console.log(JSON.stringify(countMatches(query, catalog)));
}

main();
