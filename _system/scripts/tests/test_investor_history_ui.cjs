const test = require('node:test');
const assert = require('node:assert/strict');
global.window=global;
require('../../../dashboard/investor-history.js');
const ui=global.InvestorHistory;
test('daily ETF is the default vehicle and dates never combine different days',()=>{
  const snapshots=[{vehicle_id:'old',vehicle_name:'A mutual fund',source_kind:'nport'},...['2026-10-29','2026-10-30'].map(period_end=>({vehicle_id:'daily',vehicle_name:'ETF',frequency:'daily',period_end,positions:[{ticker:'RYGYO.IS'}]}))];
  const vehicle=ui.disclosureVehicle(snapshots);
  assert.equal(vehicle.vehicle_id,'daily');
  assert.equal(ui.disclosureDates(vehicle.snapshots).snapshots[0].period_end,'2026-10-30');
  assert.equal(ui.disclosureDates(vehicle.snapshots,'2026-10-29').snapshots[0].period_end,'2026-10-29');
});
test('issuer ownership is labelled separately from unknown portfolio weight',()=>{
  const html=ui.positionsTable([{ticker:'RYSAS.IS',issuer_ownership_pct:14.98,weight_pct:null,nominal_capital_try:299509209}]);
  assert.match(html,/Ownership of issuer/);
  assert.match(html,/14.98%/);
  assert.match(html,/portfolio weight unavailable/);
  assert.match(html,/TRY nominal/);
});

test('letter valuation weights use the reported fund assets denominator',()=>{
  const html=ui.positionsTable([{issuer:'Delta Logistics',weight_pct:50,weight_basis:'reported_fund_assets'}]);
  assert.match(html,/50.00%/);
  assert.match(html,/Reported fund assets/);
});
test('a letter without extracted positions keeps its quarter and never falls back to an older portfolio',()=>{
  const snapshots=[{vehicle_id:'fund',quarter:'2020Q1',positions:[{issuer:'Example'}]},{vehicle_id:'fund',quarter:'2020Q2',positions:[],scope:'no_explicit_positions_identified'}];
  assert.deepEqual(ui.selectDisclosureSnapshots(snapshots,'latest').map(d=>d.quarter),['2020Q2']);
  assert.deepEqual(ui.selectDisclosureSnapshots(snapshots,'2020Q2')[0].positions,[]);
  assert.deepEqual(ui.availablePeriods({disclosure_quarters:['2020Q1','2020Q2']},'disclosures'),['2020Q2','2020Q1']);
});
test('verified brand, manager and legal names find the same complete filing history',()=>{
  const manager={manager_id:'dalal-street',name:'Pabrai Investments',legal_name:'Dalal Street, LLC',aliases:['Pabrai Funds','Pabrai Investment Funds','Mohnish Pabrai - Pabrai Investments'],history:[{quarter:'2012Q1'},{quarter:'2026Q2'}],disclosure_count:1,disclosure_quarters:['2020Q2']};
  for(const query of ['Pabrai','Pabrai Funds','Mohnish Pabrai','Dalal Street']) {
    const rows=ui.directoryRows([manager],{query});
    assert.equal(rows.length,1,query);
    assert.equal(rows[0].history.length,2,query);
    assert.deepEqual(ui.availablePeriods(rows[0]),['2026Q2','2020Q2','2012Q1']);
  }
  assert.deepEqual(ui.availablePeriods(manager,'disclosures'),['2020Q2']);
});
test('compressed books and position parts independently decode from one binary fetch',async()=>{
  const {gzipSync}=require('node:zlib');
  const assets={'history/a.json':{quarters:{'2000Q1':{positions_parts:['history/p.json']}}},'history/p.json':{positions:[{ticker:'NESTLE',currency:'CHF',value_usd:1.25}]}};
  const members=Object.values(assets).map(value=>gzipSync(JSON.stringify(value)));
  const mapping={};let offset=0;
  Object.keys(assets).forEach((path,i)=>{mapping[path]=['bundles/a.bin',offset,members[i].length];offset+=members[i].length;});
  let calls=0;
  const read=ui.createReader({asset_bundles:mapping},async()=>{throw new Error('Unexpected uncompressed fetch');},async()=>{calls++;return Buffer.concat(members);});
  const results=await Promise.all(Object.keys(assets).map(path=>read(`data/holdings/${path}`)));
  assert.deepEqual(results,Object.values(assets));
  assert.equal(calls,1);
});
test('invalid compressed ranges and corrupt gzip members fail visibly',async()=>{
  const {gzipSync}=require('node:zlib');
  const bytes=gzipSync('{"positions":[]}');
  const invalid=ui.createReader({asset_bundles:{'history/a.json':['bundles/a.bin',0,bytes.length+1]}},undefined,async()=>bytes);
  await assert.rejects(invalid('data/holdings/history/a.json'),/member range is invalid/);
  bytes[bytes.length-1]^=1;
  const corrupt=ui.createReader({asset_bundles:{'history/a.json':['bundles/a.bin',0,bytes.length]}},undefined,async()=>bytes);
  await assert.rejects(corrupt('data/holdings/history/a.json'));
});
test('logical books, manifests and positions share one physical fetch',async()=>{
  const assets={
    'history/a/2000.json':{quarters:{'2000Q1':{positions_parts:['history/a/p.json']}}},
    'history/a/p.json':{positions:[{ticker:'A',value_usd:1}]},
    'disclosures/fund name.json':{quarters:{'2000Q1':['disclosures/s.json']}},
    'disclosures/s.json':{snapshots:[{currency:'CHF'}]},
  };
  const calls=[];
  const read=ui.createReader({asset_bundles:Object.fromEntries(Object.keys(assets).map(key=>[key,'bundles/a.json']))},async path=>{calls.push(path);return path.includes('/bundles/') ? {assets} : {legacy:true};});
  const values=await Promise.all(Object.keys(assets).map(path=>read(`data/holdings/${encodeURI(path)}`)));
  assert.deepEqual(values,Object.values(assets));
  assert.deepEqual(calls,['data/holdings/bundles/a.json']);
  assert.deepEqual(await read('data/holdings/by_manager/a.json'),{legacy:true});
});
test('bundle failures retry and missing logical assets fail visibly',async()=>{
  let calls=0;
  const read=ui.createReader({asset_bundles:{'history/a.json':'bundles/a.json'}},async()=>{if(++calls===1)throw new Error('offline');return {assets:{}};});
  await assert.rejects(read('data/holdings/history/a.json'),/offline/);
  await assert.rejects(read('data/holdings/history/a.json'),/missing from its bundle/);
  assert.equal(calls,2);
});
test('browsing many bundles bounds retained data',async()=>{
  const paths=Array.from({length:5},(_,i)=>`history/${i}.json`);
  let calls=0;
  const read=ui.createReader({asset_bundles:Object.fromEntries(paths.map((path,i)=>[path,`bundles/${i}.json`]))},async()=>{calls++;return {assets:Object.fromEntries(paths.map(path=>[path,{}]))};});
  for(const path of paths)await read(`data/holdings/${path}`);
  await read(`data/holdings/${paths[0]}`);
  assert.equal(calls,6);
});
const managers=[
  {manager_id:'a',name:'Alpha',history:[{quarter:'2001Q1',positions:2,ssi_overlap:0},{quarter:'2026Q2',positions:7,ssi_overlap:1}]},
  {manager_id:'b',name:'Beta',history:[],disclosure_count:2,disclosure_quarters:['2020Q1']},
  {manager_id:'c',name:'No filing',history:[]},
];

test('large books remain fully searchable and paginated',()=>{
  const rows=Array.from({length:405},(_,i)=>({ticker:`T${i}`,cusip:`CUSIP${i}`,value_usd:i}));
  assert.equal(ui.positionPage(rows).rows.length,100);
  assert.equal(ui.positionPage(rows).rows[0].ticker,'T404');
  assert.equal(ui.positionPage(rows,{page:4}).rows.length,5);
  assert.equal(ui.positionPage(rows,{query:'CUSIP404'}).rows[0].ticker,'T404');
  assert.equal(ui.positionPage(rows,{query:'unmatched'}).total,0);
});
test('each fund vehicle remains selectable without combining their books',()=>{
  const snapshots=[{vehicle_id:'b',vehicle_name:'Beta',positions:[2]},{vehicle_id:'a',vehicle_name:'Alpha',positions:[1]}];
  const first=ui.disclosureVehicle(snapshots);
  assert.equal(first.vehicles.length,2);
  assert.equal(first.snapshots[0].vehicle_id,'a');
  assert.deepEqual(ui.disclosureVehicle(snapshots,'b').snapshots[0].positions,[2]);
});
test('undated disclosures remain reachable alongside dated holdings',()=>{
  const snapshots=[{vehicle_id:'a'},{vehicle_id:'a',period_end:'2020-03-31'}];
  assert.equal(ui.selectDisclosureSnapshots(snapshots,'undated').length,1);
  const manager={manager_id:'a',name:'Alpha',disclosure_count:2,disclosure_quarters:['2020Q1','undated']};
  assert.equal(ui.directoryRows([manager],{quarter:'undated'}).length,1);
  assert.ok(ui.availablePeriods(manager).includes('undated'));
});
test('all managers including non-filers appear by default',()=>{
  assert.equal(ui.directoryRows(managers).length,3);
  assert.equal(ui.directoryRows(managers,{overlap:true}).length,1);
});
test('historical selection returns the historical book, not the latest book',()=>{
  const rows=ui.directoryRows(managers,{quarter:'2001Q1'});
  assert.equal(rows.length,1);
  assert.equal(rows[0].positions,2);
  assert.equal(rows[0].ssi_overlap,0);
});
test('international-only managers remain selectable in their disclosure quarter',()=>{
  assert.equal(ui.directoryRows(managers,{quarter:'2020Q1',source:'disclosures'})[0].name,'Beta');
  assert.equal(ui.directoryRows(managers,{quarter:'2020Q1',source:'13f'}).length,0);
});

test('a non-filer can select every historical disclosure quarter',()=>{
  assert.deepEqual(ui.availablePeriods({history:[],disclosure_quarters:['2001Q1','2026Q2']},'disclosures'),['2026Q2','2001Q1']);
  assert.deepEqual(ui.availablePeriods(managers[0],'13f'),['2026Q2','2001Q1']);
});

test('an old disclosure or source gap never displays a newer US book',()=>{
  const manager={manager_id:'a',name:'Alpha',quarter:'2026Q2',positions:20,ssi_overlap:5,history:[{quarter:'2026Q2',positions:20,ssi_overlap:5}],disclosure_quarters:['2001Q1'],disclosure_count:1,filing_gaps:[{period_end:'2000-03-31'}]};
  assert.equal(ui.directoryRows([manager],{quarter:'2001Q1'})[0].positions,null);
  assert.equal(ui.directoryRows([manager],{quarter:'2000Q1',source:'13f'})[0].ssi_overlap,null);
  assert.ok(ui.availablePeriods(manager).includes('2000Q1'));
});

test('bundled disclosures select dates and amendments before loading position parts',()=>{
  const snapshots=[
    {id:'old',vehicle_id:'fund',period_end:'2000-03-31',source_kind:'nport',filed_at:'2000-05-01',positions_parts:['old.json']},
    {id:'new',vehicle_id:'fund',period_end:'2020-03-31',source_kind:'nport',filed_at:'2020-05-01',positions_parts:['new.json']},
    {id:'amended',vehicle_id:'fund',period_end:'2020-03-31',source_kind:'nport',filed_at:'2020-06-01',positions_parts:['amended.json']},
    {id:'other',vehicle_id:'second-fund',period_end:'2010-03-31',source_kind:'nport',filed_at:'2010-05-01',positions_parts:['other.json']},
  ];
  assert.deepEqual(ui.selectDisclosureSnapshots(snapshots,'2000Q1').map(d=>d.id),['old']);
  assert.deepEqual(ui.selectDisclosureSnapshots(snapshots,'latest').map(d=>d.id),['amended','other']);
});
test('holdings preserve classes, option types, unknown weights and safe strings',()=>{
  const html=ui.positionsTable([{ticker:'GOOG',issuer:'<script>',title_of_class:'CL C',put_call:'CALL',weight_pct:null,value_usd:0}]);
  assert.match(html,/CL C · CALL/);
  assert.match(html,/&lt;script&gt;/);
  assert.match(html,/—/);
  assert.match(html,/\$0/);
});
test('source links reject active URL schemes',()=>{
  assert.equal(ui.sourceLink('javascript:alert(1)','bad'),'');
  assert.match(ui.sourceLink('https://www.sec.gov/a','SEC'),/noopener/);
});
