-- Private canonical archive. Only published revision fields enter reader responses.
CREATE TABLE IF NOT EXISTS fl_funds (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, manager TEXT NOT NULL DEFAULT '',
  strategy TEXT NOT NULL DEFAULT '', aliases_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS fl_letters (
  id TEXT PRIMARY KEY, fund_id TEXT NOT NULL REFERENCES fl_funds(id),
  content_hash TEXT NOT NULL, pipeline_version TEXT NOT NULL,
  reporting_period TEXT, letter_date TEXT, publication_date TEXT, ingested_at TEXT NOT NULL,
  date_source TEXT, source_ref TEXT, source_url TEXT, source_text TEXT NOT NULL DEFAULT '',
  alternate_sources_json TEXT NOT NULL DEFAULT '[]',
  published_revision TEXT, status TEXT NOT NULL DEFAULT 'pending',
  UNIQUE(fund_id, content_hash)
);
CREATE INDEX IF NOT EXISTS fl_letters_fund_date ON fl_letters(fund_id, letter_date DESC, reporting_period DESC, id);
CREATE TABLE IF NOT EXISTS fl_revisions (
  id TEXT PRIMARY KEY, letter_id TEXT NOT NULL REFERENCES fl_letters(id),
  created_at TEXT NOT NULL, published_at TEXT, author TEXT NOT NULL, status TEXT NOT NULL,
  overview TEXT NOT NULL, content_json TEXT NOT NULL, checks_json TEXT NOT NULL,
  previous_revision TEXT REFERENCES fl_revisions(id), release_id TEXT
);
CREATE INDEX IF NOT EXISTS fl_revision_letter ON fl_revisions(letter_id, created_at DESC);
CREATE TABLE IF NOT EXISTS fl_ideas (
  id TEXT NOT NULL, revision_id TEXT NOT NULL REFERENCES fl_revisions(id),
  letter_id TEXT NOT NULL REFERENCES fl_letters(id), title TEXT NOT NULL,
  ticker TEXT, idea_type TEXT NOT NULL, activity TEXT, summary TEXT NOT NULL,
  evolution TEXT, compared_letter_id TEXT, ordinal INTEGER NOT NULL,
  PRIMARY KEY(revision_id, id)
);
CREATE INDEX IF NOT EXISTS fl_idea_letter ON fl_ideas(letter_id, revision_id, ordinal);
CREATE TABLE IF NOT EXISTS fl_evidence (
  revision_id TEXT NOT NULL REFERENCES fl_revisions(id), idea_id TEXT NOT NULL,
  claims_json TEXT NOT NULL, PRIMARY KEY(revision_id, idea_id)
);
CREATE TABLE IF NOT EXISTS fl_sections (
  letter_id TEXT NOT NULL REFERENCES fl_letters(id), id TEXT NOT NULL,
  ordinal INTEGER NOT NULL, text TEXT NOT NULL, PRIMARY KEY(letter_id, id)
);
CREATE TABLE IF NOT EXISTS fl_reviews (
  letter_id TEXT NOT NULL REFERENCES fl_letters(id), kind TEXT NOT NULL,
  detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', PRIMARY KEY(letter_id, kind)
);
CREATE TABLE IF NOT EXISTS fl_releases (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, manifest_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fl_processing_cache (
  letter_id TEXT NOT NULL REFERENCES fl_letters(id), pipeline_version TEXT NOT NULL,
  stage TEXT NOT NULL, payload_json TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(letter_id,pipeline_version,stage)
);
CREATE TABLE IF NOT EXISTS fl_publication_events (
  id TEXT PRIMARY KEY, letter_id TEXT NOT NULL REFERENCES fl_letters(id),
  revision_id TEXT NOT NULL REFERENCES fl_revisions(id), previous_revision TEXT,
  author TEXT NOT NULL, created_at TEXT NOT NULL, action TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fl_publication_letter ON fl_publication_events(letter_id,created_at DESC);
