const test = require('node:test');
const assert = require('node:assert/strict');
const F = require('../../../dashboard/financial-changes.js');
const {matchedPeerSeries} = require('../../../dashboard/stock-research-explorer.js');

const cell = (value,prior,unit='USD',extra={}) => ({
  value,prior,unit,status:'ok',cadence:'quarterly',period:'2026-09-30',prior_period:'2025-09-30',...extra
});
const row = c => ({quarter:{revenue:c}});
test('negative or zero bases retain absolute units and margin changes use basis points',()=>{
  assert.deepEqual(F.delta(cell(8,-2)),{v:10,u:'USD'});
  assert.deepEqual(F.delta(cell(-2,0)),{v:-2,u:'USD'});
  assert.deepEqual(F.delta(cell(4,6,'percent')),{v:-200,u:'bp'});
  assert.equal(F.delta(cell(4,null)),null);
  assert.equal(F.matchesDivergence({quarter:{revenue:cell(4,2),operating_margin:cell(3,6,'percent')}},'quarter'),true);
});
test('sorting holds gaps last and keeps monetary amounts within their currencies',()=>{
  const data={rows:{A:row(cell(2,1)),B:row(cell(3,1)),C:row(cell(9,2,'CAD')),D:row(cell(99,0,'USD',{status:'stale'}))}};
  assert.deepEqual(F.sortTickers(data,Object.keys(data.rows),'revenue',-1,'level'),['C','B','A','D']);
  assert.deepEqual(F.sortTickers(data,Object.keys(data.rows),'revenue',1,'level'),['C','A','B','D']);
});
test('peer median and IQR require three matched issuers and disclose contributors',()=>{
  const rows={A:row(cell(100,100)),B:row(cell(110,100)),C:row(cell(120,100)),D:row(cell(130,100)),
    E:row(cell(500,100,'USD',{period:'2026-03-31'})),F:row(cell(200,50,'CAD'))};
  rows.A.peers=Object.fromEntries(['B','C','D','E','F'].map(t=>[t,'same industry']));
  const stats=F.peerStats({rows},'A','revenue','quarter','level');
  assert.deepEqual([stats.n,stats.low,stats.median,stats.high],[3,115,120,125]);
  rows.B.quarter.revenue.status='stale';
  assert.equal(F.peerStats({rows},'A','revenue','quarter','level').median,null);
});
test('indexed comparisons share a positive starting window',()=>{
  const p=(period,value)=>({period,value});
  const series=[{points:[p('2024-03-31',4),p('2025-03-31',8),p('2026-03-31',12)]},
                {points:[p('2025-04-02',2),p('2026-04-02',3)]}];
  assert.deepEqual(matchedPeerSeries(series,45).map(s=>s.points.map(p=>p.value)),[[100,150],[100,150]]);
  assert.deepEqual(matchedPeerSeries([series[0],{points:[p('2024-12-31',4)]}],45),[]);
});
