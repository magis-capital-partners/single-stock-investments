// External-runner transport. This module is never imported by the Worker.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {at} from './shadow-core.mjs';

export function makeDatabentoMarket({key,reference,spawnProcess=spawn,clock=()=>new Date().toISOString(),python=process.env.PYTHON||(process.platform==='win32'?'python':'python3')}={}){
  const health={provider:'Databento Equities Mini',dataset:'EQUS.MINI',coverage:'selected_venues_not_sip_nbbo',status:key?'not_checked':'not_configured',quote_access:'unverified',nbbo_access:'unverified',last_success:null,last_heartbeat:null,error:null,subscriptions:0};
  const latest=new Map(),symbols=new Set(),telemetry=[],sampleWindows=new Map(),listeners=new Set();let child,closed=false,lines,dropped=0;
  function clear(status){latest.clear();health.status=status;health.quote_access=status==='not_entitled'?'not_entitled':'unavailable';}
  function accept(row){
    if(row.kind==='health'){
      if(['connecting','disconnected','not_entitled','subscription_error'].includes(row.status))clear(row.status);
      else if(row.status==='subscribed'){health.status='subscribed';if(health.quote_access!=='received')health.quote_access='awaiting_live_quote';health.error=null;health.last_heartbeat=clock();}
      return;
    }
    if(row.kind==='heartbeat'){health.last_heartbeat=clock();return;}
    if(row.kind==='invalidate'){latest.delete(row.ticker);return;}
    if(row.kind!=='quote'||row.dataset!=='EQUS.MINI'||row.schema!=='mbp-1'||!symbols.has(row.ticker))return;
    const now=at(clock()),ts=at(row.quote_at),received=at(row.observed_at);
    if(ts===null||received===null||ts>now+2000||received>now+2000||now-ts>15000||now-received>15000||(row.flags&12)||![row.bid,row.ask,row.bid_size,row.ask_size].every(Number.isFinite)||row.bid<=0||row.ask<row.bid||row.bid_size<=0||row.ask_size<=0){latest.delete(row.ticker);return;}
    latest.set(row.ticker,row);health.quote_access='received';health.status='available';health.last_success=clock();health.last_heartbeat=clock();
    // Record the FIRST receipt in each five-second window, not just the latest
    // quote at a later poll. Otherwise processing latency would look falsely low.
    const window=Math.floor(received/5000);
    if(['AAPL','SPY','IWM'].includes(row.ticker)&&sampleWindows.get(row.ticker)!==window){sampleWindows.set(row.ticker,window);if(telemetry.length<2048)telemetry.push({...row});else dropped++;}
    for(const listener of listeners)try{listener(row.ticker);}catch{}
  }
  function start(){
    if(child||closed||!key)return;
    const env={DATABENTO_API_KEY:key,PYTHONUNBUFFERED:'1',PYTHONIOENCODING:'utf-8'};
    for(const name of ['PATH','Path','SystemRoot','WINDIR','USERPROFILE','HOME','TMP','TEMP','LANG','VIRTUAL_ENV'])if(process.env[name])env[name]=process.env[name];
    child=spawnProcess(python,['-u',fileURLToPath(new URL('./databento_live.py',import.meta.url))],{env,stdio:['pipe','pipe','pipe'],windowsHide:true});
    lines=createInterface({input:child.stdout});lines.on('line',line=>{if(line.length<=4096)try{accept(JSON.parse(line));}catch{/* Ignore malformed bounded transport records. */}});
    // Vendor stderr is deliberately not forwarded: errors are classified in the helper.
    child.stderr.on('data',()=>{});child.stdin.on('error',()=>clear('disconnected'));
    child.on('error',()=>{clear('unavailable');health.error='Databento live helper could not start';});
    child.on('exit',code=>{clear(code===2?'not_entitled':'disconnected');health.error=code===2?'Databento live access was rejected or the retry budget was exhausted':'Databento live helper stopped';});
  }
  async function miniQuote(ticker,benchmark=false){
    if(!/^[A-Z][A-Z0-9.]{0,11}$/.test(ticker||''))throw new Error('Databento raw symbol requires explicit verification');
    if(!key)throw new Error('Databento credential is not configured');
    start();if(!symbols.has(ticker)){if(symbols.size>=128)throw new Error('Databento symbol budget reached');symbols.add(ticker);health.subscriptions=symbols.size;child.stdin.write(JSON.stringify({kind:'subscribe',ticker})+'\n');}
    const identity=await reference.identity(ticker),row=latest.get(ticker);
    if(!identity.security_id||identity.currency!=='usd'||(!benchmark&&(!identity.cik||identity.type!=='CS')))throw new Error('Databento quote issuer or common-share identity is unresolved');
    if(!row||at(clock())-at(row.quote_at)>15000)throw new Error('Waiting for a fresh Databento Mini quote');
    return {ticker,...identity,provider:'databento_mini',dataset:'EQUS.MINI',coverage:'selected_venues_not_sip_nbbo',quote_at:row.quote_at,observed_at:row.observed_at,bid:row.bid,ask:row.ask,bid_size:row.bid_size,ask_size:row.ask_size,consolidated:false,delayed:false,size_units:'shares',source_url:'https://databento.com/docs/datasets/equs-mini',raw:row};
  }
  return {
    health,activePolicy:key?'rs_immediate_mini.v1':'rs_immediate.v1',
    onQuote(listener){listeners.add(listener);return ()=>listeners.delete(listener);},
    observe(ticker){if(!['AAPL','SPY','IWM'].includes(ticker))return miniQuote(ticker);return miniQuote(ticker,true);},
    drainTelemetry(){const result={samples:telemetry.splice(0),dropped};dropped=0;return result;},
    async quote(ticker,policy){
      health.nbbo_access=reference.health.quote_access;
      if(policy?.quote_feed==='databento_mini')return miniQuote(ticker);
      if(!policy&&key){start();if(!symbols.has(ticker)){symbols.add(ticker);health.subscriptions=symbols.size;child.stdin.write(JSON.stringify({kind:'subscribe',ticker})+'\n');}return null;}
      return reference.quote(ticker);
    },
    news:()=>reference.news(),actions:(...args)=>reference.actions(...args),
    close(){closed=true;latest.clear();listeners.clear();if(child){child.stdin.end(JSON.stringify({kind:'stop'})+'\n');const timer=setTimeout(()=>child.kill(),3000);timer.unref();child.once('exit',()=>clearTimeout(timer));lines?.close();}},
  };
}
