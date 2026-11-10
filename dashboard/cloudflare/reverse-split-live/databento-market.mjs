// External-runner transport. This module is never imported by the Worker.
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {at} from './shadow-core.mjs';

export function makeDatabentoMarket({key,reference,spawnProcess=spawn,clock=()=>new Date().toISOString(),python=process.env.PYTHON||(process.platform==='win32'?'python':'python3')}={}){
  const health={provider:'Databento Equities Mini',dataset:'EQUS.MINI',coverage:'selected_venues_not_sip_nbbo',status:key?'not_checked':'not_configured',quote_access:'unverified',nbbo_access:'unverified',last_success:null,last_heartbeat:null,error:null,subscriptions:0,invalidations:0,rejected_records:0};
  const identityTimes=new Map(),identityLoads=new Map(),identities=new Map(),latest=new Map(),symbols=new Set(),telemetry=[],sampleWindows=new Map(),listeners=new Set();let child,closed=false,lines,dropped=0;
  function clear(status){latest.clear();health.status=status;health.quote_access=status==='not_entitled'?'not_entitled':'unavailable';}
  function accept(row){
    if(row.kind==='health'){
      if(['connecting','disconnected','not_entitled','subscription_error'].includes(row.status))clear(row.status);
      else if(row.status==='subscribed'){health.status='subscribed';if(health.quote_access!=='received')health.quote_access='awaiting_live_quote';health.error=null;health.last_heartbeat=clock();}
      return;
    }
    if(row.kind==='heartbeat'){health.last_heartbeat=clock();return;}
    if(row.kind==='invalidate'){health.invalidations++;latest.delete(row.ticker);return;}
    if(row.kind!=='quote'||row.dataset!=='EQUS.MINI'||row.schema!=='mbp-1'||!symbols.has(row.ticker))return;
    const now=at(clock()),ts=at(row.quote_at),received=at(row.observed_at);
    if(ts===null||received===null||ts>now+2000||received>now+2000||now-ts>15000||now-received>15000||(row.flags&12)||![row.bid,row.ask,row.bid_size,row.ask_size].every(Number.isFinite)||row.bid<=0||row.ask<row.bid||row.bid_size<=0||row.ask_size<=0){health.rejected_records++;latest.delete(row.ticker);return;}
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
  async function verifyIdentity(ticker){if(identities.has(ticker))return identities.get(ticker);if(!identityLoads.has(ticker))identityLoads.set(ticker,reference.identity(ticker).then(identity=>{identities.set(ticker,identity);identityTimes.set(ticker,clock());return identity;}).finally(()=>identityLoads.delete(ticker)));return identityLoads.get(ticker);}
  async function miniQuote(ticker,benchmark=false){
    if(!/^[A-Z][A-Z0-9.]{0,11}$/.test(ticker||''))throw new Error('Databento raw symbol requires explicit verification');
    if(!key)throw new Error('Databento credential is not configured');
    start();if(!symbols.has(ticker)){if(symbols.size>=128)throw new Error('Databento symbol budget reached');symbols.add(ticker);health.subscriptions=symbols.size;child.stdin.write(JSON.stringify({kind:'subscribe',ticker})+'\n');}
    const identity=await verifyIdentity(ticker),row=latest.get(ticker);
    if(!identity.security_id||identity.currency!=='usd'||(!benchmark&&(!identity.cik||identity.type!=='CS')))throw new Error('Databento quote issuer or common-share identity is unresolved');
    if(!row||at(clock())-at(row.quote_at)>15000)throw new Error('Waiting for a fresh Databento Mini quote');
    return {ticker,...identity,provider:'databento_mini',dataset:'EQUS.MINI',coverage:'selected_venues_not_sip_nbbo',quote_at:row.quote_at,observed_at:row.observed_at,bid:row.bid,ask:row.ask,bid_size:row.bid_size,ask_size:row.ask_size,consolidated:false,delayed:false,size_units:'shares',source_url:'https://databento.com/docs/datasets/equs-mini',raw:row};
  }
  return {
    get health(){const atNow=at(clock()),age=health.last_success?(atNow-at(health.last_success))/1000:null,per_symbol=[...symbols].map(ticker=>{const q=latest.get(ticker),quote_age_seconds=q?(atNow-at(q.quote_at))/1000:null;return {ticker,quote_at:q?.quote_at||null,observed_at:q?.observed_at||null,quote_age_seconds,status:quote_age_seconds!==null&&quote_age_seconds<=15?'fresh':q?'stale':'awaiting_quote'};});return {...health,quote_access:health.quote_access==='received'&&age>15?'stale':health.quote_access,last_quote_age_seconds:age,per_symbol,symbol_budget:128,symbol_budget_remaining:128-symbols.size};},
    verifyIdentity,identityKnown:ticker=>identities.has(ticker),
    peek(ticker){const row=latest.get(ticker);if(!row)return null;const identity=identities.get(ticker);return {...identity,...row,raw:row,size_units:'shares',coverage:'selected_venues_not_sip_nbbo',identity_verified_at:identityTimes.get(ticker)||null,identity_verified:!!identity?.security_id&&!!identity.cik&&identity.type==='CS'&&identity.currency==='usd',security_id:identity?.security_id||null};},
    warm(ticker){if(!/^[A-Z][A-Z0-9.]{0,11}$/.test(ticker||'')||!key)return;start();if(!symbols.has(ticker)){if(symbols.size>=128){health.error='Databento symbol budget reached';return;}symbols.add(ticker);health.subscriptions=symbols.size;child.stdin.write(JSON.stringify({kind:'subscribe',ticker})+'\n');}},
    reconcileSymbols(wanted){const keep=[...new Set(['AAPL','SPY','IWM',...wanted])].filter(t=>/^[A-Z][A-Z0-9.]{0,11}$/.test(t)).slice(0,128);if(symbols.size<96||(!keep.some(t=>!symbols.has(t))&&keep.length>=symbols.size-16))return;const atNow=at(clock());if(atNow-(health.last_rotation_ms||0)<300000)return;health.last_rotation_ms=atNow;health.subscription_rotations=(health.subscription_rotations||0)+1;symbols.clear();for(const t of keep)symbols.add(t);latest.clear();health.subscriptions=symbols.size;health.quote_access='awaiting_live_quote';child?.stdin.write(JSON.stringify({kind:'replace_subscriptions',tickers:keep})+'\n');},
    activePolicy:key?'rs_immediate_mini.v1':'rs_immediate.v1',
    onQuote(listener){listeners.add(listener);return ()=>listeners.delete(listener);},
    observe(ticker){if(!['AAPL','SPY','IWM'].includes(ticker))return miniQuote(ticker);return miniQuote(ticker,true);},
    drainTelemetry(){const result={samples:telemetry.splice(0),dropped};dropped=0;return result;},
    async quote(ticker,policy){
      health.nbbo_access=reference.health.quote_access;
      if(policy?.quote_feed==='databento_mini')return miniQuote(ticker);
      if(!policy&&key){start();if(!symbols.has(ticker)){if(symbols.size>=128)throw new Error('Databento symbol budget reached');symbols.add(ticker);health.subscriptions=symbols.size;child.stdin.write(JSON.stringify({kind:'subscribe',ticker})+'\n');}return null;}
      return reference.quote(ticker);
    },
    news:()=>reference.news(),actions:(...args)=>reference.actions(...args),
    async releaseForHandoff(){
      const old=child;if(!old)return;
      if(old.exitCode===null||old.exitCode===undefined)await new Promise((resolve,reject)=>{
        let force,limit;const finish=error=>{clearTimeout(force);clearTimeout(limit);old.removeListener('close',onClose);error?reject(error):resolve();},onClose=()=>finish();old.once('close',onClose);
        force=setTimeout(()=>old.kill('SIGKILL'),2000);limit=setTimeout(()=>finish(new Error('Databento helper close was not confirmed; collector lease retained')),7000);
        old.stdin.end(JSON.stringify({kind:'stop'})+'\n');
      });
      child=null;lines?.close();latest.clear();symbols.clear();health.subscriptions=0;health.quote_access='unavailable';health.status='closed_for_handoff';
    },
    close(){closed=true;latest.clear();listeners.clear();if(child){child.stdin.end(JSON.stringify({kind:'stop'})+'\n');const timer=setTimeout(()=>child.kill(),3000);timer.unref();child.once('exit',()=>clearTimeout(timer));lines?.close();}},
  };
}
