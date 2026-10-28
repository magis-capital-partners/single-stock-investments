'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const UI=require('../../../dashboard/third-plus-announcement.js'),S=require('./announcement_study.cjs');
const root=path.join(S.ROOT,'dashboard/data'),body=fs.readFileSync(path.join(root,'third_plus_announcement.json'),'utf8'),meta=JSON.parse(body),manifest=JSON.parse(fs.readFileSync(path.join(root,'third_plus_announcement_manifest.json'),'utf8'));
const partBodies=new Map(meta.parts.map(p=>[p.file,fs.readFileSync(path.join(root,p.file),'utf8')])),doc={...meta,models:meta.parts.flatMap(p=>JSON.parse(partBodies.get(p.file)).models)};
test('full-size publication contains every split-history and filter comparison',()=>{
 UI.validate(doc);assert.equal(new Set(doc.models.map(m=>m.id)).size,doc.model_count);assert.equal(doc.model_count,13*3*doc.arms.length*4*2);
 for(const m of doc.models){assert.equal(m.id,[m.cohort,m.ordinal,m.timing,m.holding,'usd100k',m.scenario,m.filter,m.capacity].join('__'));assert.equal(m.size,'usd100k');assert.ok(m.summary.peak_concurrent<=3||m.capacity==='unlimited');assert.ok(m.summary.net_pnl+m.summary.costs.locate<=m.summary.gross_before_costs+1e-6);assert.ok(m.feature_covered>=m.signal_pass);}
 for(const c of Object.values(doc.cohorts))assert.equal(c.ordinal_counts.first+c.ordinal_counts.second+c.ordinal_counts.third_plus,c.events);
});
test('default view uses full sizing and shows every fundamental and split-history comparison',()=>{
 const s=UI.defaults(),html=UI.view(doc,s);assert.equal(s.ordinal,'all');assert.equal(s.filter,'all');assert.ok(!('size' in s));
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
