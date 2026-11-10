// Presentation/evidence classification only; never changes a registered gate.
export function financialAssessment(event){
 const f=event.financials||{},issuer=f.issuer_financials||f,min=event.policy?.minimum_score??60,needed=event.policy?.minimum_signals??3;
 const score=issuer.score,count=issuer.signal_count??Object.keys(issuer.signals||{}).length,excluded=f.status==='instrument_not_in_operating_company_strategy';
 const base={score:Number.isFinite(score)?score:null,signal_count:count,minimum_score:min,minimum_signals:needed,period:issuer.period||f.period||null,instrument_eligible:!excluded,changes_strategy:false};
 if(!Number.isFinite(score)||count<needed){const reason=issuer.status==='stale_or_missing_period'?`Latest usable period ${base.period||'unknown'} is stale or missing.`:issuer.status==='financial_source_conflict'?'Primary financial sources conflict; review required.':`${count} supported factors; ${needed} are required for a usable score.`;return {...base,status:'missing_data',label:'Financial data needed',reason,data_ready:false};}
 if(excluded)return {...base,status:'instrument_excluded',label:'Issuer scored; instrument excluded',reason:`Issuer score ${score}; this security type is outside the registered common-share strategy.`,financial_result:score<min?'below_threshold':'meets_threshold',data_ready:true};
 if(score<min)return {...base,status:'financial_rejection',label:'Financial filter not met',reason:`Score ${score} is below ${min}, using ${count} supported factors.`,data_ready:true};
 return {...base,status:'meets_financial_filter',label:'Meets financial filter',reason:'Other announcement, prior-split, quote and broker requirements still apply.',data_ready:true};
}
