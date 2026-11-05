-- Public inventory is created by the collector itself, not re-imported from D1.
CREATE INDEX IF NOT EXISTS rs_shadow_evidence_kind_clock ON rs_shadow_evidence(kind,observed_at,id);
