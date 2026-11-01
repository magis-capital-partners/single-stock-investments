'use strict';
const I=require('./identity.cjs');
function event(ctx,c,horizon=20){
 if(!c?.day)return {status:'missing_entry_session'};
 const index=ctx.prices.index.get(c.day),end=ctx.prices.days[index+horizon-1];
 if(!end)return {status:'immature'};
 const security=I.resolve(c,end);
 if(security.venue!=='NASDAQ')return {status:'venue_exit',resolved_ticker:security.ticker,source_urls:security.sources};
 const start=ctx.auction(I.resolve(c,c.day).ticker,c.day)?.open,exit=ctx.auction(security.ticker,end)?.close,factor=I.factor(ctx,c,end);
 if(!(factor>0))return {status:'corporate_action_conflict'};
 if(!(start>0&&exit>0))return {status:'missing_official_price',resolved_ticker:security.ticker,source_urls:security.sources};
 return {status:'observed_price_pair',return_on_initial_gross:1-exit/factor/start,resolved_ticker:security.ticker,source_urls:security.sources};
}
function summarize(rows){
 const returns=rows.filter(r=>r.status==='observed_price_pair').map(r=>r.return_on_initial_gross).sort((a,b)=>a-b),n=returns.length;
 return {purpose:'Price-only diagnostic, not executable profit. Complete price pairs are a selected subset; missing outcomes remain unknown.',events:rows.length,complete_price_pairs:n,missing_or_immature:rows.length-n,statuses:rows.reduce((a,r)=>(a[r.status]=(a[r.status]||0)+1,a),{}),mean_price_return:n?returns.reduce((a,b)=>a+b,0)/n:null,median_price_return:n?(returns[Math.floor((n-1)/2)]+returns[Math.floor(n/2)])/2:null,worst_price_return:n?returns[0]:null,borrow_verified:false,execution_verified:false};
}
module.exports={event,summarize};
