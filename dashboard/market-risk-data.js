/* Observation-date reconciliation: transport success is not freshness. */
(function(global){
  'use strict';
  const time=v=>{const t=Date.parse(v || '');return Number.isFinite(t)?t:-Infinity;};
  const key=r=>[r.component,r.scope,r.symbol].join(':');
  function components(api=[],fallback=[]){
    const rows=new Map();
    for(const [origin,list] of [['committed',fallback],['api',api]])for(const row of list || []){
      if(!row?.component || !row?.scope || !row?.symbol)continue;
      const old=rows.get(key(row));
      // A timestamp-less row cannot supersede a real dated observation.
      if(!old || time(row.as_of)>time(old.as_of) || time(row.as_of)===time(old.as_of) && origin==='api')rows.set(key(row),{...row,delivery_origin:origin});
    }
    return [...rows.values()];
  }
  function merge(api,fallback,stack){
    const output={...(fallback || {}),...(api || {})};
    const bySymbol={};
    for(const source of [fallback,api]){
      const candidates=[...(source?.market || []),...(source?.sectors || []),...Object.values(source?.by_symbol || {})];
      if(source?.symbol)candidates.push(source);
      for(const row of candidates)if(row?.symbol && (!bySymbol[row.symbol] || time(row.as_of)>time(bySymbol[row.symbol].as_of)))bySymbol[row.symbol]=row;
    }
    if(Object.keys(bySymbol).length){output.by_symbol=bySymbol;output.market=Object.values(bySymbol).filter(r=>r.scope==='market');output.sectors=Object.values(bySymbol).filter(r=>r.scope==='sector');}
    output.components=components(api?.components,stack?.components || fallback?.components);
    output.reconciliation=stack?.reconciliation || api?.reconciliation || null;
    output.expected_session=global.MarketSessions?.completed() || stack?.expected_session || api?.expected_session || null;
    output.release_stage=stack?.release_stage || api?.release_stage || null;
    return output;
  }
  function summary(payload){
    const rows=(payload?.components || []).filter(r=>r.scope==='market' && r.component!=='observed_vol_target_flows');
    const expected=payload?.expected_session;
    const current=rows.filter(r=>expected && r.session_date===expected && !['stale','unavailable','lagging'].includes(r.quality_state));
    return {session:expected,current:current.length,total:rows.length,pending:rows.length-current.length};
  }
  global.MarketRiskData={components,merge,summary};
})(window);
