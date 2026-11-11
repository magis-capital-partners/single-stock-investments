// HTTPS market data only. No trading credentials, broker sockets, or paid downloads.
import {at,iso,finite} from './shadow-core.mjs';
const BASE='https://api.massive.com';
export function makeMarketData({key,fetcher=fetch,clock=()=>new Date().toISOString()}={}){
  const cache=new Map(),health={provider:'Massive / Polygon',status:key?'not_checked':'not_configured',last_success:null,error:null,quote_access:'unverified',requests:0,next_attempt:null};const cooldowns=new Map();
  async function get(path){
    if(!key)throw new Error('Market-data credential is not configured');
    const capability=path.includes('/nbbo/')?'quotes':path.includes('/news')?'news':path.includes('/splits')?'actions':'identity';
    if(Date.now()<(cooldowns.get(capability)||0))throw new Error('Market '+capability+' data is in backoff');
    const url=new URL(path,BASE);if(url.origin!==BASE)throw new Error('Unsupported market-data host');
    health.requests++;
    const response=await fetcher(url,{headers:{authorization:'Bearer '+key,accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(8000)});
    if(!response.ok){await response.body?.cancel();const cooldown=Date.now()+(response.status===429?60000:[401,403].includes(response.status)?3600000:30000);cooldowns.set(capability,cooldown);if(capability==='quotes')health.quote_access=[401,403].includes(response.status)?'not_entitled':'unavailable';health.status='degraded';health.error='Market data HTTP '+response.status;health.next_attempt=iso(cooldown);throw new Error(health.error);}
    if(Number(response.headers.get('content-length'))>2000000){await response.body?.cancel();throw new Error('Market-data response exceeds limit');}
    const reader=response.body.getReader(),chunks=[];let length=0;
    for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>2000000){await reader.cancel();throw new Error('Market-data response exceeds limit');}chunks.push(value);}
    const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
    const body=JSON.parse(new TextDecoder().decode(bytes));health.last_success=clock();health.status='available';health.error=null;health.next_attempt=null;return body;
  }
  async function cached(id,ttl,load){const old=cache.get(id);if(old&&Date.now()-old.at<ttl)return old.value;const value=await load();cache.set(id,{at:Date.now(),value});return value;}
  const symbol=t=>{if(!/^[A-Z][A-Z0-9.-]{0,11}$/.test(t||''))throw new Error('Unsupported ticker');return encodeURIComponent(t);};
  const identity=ticker=>cached('identity:'+ticker,300000,async()=>{const path='/v3/reference/tickers/'+symbol(ticker),r=(await get(path)).results||{};if(r.ticker!==ticker)throw new Error('Reference ticker identity mismatch');return {ticker:r.ticker,cik:r.cik?String(Number(r.cik)):null,security_id:r.share_class_figi||r.composite_figi||null,type:r.type,currency:r.currency_name,active:r.active===true,source_url:BASE+path,observed_at:clock()};});
  return {
    health,identity,
    async quote(ticker){
      const t=symbol(ticker),issuer=await identity(ticker);
      const raw=await get('/v2/last/nbbo/'+t),r=raw.results||{},observed_at=clock(),quote_at=finite(r.t)?iso(r.t/1000000):null;
      if((r.T&&r.T!==ticker)||!quote_at||![r.p,r.P,r.s,r.S].every(finite))throw new Error('Market-data quote is incomplete or has the wrong symbol');
      health.quote_access=raw.status==='DELAYED'?'delayed':'received';
      return {ticker,...issuer,provider:'massive_nbbo',quote_at,observed_at,bid:r.p,ask:r.P,bid_size:r.s,ask_size:r.S,consolidated:true,delayed:raw.status==='DELAYED',size_units:'shares',source_url:BASE+'/v2/last/nbbo/'+t,raw:r};
    },
    async actions(ticker,start){return cached('actions:'+ticker+':'+start+':'+clock().slice(0,10),3600000,async()=>{
      let path='/stocks/v1/splits?ticker='+symbol(ticker)+'&execution_date.gte='+encodeURIComponent(start)+'&limit=100',rows=[];
      for(let page=0;page<5&&path;page++){const body=await get(path);rows.push(...(body.results||[]));path=body.next_url||null;}
      return {records:rows,complete:!path,observed_at:clock()};
    });},
    async news(){const body=await get('/v2/reference/news?order=desc&sort=published_utc&limit=100');return (body.results||[]).filter(r=>/reverse[\s-]+(?:stock[\s-]+|share[\s-]+)?split|share consolidation/i.test(r.title||''));},
  };
}
