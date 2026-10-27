'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const UI=require('../../../dashboard/third-plus-announcement.js'),S=require('./announcement_study.cjs');
const root=path.join(S.ROOT,'dashboard/data'),body=fs.readFileSync(path.join(root,'third_plus_announcement.json'),'utf8'),meta=JSON.parse(body),manifest=JSON.parse(fs.readFileSync(path.join(root,'third_plus_announcement_manifest.json'),'utf8'));
const partBodies=new Map(meta.parts.map(p=>[p.file,fs.readFileSync(path.join(root,p.file),'utf8')])),doc={...meta,models:meta.parts.flatMap(p=>JSON.parse(partBodies.get(p.file)).models)};
test('full-size publication contains every split-history and filter comparison',()=>{
 UI.validate(doc);assert.equal(new Set(doc.models.map(m=>m.id)).size,doc.model_count);assert.equal(doc.model_count,13*3*doc.arms.length*4*2);
 for(const m of doc.models){assert.ok(m.summary.net_pnl<=m.summary.entry_dollars+1e-5);assert.equal(m.id,[m.cohort,m.ordinal,m.timing,m.holding,'usd100k',m.scenario,m.filter,m.capacity].join('__'));assert.equal(m.size,'usd100k');assert.ok(m.summary.peak_concurrent<=3||m.capacity==='unlimited');assert.ok(m.summary.net_pnl+m.summary.costs.locate<=m.summary.gross_before_costs+1e-6);assert.ok(m.feature_covered>=m.signal_pass);assert.ok(Math.abs(m.summary.gross_before_costs-Object.values(m.summary.costs).reduce((s,x)=>s+x,0)-m.summary.net_pnl)<1e-5);assert.ok(Math.abs(m.summary.net_pnl-m.summary.price_imputed_net_pnl-m.summary.pnl_without_price_imputation)<1e-5);assert.ok(m.summary.price_imputed_entries<=m.summary.entered);}
 for(const c of Object.values(doc.cohorts))assert.equal(c.ordinal_counts.first+c.ordinal_counts.second+c.ordinal_counts.third_plus,c.events);
 const all=doc.models.find(m=>m.cohort==='scheduled_disclosures'&&m.ordinal==='all'&&m.timing==='announce_now'&&m.holding==='entry20'&&m.scenario==='base'&&m.filter==='all'&&m.capacity==='unlimited'),sum=doc.models.filter(m=>m.cohort===all.cohort&&m.ordinal!=='all'&&m.timing===all.timing&&m.holding===all.holding&&m.scenario===all.scenario&&m.filter===all.filter&&m.capacity===all.capacity).reduce((s,m)=>s+m.summary.net_pnl,0);assert.ok(Math.abs(all.summary.net_pnl-sum)<1e-5);
});
test('default view uses full sizing and shows every fundamental and split-history comparison',()=>{
 const s=UI.defaults(),html=UI.view(doc,s);assert.equal(s.ordinal,'all');assert.equal(s.filter,'all');assert.equal(s.capacity,'unlimited');assert.ok(!('size' in s));
 assert.match(html,/Full-size announcement backtest/);assert.match(html,/One initial share applies only to the future live pilot/);assert.match(html,/Same-coverage control/);assert.match(html,/First documented split/);assert.match(html,/Original weak split-day/);assert.match(html,/not a verified IBKR tariff/);
 assert.equal(UI.rows(doc,s).length,3);assert.equal(UI.rows(doc,{...s,cohort:'completed_matched'}).length,4);
 const one=UI.chosen(doc,s,{ordinal:'first'}),two=UI.chosen(doc,s,{ordinal:'second'});assert.notEqual(one.id,two.id);assert.equal(one.candidates,doc.cohorts.scheduled_disclosures.ordinal_counts.first);
});
test('rendering escapes metadata and exports only full-sized selected cases',()=>{
 const d={...doc,disclosure_through:'<img onerror="bad()">'};assert.ok(!UI.view(d,UI.defaults()).includes('<img onerror='));const csv=UI.csv(doc,UI.defaults());assert.equal(csv.split('\r\n').length,4);assert.match(csv,/"usd100k"/);assert.ok(!csv.includes('one_share'));assert.match(csv,/intraday_proxy_entries/);
});
test('browser loader verifies all publication shards and rejects mixed bytes or paths',async()=>{
 const fetcher=async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>url.includes('third_plus_announcement.json?')?body:partBodies.get(url.split('?')[0].replace('data/',''))};
 assert.equal((await UI.load(fetcher,crypto.webcrypto)).models.length,doc.model_count);
 await assert.rejects(UI.load(async url=>url.includes('manifest')?{ok:true,json:async()=>manifest}:{ok:true,text:async()=>body+' '},crypto.webcrypto),/different publications/);
 await assert.rejects(UI.load(async url=>url.includes('manifest')?{ok:true,json:async()=>({...manifest,payload:'../../private'})}:{ok:true,text:async()=>body},crypto.webcrypto),/Invalid announcement manifest/);
 const broken=async url=>{const r=await fetcher(url);return url.includes('_all.json?')?{ok:true,text:async()=>(await r.text())+' '}:r;};await assert.rejects(UI.load(broken,crypto.webcrypto),/Mixed announcement comparison/);
});

test('primary action receipts bind final units and never promote authorization ranges',()=>{
 const b=fs.readFileSync(path.join(root,meta.action_audit.file)),a=JSON.parse(b);assert.equal(crypto.createHash('sha256').update(b).digest('hex'),meta.action_audit.sha256);
 for(const [ticker,day,factor]of [['LAZR','2024-11-21',15],['HOLO','2024-10-09',20],['RAYA','2025-09-30',220],['LNKS','2026-04-06',250],['SMX','2023-08-21',22],['ELBM','2025-01-02',4],['FCHL','2026-03-23',15],['GSAT','2025-02-11',15],['PBM','2025-05-05',7.97],['STFS','2026-03-13',40],['GIBO','2026-06-29',25],['FTEL','2026-01-08',8],['GMEX','2026-05-01',7],['ACST','2021-08-31',8],['VERO','2025-03-04',11],['ISPC','2026-04-28',40]]){const r=a.ledger.find(x=>x.ticker===ticker&&x.ex_date===day);assert.equal(r?.price_factor,factor,ticker+' final primary units');assert.match(r.source_sha256,/^[a-f0-9]{64}$/);}
 assert.ok(a.ledger.every(r=>Date.parse(r.source_public_date||r.source_filed_at)<=Date.parse(r.ex_date)+2*86400000||r.ratio_basis==='reviewed_exact_primary_ratio_and_first_trading_date'));assert.ok(!a.excluded_issuers.some(x=>/Bollinger/i.test(x.name)));assert.equal(meta.action_audit.remaining_nominal_discontinuities,a.remaining_nominal_discontinuities.length);
 const primary=UI.chosen(doc,UI.defaults());assert.equal(primary.summary.unresolved_action_paths,0);
 for(const [ticker,day,factor,cash]of [['FRGT','2023-03-24',10,null],['FRGT','2024-02-05',10,null],['ITRG','2023-05-26',2.5,null],['USAS','2025-08-26',2.5,null],['SPPL','2025-04-07',8,null],['NCI','2025-06-16',5,null],['ORKT','2025-09-29',4,null],['MGN','2026-09-17',30,null],['HON','2026-06-29',2,null],['QGEN','2024-01-30',25/24.25,1.28],['QGEN','2025-01-29',36/35,1.26],['QGEN','2026-01-08',20/19,2.29]]){const r=a.ledger.find(x=>x.ticker===ticker&&x.ex_date===day);assert.equal(r?.price_factor,factor,ticker+' dated units');if(cash)assert.equal(r.cash_per_old_share,cash);}
 assert.equal(a.ledger.find(x=>x.ticker==='IX'&&x.ex_date==='2025-02-28')?.price_factor,.2);assert.ok(a.excluded_issuers.some(x=>x.name==='VS Trust'));
});

test('the published universe excludes warrant-update datelines and joins a documented schedule revision',()=>{
 const csv=fs.readFileSync(path.join(root,meta.event_audit.file),'utf8');assert.ok(!csv.includes('"announcement/1838163/2026-01-28"'));assert.ok(!csv.includes('"announcement/1838163/2026-01-29"'));
 assert.equal((csv.match(/^"announcement\/1549084\/2025-(?:05|06)-[^\"]+"/gm)||[]).length,1);
 const qgen=csv.split(/\r?\n/).find(line=>line.startsWith('"announcement/1015820/2025-01-29",'));assert.ok(qgen);assert.ok(Date.parse(qgen.split('\",\"')[4])<Date.parse('2025-01-16T00:00:00Z'));
});
