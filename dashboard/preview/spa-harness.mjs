// Committed-data component render checks. The real SPA is also checked in the
// browser; this harness neither simulates authenticated APIs nor edits data.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(import.meta.url);
global.window=global;
const storage=new Map();
global.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value)),removeItem:key=>storage.delete(key)};
for(const name of ['desk-briefs','reverse-splits','short-alpha','special-situations','separations']) require(path.join(root,'dashboard',name+'-viz.js'));
const read=name=>JSON.parse(fs.readFileSync(path.join(root,'dashboard/data',name+'.json'),'utf8'));
const reports=[];
const renders={};
function check(name,html,needles) {
  for(const needle of needles) assert.ok(html.includes(needle),`${name}: missing ${needle}`);
  reports.push({name,status:'ok',html_bytes:Buffer.byteLength(html),assertions:needles});
  renders[name]=html;
}
const briefs=read('desk_briefs');
check('inbox',DeskBriefsViz.render(briefs),['Desk briefs','Special Situations','claude-drew-special-situations','Drew','Inputs.','old at read']);
const short=read('short_alpha');
assert.equal(short.schema_version,'1.2');
assert.equal(short.summary.candidate_count,short.candidates.length);
storage.set('ssi_short_alpha_filter_v2',JSON.stringify({query:'EDBL',framework:'all',stage:'all'}));
const shorts=ShortAlphaViz.render(short);
check('shorts',shorts,['EDBL','Reverse split','reverse-split-research','#reverse-split','0 of 6 lens reviews recorded','Reverse-split discovery lead']);
const strip=shorts.match(/class="short-lens-strip"[^>]*>(.*?)<\/span>/s);
assert.ok(strip,'EDBL lens strip missing');
assert.equal((strip[1].match(/<i /g)||[]).length,6,'Expected six lens cells');
check('reverse-splits',ReverseSplitsViz.render(read('reverse_splits')),['Recent announcements','Repeat splitters','Honest limits']);
const situations=read('special_situations');
// Match loadSpecialSituations()'s composition in dashboard/index.html.
situations.separations=read('separations');
const mdt=situations.rows.find(row=>row.ticker==='MDT'&&row.lanes.includes('split_offs'));
assert.ok(mdt,'MDT split-off row missing');
// Open the detail row through the production event handler, as the UI does.
function openSituation(id) {
  const host={querySelectorAll:selector=>selector==='[data-situation-open]'?[{dataset:{situationOpen:id},addEventListener:(_,fn)=>fn()}]:[],querySelector:()=>null};
  SpecialSituationsViz.attach(host,situations,{onChange(){}});
}
openSituation(mdt.id);
check('split-offs',SpecialSituationsViz.render(situations,{lane:'split_offs'}),['Split-offs and exchange offers','MDT','MiniMed','Exchange terms.','Who must sell.']);
const forcedRow=situations.rows.find(row=>row.ticker==='MMED'&&row.lanes.includes('forced_sellers'));
assert.ok(forcedRow,'MiniMed modeled forced-seller row missing');
openSituation(forcedRow.id);
const forced=SpecialSituationsViz.render(situations,{lane:'forced_sellers'});
check('forced-sellers',forced,['MMED','Selling window','estimate']);
const ticker=read('tickers/MDT');
check('mdt-card',SeparationsViz.renderTickerCard(ticker.separation),['Separation','MMED']);
const feed=read('feed_status');
for(const id of ['desk-briefs','reverse-splits','separations','short-alpha','special-situations']) assert.ok(feed.surfaces.some(row=>row.id===id),`Feed status missing ${id}`);
reports.push({name:'feed-contract',status:'ok',scope:'Data contract; see browser evidence for the rendered Data Health page'});
const report={research_only:true,in_base_irr:false,authority:'none',core_generated_at:read('core').generated_at,
  scope:'Production component functions and committed data. Real SPA navigation, lazy loading and console errors require the separate browser check.',checks:reports};
if(process.argv[2]) {
  fs.mkdirSync(process.argv[2],{recursive:true});
  for(const [name,html] of Object.entries(renders)) fs.writeFileSync(path.join(process.argv[2],name+'.html'),html);
  fs.writeFileSync(path.join(process.argv[2],'render-report.json'),JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify(report,null,2));
