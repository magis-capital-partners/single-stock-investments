-- Securities and themes resolved from published fund-letter ideas. Rows are keyed by the rule
-- version that produced them, so a release never rewrites an accepted row: fl_settings names the
-- current versions, and the two views show only those rows. A mention that is not resolved to a
-- security is stored as 'unresolved' and is never matched or counted.
CREATE TABLE IF NOT EXISTS fl_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS fl_idea_entities (
  resolver TEXT NOT NULL, revision_id TEXT NOT NULL, idea_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
  mention TEXT NOT NULL, ticker TEXT, exchange TEXT, name TEXT, status TEXT NOT NULL, reason TEXT,
  PRIMARY KEY(resolver, revision_id, idea_id, ordinal)
);
CREATE INDEX IF NOT EXISTS fl_idea_entities_ticker ON fl_idea_entities(resolver, status, ticker, revision_id, idea_id);
CREATE TABLE IF NOT EXISTS fl_idea_themes (
  theme_set TEXT NOT NULL, revision_id TEXT NOT NULL, idea_id TEXT NOT NULL, theme TEXT NOT NULL,
  PRIMARY KEY(theme_set, revision_id, idea_id, theme)
);
CREATE VIEW IF NOT EXISTS fl_idea_tickers AS
  SELECT revision_id, idea_id, ordinal, ticker, exchange, name FROM fl_idea_entities
  WHERE status='resolved' AND resolver=(SELECT value FROM fl_settings WHERE key='entity_resolver');
CREATE VIEW IF NOT EXISTS fl_themed_ideas AS
  SELECT revision_id, idea_id, theme FROM fl_idea_themes
  WHERE theme_set=(SELECT value FROM fl_settings WHERE key='idea_themes');
