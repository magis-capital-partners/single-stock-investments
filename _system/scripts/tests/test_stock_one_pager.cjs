const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'../../..');
const context=vm.createContext({Intl,Date,Map,Set,URL,module:{exports:{}}});context.window=context;
for(const name of ['source-links.js','stock-one-pager.js'])vm.runInContext(fs.readFileSync(path.join(root,'dashboard',name),'utf8'),context);
const ui=context.StockOnePager;
const p=(period,value)=>({period,value,source:{ref:'https://example.com/filing'}});
const t={ticker:'CPRT',one_pager:{schema_version:'stock-one-pager.v1',profile:{type:'Operating company',description:'Auction marketplace',focus:'Cash generation',countercase:'Lower volumes',kpis:['revenue'],drivers:['Units','Price'],chart_metrics:['revenue']},financials:{fiscal_year_end:'07-31',latest_period:'2025-07-31',notes:[],series:[{id:'revenue',label:'Revenue',unit:'USD',statement:'income',annual:[p('2024-07-31',10),p('2025-07-31',12)],quarterly:[p('2024-10-31',1),p('2025-01-31',2),p('2025-04-30',3),p('2025-07-31',4)]},{id:'cash',label:'Cash',unit:'USD',statement:'balance',annual:[],quarterly:[p('2024-10-31',10),p('2025-01-31',20),p('2025-04-30',30),p('2025-07-31',40)]}]},model:{as_of:'2025-07-31',assumptions:[{label:'<script>unsafe</script>',component:'Business',kind:'estimate',unit:'ratio',values:{low:.02,base:.04,high:.06},source:{ref:'https://example.com/filing'}}],components:[]},risks:['Volumes fall']} };
const h={linkHtml:(url,label)=>`<a href="${url}">${label}</a>`,developments:[]};
test('six pilot tabs and existing aliases preserve the intended section',()=>{
 assert.equal(ui.tabs.length,6);assert.equal(ui.validTab('models'),'valuation');assert.equal(ui.validTab('evidence'),'sources');assert.equal(ui.validTab('buyback'),'business');
 assert.equal(ui.isPilot(t),true);assert.equal(ui.isPilot({ticker:'CPRT'}),false);assert.equal(ui.isPilot({ticker:'AAPL',one_pager:t.one_pager}),false);
});
test('TTM sums only four consecutive quarters and never sums balance sheet stocks',()=>{
 assert.equal(ui.pointsOf(t,'revenue','ttm')[0].value,10);
 assert.equal(ui.pointsOf(t,'cash','ttm').at(-1).value,40);
 const copy=JSON.parse(JSON.stringify(t));copy.one_pager.financials.series[0].quarterly.splice(1,1);
 assert.equal(ui.pointsOf(copy,'revenue','ttm').length,0);
});
test('financial history offers source links, period controls and accessible exact-value tables',()=>{
 const html=ui.render('financials',t,h,{});
 assert.match(html,/Trailing twelve months/);assert.match(html,/All available history/);assert.match(html,/exact values and sources follow/);
 assert.match(html,/Fiscal year ends 07-31/);assert.match(html,/FY 2025/);assert.match(html,/https:\/\/example.com\/filing/);
});
test('all inputs remain available and source text is escaped',()=>{
 const html=ui.render('valuation',t,h,{});
 assert.match(html,/All 1 model inputs/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.equal(ui.format(null),'—');assert.equal(ui.format(0),'0');
});
test('repaired and unavailable URLs work across canonical and legacy owners',()=>{
 const url='https://github.com/GoldmanDrew/single-stock-investments/blob/main/CPRT/research/note.pdf';
 context.SourceLinks.setIndex({repairs:{[url]:{url:null,status:'unavailable'}}});
 assert.equal(context.SourceLinks.resolve(url),null);
 assert.equal(context.SourceLinks.resolve(url.replace('GoldmanDrew','magis-capital-partners')),null);
 assert.equal(context.SourceLinks.resolve('javascript:alert(1)'),null);
 assert.match(context.SourceLinks.reference('_system/reference/sumzero-research/CPRT/note.txt'),/research-vault\/blob\/main\/sumzero-research/);
});
