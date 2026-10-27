'use strict';
// Conditional one-second bar replay. No bar-derived quote or fill is presented as observed.
const {fee,above}=require('./replay.cjs');
const sum=xs=>xs.reduce((a,b)=>a+b,0),EPS=1e-8;
function gaps(s,start,end){
 if(!s)return ['session_missing'];const out=[...(s.data_gaps||[])];
 if(s.schema!=='third_plus_bar_session.v2')out.push('schema');
 if(s.synthetic)out.push('synthetic');
 if(!(s.capture_start_ms<=start&&s.capture_end_ms>=end))out.push('window');
 if(!s.source_hashes?.length||s.source_hashes.some(h=>!/^[a-f0-9]{64}$/.test(h)))out.push('source_hashes');
 // OHLC does not identify a spread. An absent/partial quote path is missing
 // evidence, not a no-fill and never permission to manufacture a bid and ask.
 const quotes=s.quotes||[];let i=0,q=null;
 if(!quotes.length)out.push('quote_history');
 else for(const b of s.bars||[]){
  const at=b[0]*1000;if(at<start||at>=end)continue;
  while(i<quotes.length&&quotes[i][0]*1000<=at)q=quotes[i++];
  if(!q||at-q[0]*1000>1000||!(q[1]>0&&q[2]>=q[1])){out.push('quote_history');break;}
 }
 return out;
}
function eligibleFraction(bar,limit){
 // Entire-bar clearance is a conservative scenario. A crossing range contains
 // no information about how much volume traded above our price or after ack.
 const [,,,low,,v]=bar;return v>0&&low>limit+EPS?1:0;
}
function replay(s,opt){
 const o={side:'sell',policy:'E2',participation:.1,latency_ms:500,child_usd:2000,target_usd:100000,capture:.5,cooldown_ms:5000,borrow_mode:'conditional',...opt};
 if(!['E0','E1','E2'].includes(o.policy)||!(o.participation>0&&o.participation<=.1)||!(o.capture>=0&&o.capture<=1)||!(o.end_ms>o.start_ms)||!(o.latency_ms>0))throw Error('Invalid bar sensitivity settings');
 const missing=gaps(s,o.start_ms,o.end_ms);if(missing.length)return {status:'data_missing',gaps:missing};
 if(o.borrow_mode==='verified')return {status:'data_missing',gaps:['borrow_history']};
 const cacheKey=JSON.stringify([o.side,o.policy,o.participation,o.latency_ms,o.child_usd,o.target_usd,o.quantity,o.capture,o.cooldown_ms,o.start_ms,o.end_ms,o.initial_price]);
 if(s._results?.has(cacheKey))return s._results.get(cacheKey);
 const bars=s.bars,quotes=s.quotes||[],states=s.statuses||[],fills=[],flow=[];
 let last=o.initial_price||null,qi=0,si=0,quote=null,restricted=s.opening_restricted!==0,trading=true;
 let volume=0,filled=0,fees=0,child=null,children=0,lastAction=-Infinity,target=o.quantity??null,arrival=null,reason=null,eligibleCarry=0;
 const reserved=()=>child?.remaining||0;
 function market(at){
  while(qi<quotes.length&&quotes[qi][0]*1000<=at)quote=quotes[qi++];
  while(si<states.length&&states[si].available_ms<=at){const z=states[si++];if(z.restricted==='Y'||z.restricted==='N')restricted=z.restricted==='Y';if(z.trading==='Y'||z.trading==='N')trading=z.trading==='Y';}
  if(quote&&quote[0]*1000<=at&&at-quote[0]*1000<=1000)return {bid:quote[1],ask:quote[2],mid:(quote[1]+quote[2])/2};
  return null;
 }
 function finish(){if(child?.filled)fees+=fee(child.filled,child.cash/child.filled,s.date,o.side==='sell');child=null;eligibleCarry=0;}
 function decide(at){
  const m=market(at);if(child?.cancel_at!==null&&child?.cancel_at<=at)finish();
  if(at>=o.end_ms){reason='deadline';if(child&&!child.cancel_at)child.cancel_at=o.end_ms+o.latency_ms;return;}
  if(!m||!trading){if(child&&!child.cancel_at)child.cancel_at=at+o.latency_ms;return;}
  if(target===null){arrival=m.mid;target=Math.floor(o.target_usd/arrival);}
  if(o.side==='sell'&&o.policy==='E0'&&restricted){reason='ssr_skip';return;}
  const tick=m.bid>=1?.01:.0001;
  const desired=o.side==='buy'?m.ask:o.policy==='E1'||!restricted?Math.max(m.ask,above(m.bid,tick)):above(m.bid,tick);
  if(child){
   const priceBlocked=o.side==='sell'&&restricted&&child.price<=m.bid+EPS;
   if(!child.cancel_at&&(priceBlocked||at-lastAction>=o.cooldown_ms&&Math.abs(desired-child.price)>EPS)){child.cancel_at=at+o.latency_ms;lastAction=at;}
   return;
  }
  if(filled>=target||at-lastAction<o.cooldown_ms)return;
  while(flow.length&&flow[0][0]<at-60000)flow.shift();
  const rollFilled=sum(fills.filter(f=>f.at_ms>=at-60000).map(f=>f.quantity));
  const available=Math.min(Math.floor(o.participation*volume)-filled,Math.floor(o.participation*sum(flow.map(x=>x[1])))-rollFilled);
  const cashRemaining=o.side==='buy'?Infinity:Math.floor((o.target_usd-sum(fills.map(f=>f.quantity*f.price)))/desired+EPS);
  const childShares=o.side==='buy'?Math.max(1,Math.floor(o.child_usd/desired)):Math.floor(o.child_usd/desired);
  const q=Math.min(target-filled,available,childShares,cashRemaining);
  if(q<1)return;
  child={id:'bar-child-'+(++children),price:desired,remaining:q,filled:0,cash:0,ack_at:at+o.latency_ms,cancel_at:null};lastAction=at;
 }
 for(const b of bars){
  const start=b[0]*1000,end=start+1000;
  if(end<=o.start_ms){last=b[4];continue;}
  if(start>o.end_ms+2*o.latency_ms+1000)break;
  decide(Math.max(start,o.start_ms));const m=market(start);
  const [t,op,high,low,close,v]=b;
  if(![op,high,low,close].every(x=>Number.isFinite(x)&&x>0)||!Number.isInteger(v)||v<0||low>Math.min(op,close)||high<Math.max(op,close))throw Error('Invalid actual bar');
  if(start>=o.start_ms&&trading){
   const permitted=o.side!=='sell'||!restricted||(o.policy!=='E0'&&child?.price>m?.bid+EPS);
   if(child&&child.ack_at<=start&&(!child.cancel_at||child.cancel_at>=end)&&m&&permitted){
    // The order was already live. Future bar range/volume determine an assumed execution, never admission.
    const eligible=o.side==='buy'?(high<child.price-EPS&&m.ask<=child.price+EPS?1:0):eligibleFraction(b,child.price);
    eligibleCarry+=o.participation*v*eligible*o.capture;
    const q=Math.min(child.remaining,Math.floor(eligibleCarry+EPS));
    if(q>0){
     eligibleCarry-=q;
     const price=child.price;
     fills.push({at_ms:end,quantity:q,price,limit_price:child.price,child_id:child.id,trade_id:'assumed-bar:'+t,side:o.side,evidence:'whole_bar_clearance_scenario'});
     child.remaining-=q;child.filled+=q;child.cash+=q*price;filled+=q;
     if(!child.remaining)finish();
    }
   }
   volume+=v;flow.push([end,v]);
  }
  last=close;decide(end);
  if(filled+reserved()>Math.floor(o.participation*volume+EPS)||target!==null&&filled+reserved()>target)throw Error('Bar reservation invariant failed');
  if(reason==='ssr_skip')break;
 }
 finish();
 const notional=sum(fills.map(f=>f.quantity*f.price));
 const result={status:filled?'filled':reason==='ssr_skip'?'ssr_skip':'no_fill',reason:reason||(!volume?'no_recorded_flow':filled?'window_end':children?'no_eligible_fill':'no_economical_child'),fills,journal:[],fees,
  target_shares:target,arrival_mid:arrival,filled_shares:filled,notional,mean_fill:filled?notional/filled:null,fill_fraction:target?filled/target:null,
  observed_external_volume:volume,children,borrow_exceptions:0,borrow_mode:'conditional',locate_cost:0,evidence:'one_second_bar_fill_sensitivity',quote_basis:s.quote_basis};
 s._results?.set(cacheKey,result);return result;
}
module.exports={gaps,replay,eligibleFraction};
