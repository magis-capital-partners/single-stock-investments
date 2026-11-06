-- Fallback SQL paths only; normal dashboard history is served from private R2 pages.
CREATE INDEX IF NOT EXISTS rs_shadow_policy_recent ON rs_shadow_tracks(policy_id,enrolled_at DESC,id);
CREATE INDEX IF NOT EXISTS rs_shadow_state_policy_recent ON rs_shadow_tracks(state,policy_id,enrolled_at DESC,id);
CREATE INDEX IF NOT EXISTS rs_execution_policy_id ON rs_execution_tracks(policy_id,id);
