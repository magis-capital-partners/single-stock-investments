// Public exchange observations are dated research evidence, never broker approvals.
import {plain,etDay,easternTime} from './core.mjs';
export const HALT_URL='https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts';
export const STATUS_VERSION='nasdaq_public_status.v1';
const field=(s,name)=>plain(new RegExp('<(?:[A-Za-z_][\\w.-]*:)?'+name+'(?:\\s[^>]*)?>([\\s\\S]*?)<\\/(?:[A-Za-z_][\\w.-]*:)?'+name+'>','i').exec(s)?.[1]||'');
const ms=s=>Number.isFinite(Date.parse(s))?Date.parse(s):null;
const symbol=s=>/^[A-Z][A-Z0-9.-]{0,15}$/.test(s||'');
function clock(day,time){const m=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(day||'');if(!m||!/^\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?$/.test(time||''))throw new Error('Invalid exchange event clock');return easternTime(m[3]+'-'+m[1].padStart(2,'0')+'-'+m[2].padStart(2,'0'),time);}
export function parseHaltFeed(xml,observedAt){
 if(xml.length>5*1024*1024||!/<rss\b/i.test(xml))throw new Error('Invalid bounded halt feed');
 const channel=xml.split(/<item\b/i)[0],as_of=field(channel,'pubDate'),asof=ms(as_of),observed=ms(observedAt);
 if(asof===null||observed===null||asof>observed+2000||observed-asof>90000)throw new Error('Halt feed clock missing, future or stale');
 const bodies=[...xml.matchAll(/<item\b[^>]*>([\s\S]*?)<\/item>/gi)],countText=field(channel,'numItems'),count=Number(countText);
 if(!/^\d+$/.test(countText)||!Number.isInteger(count)||count<0||count>5000||count!==bodies.length)throw new Error('Halt feed item count mismatch');
 const items=bodies.map(([,body])=>{const ticker=field(body,'IssueSymbol'),halt_at=clock(field(body,'HaltDate'),field(body,'HaltTime')),date=field(body,'ResumptionDate'),time=field(body,'ResumptionTradeTime'),resume_at=date&&time?clock(date,time):null;if(!symbol(ticker)||ms(halt_at)>asof+2000||(resume_at&&ms(resume_at)<ms(halt_at)))throw new Error('Invalid halt event identity or chronology');return {ticker,halt_at,resume_at,market:field(body,'Market'),reason:field(body,'ReasonCode')};});
 return {as_of:new Date(asof).toISOString(),items,complete:true,coverage:'Nasdaq_and_other_exchange_listed_securities',refresh_seconds:60};
}
export function parseCarryRestrictions(text,day,observedAt){
 const lines=text.trim().split(/\r?\n/),footer=lines.at(-1),expected=day.replaceAll('-','');
 if(text.length>5*1024*1024||!/^Symbol,Security Name,Market Category,Trigger Time\s*$/i.test(lines[0])||!/^\d{14}$/.test(footer)||!footer.startsWith(expected))throw new Error('Restriction file identity or day mismatch');
 const as_of=easternTime(day,footer.slice(8,10)+':'+footer.slice(10,12)+':'+footer.slice(12,14));if(ms(as_of)>ms(observedAt)||etDay(observedAt)!==day)throw new Error('Restriction file day or clock invalid');
 const symbols=lines.slice(1,-1).map(line=>{const ticker=line.split(',')[0];if(!symbol(ticker)||!/,\d{1,2}\/\d{1,2}\/\d{4}\s/.test(line))throw new Error('Invalid restriction file row');return ticker;});
 return {day,as_of,symbols:[...new Set(symbols)],complete:true,intraday_clearance:false,source_url:'https://www.nasdaqtrader.com/dynamic/symdir/shorthalts/shorthalts'+expected+'.txt'};
}
export function publicMarketEvidence(snapshot,event,now){
 if(!event?.id||!/^\d{1,10}$/.test(event.cik||'')||!symbol(event.ticker)||!snapshot?.listed?.has(event.ticker))return [];
 const records=[],base={event_id:event.id,cik:event.cik,ticker:event.ticker,provider:'NasdaqTrader',scope:'reverse_split',evidence_version:STATUS_VERSION,broker_execution_verified:false,authority:'none'},feed=snapshot.halts;
 if(feed?.complete&&ms(feed.observed_at)!==null&&ms(feed.observed_at)<=ms(now)&&ms(now)-ms(feed.observed_at)<=65000&&ms(feed.as_of)!==null&&ms(feed.as_of)<=ms(now)+2000&&ms(now)-ms(feed.as_of)<=155000&&/^[a-f0-9]{64}$/.test(feed.source_sha256||'')){
  const rows=feed.items.filter(r=>r.ticker===event.ticker&&ms(r.halt_at)<=ms(now)).sort((a,b)=>ms(b.halt_at)-ms(a.halt_at)),latest=rows[0],halted=!!latest&&(!latest.resume_at||ms(latest.resume_at)>ms(feed.as_of));
  records.push({...base,kind:'trading_status',halted,observed_at:feed.observed_at,source_at:feed.as_of,valid_until:new Date(ms(feed.observed_at)+65000).toISOString(),source_url:HALT_URL,source_sha256:feed.source_sha256,reference:latest?'Official halt/resumption schedule in a fresh complete feed':'Absent from a fresh complete current halt feed',refresh_seconds:60,coverage:feed.coverage,resumption_is_not_verified_execution:true});
 }
 const carry=snapshot.carry;
 if(carry?.complete&&carry.day===etDay(now)&&ms(carry.observed_at)<=ms(now)&&carry.symbols.includes(event.ticker)&&/^[a-f0-9]{64}$/.test(carry.source_sha256||''))records.push({...base,kind:'ssr',restricted:true,observed_at:carry.observed_at,source_at:carry.as_of,valid_until:easternTime(carry.day,'16:00:00'),source_url:carry.source_url,source_sha256:carry.source_sha256,reference:'Official daily carry-in restriction; absence never proves intraday clearance',intraday_clearance:false});
 return records.filter(r=>ms(r.valid_until)>ms(now));
}
export function validatedPublicStatus(r,kind,now,identity={}){
 if(r.kind!==kind||r.provider!=='NasdaqTrader'||r.scope!=='reverse_split'||r.evidence_version!==STATUS_VERSION||!/^\d{1,10}$/.test(r.cik||'')||!symbol(r.ticker)||!r.event_id||!/^[a-f0-9]{64}$/.test(r.source_sha256||'')||ms(r.observed_at)===null||ms(r.observed_at)>ms(now)||ms(r.source_at)===null||ms(r.source_at)>ms(r.observed_at)+2000||ms(r.valid_until)===null||ms(r.valid_until)<ms(now))return false;
 if(identity.ticker&&identity.ticker!==r.ticker||identity.cik&&String(Number(identity.cik))!==String(Number(r.cik))||identity.event_id&&identity.event_id!==r.event_id)return false;
 if(kind==='trading_status')return typeof r.halted==='boolean'&&r.source_url===HALT_URL&&ms(r.valid_until)-ms(r.observed_at)<=65000&&ms(r.observed_at)-ms(r.source_at)<=90000;
 return kind==='ssr'&&r.restricted===true&&r.intraday_clearance===false&&r.source_url==='https://www.nasdaqtrader.com/dynamic/symdir/shorthalts/shorthalts'+etDay(now).replaceAll('-','')+'.txt'&&ms(r.valid_until)<=ms(easternTime(etDay(now),'16:00:00'));
}
