const test = require('node:test');
const assert = require('node:assert/strict');
const V = require('../../../dashboard/stock-valuation.js');
const model = (method, overrides={}) => ({method, anchor_label:'Sourced anchor', blockers:[], inputs:{entry_price:100,entry_date:'2026-11-18',anchor:10,horizon:5,discount_rate:0.1},cases:Object.fromEntries(V.cases.map(c=>[c,{growth:0,payout:1,exit_multiple:10,reinvestment:0,incremental_roic:0,roe:0.1,distribution_yield:0.02,...overrides}]))});
test('dated dividends plus a terminal equity sale reconcile to price at the IRR',()=>{
  const m=model('earnings'), r=V.calculate(m).cases.base;
  assert.ok(Math.abs(r.irr-.1)<.0001);
  assert.ok(Math.abs(V.presentValue(r.flows,r.irr,m.inputs.entry_date)-100)<1e-9);
  assert.equal(r.flows.at(-1).amount,110);
  assert.ok(r.value>99.95&&r.value<100.05);
});
test('terminal present value is never treated as a future payoff',()=>{
  assert.equal(V.calculate(model('payoff')).ready,false);
  const m=model('payoff',{payoff:200,payoff_date:'2031-11-18'}),r=V.calculate(m).cases.base;
  assert.ok(Math.abs(r.irr-(2**(1/5)-1))<.0001);
  assert.notEqual(r.value,200);
});
test('growth reinvestment reduces distributions; retained book earnings are not paid twice',()=>{
  const m=model('owner_cash',{reinvestment:.5,incremental_roic:.2});
  const c=V.calculate(m).cases.base;
  assert.equal(c.flows[0].anchor,11); assert.equal(c.flows[0].distribution,5.5);
  const b=V.calculate(model('book',{roe:.1,payout:.2})).cases.base;
  assert.equal(b.flows[0].distribution,.2); assert.equal(b.flows[0].anchor,10.8);
});
test('negative returns and total losses remain visible; invalid, mixed-sign and missing schedules fail closed',()=>{
  assert.ok(V.irr(100,[{date:'2027-11-18',amount:50}],'2026-11-18')<0);
  assert.equal(V.irr(100,[{date:'2027-11-18',amount:0}],'2026-11-18'),-1);
  assert.equal(V.irr(100,[{date:'2027-11-18',amount:-50}],'2026-11-18'),null);
  assert.equal(V.irr(100,[{date:'2026-11-18',amount:110}],'2026-11-18'),null);
  assert.equal(V.calculate({...model('earnings'),blockers:['Share class unverified']}).ready,false);
  assert.equal(V.calculate(model('earnings'),{inputs:{anchor:null}}).ready,false);
  assert.equal(V.calculate(model('earnings',{growth:Infinity})).ready,false);
});
test('local edits recompute without mutating the source or another stock; leap days retain year boundaries',()=>{
  const m=model('earnings'),copy=JSON.stringify(m),a=V.calculate(m),b=V.calculate(m,{inputs:{entry_price:50},cases:{base:{growth:.05}}});
  assert.ok(b.cases.base.irr>a.cases.base.irr);assert.equal(JSON.stringify(m),copy);
  assert.equal(V.anniversary('2024-02-29',1),'2025-02-28');
});
test('transition dilution reduces existing shareholder proceeds and pays no unearned interim profits',()=>{
  const r=V.calculate(model('transition',{growth:.1,target_margin:.1,dilution:.2})).cases.base;
  assert.ok(r.flows.at(-1).anchor<1);assert.equal(r.flows[0].distribution,0);
});
test('unsupported model methods and nonexistent calendar dates cannot produce an IRR',()=>{
  assert.equal(V.calculate(model('invented')).ready,false);
  assert.equal(V.irr(100,[{date:'2027-02-31',amount:110}],'2026-11-18'),null);
});
test('issuer schedules keep their dates and amounts; edits scale only an explicit sensitivity',()=>{
  const m=model('dated_cashflows',{scale:1,cashflows:[{date:'2027-11-16',distribution:10,terminal:0},{date:'2028-11-15',distribution:10,terminal:100}]});
  m.inputs.anchor=null;
  const r=V.calculate(m),e=V.calculate(m,{cases:{base:{scale:.5}}});
  assert.equal(r.ready,true);assert.equal(r.cases.base.flows[0].date,'2027-11-16');
  assert.equal(e.cases.base.flows.at(-1).amount,55);
  assert.equal(V.calculate(m,{inputs:{entry_date:'2028-11-16'}}).ready,false);
});
test('perpetual preferred scenarios aggregate coupons monthly and use an assumed sale, not a maturity',()=>{
  const m=model('preferred',{coupon_paid:1,exit_price:100});m.inputs.anchor=15;
  const r=V.calculate(m).cases.base;
  assert.equal(r.flows.length,60);assert.equal(r.flows[0].distribution,1.25);
  assert.equal(r.flows.at(-1).amount,101.25);
  assert.ok(Math.abs(V.presentValue(r.flows,r.irr,m.inputs.entry_date)-100)<1e-8);
  assert.equal(V.monthAfter('2026-01-31',1),'2026-02-28');
});
test('the research view exposes all three IRRs, editable assumptions and source gaps safely',()=>{
  const W=require('../../../dashboard/stock-valuation-view.js');
  const m={...model('earnings'),label:'Earnings',anchor_label:'Annual earnings',currency:'USD',quote:{},notes:['<script>unsafe</script>'],blockers:[]};
  const t={ticker:'TEST',one_pager:{valuation_model:m}},h={linkHtml:(url,label)=>`<a href="${url}">${label}</a>`};
  const html=W.render(t,h);
  assert.equal((html.match(/<dt>Annual IRR<\/dt>/g)||[]).length,3);
  assert.match(html,/Apply assumptions/);assert.match(html,/Reset to published inputs/);
  assert.match(html,/data-vm-chart="cash"/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
  m.anchor={period:'2025-12-31',value:10,calculation_inputs:[{label:'Operating cash flow',value:20000000,unit:'USD',period:'2025-12-31'},{label:'Diluted shares',value:2000000,unit:'shares',period:'2025-12-31'}]};
  const facts=W.render(t,h);
  assert.match(facts,/Reported inputs behind the per-share anchor/);assert.match(facts,/million shares/);assert.match(facts,/>20<\/td>/);
  m.inputs.anchor=null;
  const missing=W.render(t,h);
  assert.match(missing,/What is needed to calculate this model/);assert.doesNotMatch(missing,/NaN|Infinity|undefined/);
});
