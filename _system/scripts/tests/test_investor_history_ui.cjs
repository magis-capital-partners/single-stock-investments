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
