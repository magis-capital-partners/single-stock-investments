const {test}=require('node:test');
const assert=require('node:assert/strict');
const lib=require('../../../dashboard/company-research.js');
test('full text search reaches items after previous feed limits',()=>{
 const rows=Array.from({length:351},(_,i)=>({id:String(i),title:`Source ${i}`,category:'analysis',date:'2026-10-01',relationship:'direct'}));
 const found=lib.filter(rows,{query:'treasury exposure'},{treasury:['350'],exposure:['350']});
 assert.equal(found.length,1);assert.equal(found[0].id,'350');
 assert.equal(lib.filter(rows,{},null).length,351);
});
test('category, author, date and company context filters combine',()=>{
 const rows=[{id:'1',title:'Gold model',category:'models',author:'Fund A',date:'2026-10-01',relationship:'industry_context'},{id:'2',title:'Company report',category:'analysis',author:'Fund B',date:'2025-01-01',relationship:'direct'}];
 assert.equal(lib.filter(rows,{category:'models',relation:'industry_context',author:'fund a',from:'2026-01-01'},null)[0].id,'1');
 assert.equal(lib.filter(rows,{to:'2024-01-01'},null).length,0);
});
test('source text and URLs cannot execute markup',()=>{
 const html=lib.rowHTML({id:'1',title:'<script>alert(1)</script>',author:'<img src=x>',reason:'<b>read me</b>',category:'calls',processing_status:'indexed',availability:'available',locations:[{url:'javascript:alert(1)'}],passages:[{text:'<svg onload=x>',locator:'Page 1'}]});
 assert.doesNotMatch(html,/<script>|javascript:|<svg/);assert.match(html,/&lt;script&gt;/);
 assert.equal(lib.safeURL('javascript:alert(1)'),'');
});
test('search normalization matches the builder tokenizer',()=>{
 assert.deepEqual(lib.words('Café: BTC / Supply-Demand'),['cafe','btc','supply','demand']);
});
