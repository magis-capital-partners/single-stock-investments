// Initial score timing comes from immutable decisions, never a later rescore.
export function decisionTiming(db,event,now=new Date().toISOString()){
 const received=Date.parse(event.first_seen_at);if(!Number.isFinite(received))return {first_analysis_at:null,first_scored_at:null,receipt_to_analysis_seconds:null,receipt_to_filters_seconds:null,first_scored_decision_id:null};
 const first=db.prepare('SELECT id,recorded_at FROM rs_decisions WHERE event_id=? AND recorded_at>=? AND recorded_at<=? ORDER BY recorded_at,id LIMIT 1').get(event.id,event.first_seen_at,now);
 const scored=db.prepare("SELECT id,recorded_at FROM rs_decisions WHERE event_id=? AND recorded_at>=? AND recorded_at<=? AND json_type(payload,'$.financials.score') IN ('integer','real') AND coalesce(json_extract(payload,'$.financials.signal_count'),0)>=3 AND json_extract(payload,'$.metadata_error') IS NULL ORDER BY recorded_at,id LIMIT 1").get(event.id,event.first_seen_at,now);
 const seconds=row=>row?(Date.parse(row.recorded_at)-received)/1000:null;
 return {first_analysis_at:first?.recorded_at||null,first_scored_at:scored?.recorded_at||null,receipt_to_analysis_seconds:seconds(first),receipt_to_filters_seconds:seconds(scored),first_scored_decision_id:scored?.id||null};
}
