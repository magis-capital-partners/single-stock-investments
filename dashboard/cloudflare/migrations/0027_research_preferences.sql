-- Viewer-scoped saved charts, scenarios, screens, imports and in-app alert rules.
CREATE TABLE IF NOT EXISTS research_preferences (
  viewer_email TEXT NOT NULL,
  preference_key TEXT NOT NULL,
  value_json TEXT NOT NULL CHECK(length(value_json) <= 524288),
  revision INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY (viewer_email, preference_key)
);
CREATE TABLE IF NOT EXISTS research_alert_events (
  viewer_email TEXT NOT NULL,
  event_key TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  ticker TEXT NOT NULL,
  metric TEXT NOT NULL,
  observed_value REAL NOT NULL,
  unit TEXT,
  period TEXT NOT NULL,
  filed TEXT,
  note TEXT,
  release_sha256 TEXT NOT NULL,
  triggered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  read_at TEXT,
  PRIMARY KEY (viewer_email, event_key)
);
CREATE INDEX IF NOT EXISTS research_alert_inbox ON research_alert_events(viewer_email, triggered_at DESC);
