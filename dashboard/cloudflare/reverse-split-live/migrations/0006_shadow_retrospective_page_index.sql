-- Dashboard retrospective pages filter by state and policy and sort by (enrolled_at DESC, id);
-- without this, D1 reads every retrospective track of every policy and sorts them on each poll.
CREATE INDEX IF NOT EXISTS rs_shadow_retrospective_page ON rs_shadow_tracks(state,policy_id,enrolled_at DESC,id);
