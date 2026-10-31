const test = require('node:test');
const assert = require('node:assert/strict');
global.window=global;
require('../../../dashboard/investor-history.js');
const ui=global.InvestorHistory;
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
