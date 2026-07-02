/** Shared Insights / PDF library search matching (browser + Node). */
(function (global) {
  const TOKEN_SPLIT = /[^a-zA-Z0-9]+/;
  const DOCUMENT_TEXT_FIELDS = [
    'ticker',
    'title',
    'source_label',
    'source_type',
    'quarter',
    'period_label',
    'document_date',
  ];

  function normalizeQuery(q) {
    return String(q || '').trim().toLowerCase();
  }

  function tokenize(text) {
    return String(text || '')
      .toLowerCase()
      .split(TOKEN_SPLIT)
      .filter(Boolean);
  }

  function tokenContains(text, q) {
    const query = normalizeQuery(q);
    if (!query) return true;
    return tokenize(text).includes(query);
  }

  function tickerFieldMatches(ticker, q) {
    const t = String(ticker || '').toLowerCase();
    const query = normalizeQuery(q);
    if (!query || !t) return false;
    if (t === query) return true;
    return t.startsWith(query) && query.length >= 2;
  }

  function catalogKnownTickers(catalog) {
    if (Array.isArray(catalog?.known_tickers) && catalog.known_tickers.length) {
      return catalog.known_tickers.map(t => String(t).toUpperCase());
    }
    const byTicker = catalog?.summary?.by_ticker || {};
    return Object.keys(byTicker).map(t => String(t).toUpperCase());
  }

  function buildKnownTickerSet(knownTickers) {
    return new Set((knownTickers || []).map(t => String(t).toUpperCase()));
  }

  function isTickerQuery(q, knownTickers) {
    const query = normalizeQuery(q);
    if (!query || query.includes(' ')) return false;
    const known = buildKnownTickerSet(knownTickers);
    if (known.has(query.toUpperCase())) return true;
    if (query.length < 2) return false;
    for (const ticker of known) {
      if (ticker.toLowerCase().startsWith(query)) return true;
    }
    return false;
  }

  function textHaystack(record, fields) {
    return (fields || [])
      .map(field => String(record?.[field] || ''))
      .join(' ')
      .toLowerCase();
  }

  function arrayFieldMatches(values, q, knownTickers) {
    const query = normalizeQuery(q);
    if (!query) return true;
    const list = values || [];
    if (isTickerQuery(query, knownTickers)) {
      return list.some(value => tickerFieldMatches(value, query) || tokenContains(value, query));
    }
    return list.some(value => String(value || '').toLowerCase().includes(query));
  }

  function matchTextRecord(record, q, opts) {
    const query = normalizeQuery(q);
    if (!query) return true;
    const {
      knownTickers = [],
      fields = [],
      tickerField = 'ticker',
      titleField = 'title',
      arrayFields = [],
    } = opts || {};

    if (isTickerQuery(query, knownTickers)) {
      if (tickerFieldMatches(record?.[tickerField], query)) return true;
      if (tokenContains(record?.[titleField], query)) return true;
      return arrayFields.some(name => arrayFieldMatches(record?.[name], query, knownTickers));
    }

    if (query.includes(' ')) {
      return textHaystack(record, fields).includes(query);
    }

    if (tokenContains(record?.[tickerField], query)) return true;
    for (const field of fields) {
      if (field === tickerField) continue;
      const value = record?.[field];
      if (Array.isArray(value)) {
        if (arrayFieldMatches(value, query, knownTickers)) return true;
      } else if (String(value || '').toLowerCase().includes(query)) {
        return true;
      }
    }
    for (const name of arrayFields) {
      if (arrayFieldMatches(record?.[name], query, knownTickers)) return true;
    }
    return false;
  }

  function matchDocumentCatalogRow(row, q, knownTickers) {
    return matchTextRecord(row, q, {
      knownTickers,
      fields: DOCUMENT_TEXT_FIELDS,
      tickerField: 'ticker',
      titleField: 'title',
    });
  }

  function documentCatalogMatchScore(row, q, knownTickers) {
    const query = normalizeQuery(q);
    if (!query) return 0;
    const ticker = String(row?.ticker || '').toLowerCase();
    if (ticker === query) return 100;
    if (tickerFieldMatches(row?.ticker, query)) return 80;
    if (tokenContains(row?.title, query)) return 60;
    if (textHaystack(row, DOCUMENT_TEXT_FIELDS).includes(query)) return 40;
    return 0;
  }

  function matchEvent(event, q, knownTickers) {
    return matchTextRecord(event, q, {
      knownTickers,
      fields: ['ticker', 'title', 'summary', 'source_label', 'source', 'impact_axis'],
      tickerField: 'ticker',
      titleField: 'title',
    });
  }

  function matchTickerEssential(tickerRow, q, knownTickers) {
    const essentials = tickerRow?.essential_insights || {};
    const synthetic = {
      ticker: tickerRow?.ticker,
      company: tickerRow?.company,
      status_label: essentials.status?.label,
      source_mix: (essentials.source_mix || []).join(' '),
      bullets: (essentials.bullets || [])
        .map(b => `${b.title || ''} ${b.summary || ''}`)
        .join(' '),
    };
    return matchTextRecord(synthetic, q, {
      knownTickers,
      fields: ['ticker', 'company', 'status_label', 'source_mix', 'bullets'],
      tickerField: 'ticker',
      titleField: 'company',
    });
  }

  function matchLetterIndexRow(row, q, knownTickers) {
    const query = normalizeQuery(q);
    if (!query) return true;
    if (String(row?.fund || '').toLowerCase().includes(query)) return true;
    if (isTickerQuery(query, knownTickers)) {
      if ((row?.tickers || []).some(t => tickerFieldMatches(t, query))) return true;
      if ((row?.our_overlap || []).some(t => tickerFieldMatches(t, query))) return true;
      return (row?.themes || []).some(t => tokenContains(t, query));
    }
    if ((row?.tickers || []).some(t => String(t || '').toLowerCase().includes(query))) return true;
    if ((row?.our_overlap || []).some(t => String(t || '').toLowerCase().includes(query))) return true;
    return (row?.themes || []).some(t => String(t || '').toLowerCase().includes(query));
  }

  function matchConsensusRow(row, q, knownTickers) {
    return matchTextRecord(row, q, {
      knownTickers,
      fields: ['ticker', 'name', 'fund'],
      tickerField: 'ticker',
      titleField: 'name',
    });
  }

  function matchMemoryClaim(row, q, knownTickers) {
    return matchTextRecord(row, q, {
      knownTickers,
      fields: ['ticker', 'claim', 'claim_type', 'source_title', 'source_type'],
      tickerField: 'ticker',
      titleField: 'claim',
    });
  }

  function matchFundRegistryRow(row, q, knownTickers) {
    return matchTextRecord(row, q, {
      knownTickers,
      fields: ['fund'],
      tickerField: 'fund',
      titleField: 'fund',
      arrayFields: ['our_tickers', 'themes'],
    });
  }

  const SearchMatch = {
    normalizeQuery,
    tokenize,
    tokenContains,
    tickerFieldMatches,
    catalogKnownTickers,
    isTickerQuery,
    textHaystack,
    matchTextRecord,
    matchDocumentCatalogRow,
    documentCatalogMatchScore,
    matchEvent,
    matchTickerEssential,
    matchLetterIndexRow,
    matchConsensusRow,
    matchMemoryClaim,
    matchFundRegistryRow,
    DOCUMENT_TEXT_FIELDS,
  };

  global.SearchMatch = SearchMatch;
  if (typeof module !== 'undefined') module.exports = SearchMatch;
})(typeof window !== 'undefined' ? window : global);
