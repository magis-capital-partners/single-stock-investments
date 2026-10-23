
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SSI_PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(__dirname,'../../..'),read=p=>JSON.parse(fs.readFileSync(path.join(root,'dashboard/data',p),'utf8'));
(async()=>{
const shotDir=process.env.BUYBACK_SCREENSHOT_DIR || path.join(require('node:os').tmpdir(),'ssi-buyback-browser');fs.mkdirSync(shotDir,{recursive:true});
const m=read('buyback_manifest.json'),c=read(m.companies),events=read(m.events);
const selected=c.companies.find(r=>r.rank_eligible && r.buyback_yield_pct!==null && r.detail_ref);
assert.ok(selected);
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('https://buyback.test/**',async route=>{
 const url=new URL(route.request().url()),relative=decodeURIComponent(url.pathname.slice(1));
 if(relative===''){
  return route.fulfill({contentType:'text/html',body:'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/buyback.css"><style>body{background:#10131a;color:#e7eaf0;font:14px system-ui;margin:24px;}main{max-width:1200px;margin:auto}a{color:#72c8c3}table{width:100%}h1{font-size:24px}button{cursor:pointer}</style></head><body><main><h1>Buyback research</h1><div id="coverage"><div><input id="search" placeholder="Search"></div><table><tbody id="cells"></tbody></table></div><div id="screen"></div><div id="detail"></div><div id="events"></div><div id="signals"></div></main><script src="/buyback-viz.js"></script></body></html>'});
 }
 const file=path.join(root,'dashboard',relative);
 if(!file.startsWith(path.join(root,'dashboard')) || !fs.existsSync(file))return route.fulfill({status:404,body:'not found'});
 return route.fulfill({body:fs.readFileSync(file),contentType:relative.endsWith('.js')?'application/javascript':relative.endsWith('.css')?'text/css':'application/json'});
});
await page.goto('https://buyback.test/#/ideas/buybacks');
await page.evaluate(async ticker=>{
 await BuybackViz.load();const b=BuybackViz.company(ticker);
 document.getElementById('cells').innerHTML='<tr><td>'+ticker+'</td>'+BuybackViz.renderHoldingsCell({ticker,buyback:b})+'</tr>';
 BuybackViz.mountScreen(document.getElementById('screen'));
 document.getElementById('detail').innerHTML=BuybackViz.renderDetail({ticker,buyback:b});
},selected.ticker);
assert.equal(await page.locator('#buyback-coverage-controls').count(),0);
assert.equal(await page.locator('#screen #buyback-screen-controls').count(),1);
assert.equal(await page.locator('#screen table tbody tr').count()>0,true);
assert.equal(await page.locator('[data-bb-filter]').inputValue(),'focused');
await page.locator('#screen').screenshot({path:path.join(shotDir,'buyback-radar-desktop.png')});
const firstTicker=await page.locator('#screen tbody tr .bb-company a').first().innerText();
await page.locator('[data-bb-search]').fill(firstTicker);
assert.ok(await page.locator('#screen tbody tr').count()>0);
assert.ok((await page.locator('#screen tbody tr').count())<=30);
await page.locator('[data-bb-search]').fill('no-such-company-12345');
assert.equal(await page.locator('#screen tbody tr').count(),0);
await page.locator('[data-bb-reset]').click();
assert.equal(await page.locator('[data-bb-search]').inputValue(),'');
await page.locator('[data-bb-filter]').selectOption('all');
assert.equal(await page.locator('#screen tbody tr').count(),30);
await page.locator('[data-bb-page="1"]').click();
assert.match(await page.locator('.bb-pagination > span').innerText(),/^31/);
await page.locator('[data-bb-reset]').click();
await page.setViewportSize({width:390,height:844});
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'focused radar overflow on mobile');
await page.locator('#screen').screenshot({path:path.join(shotDir,'buyback-radar-mobile.png')});
await page.setViewportSize({width:1400,height:1000});
await page.waitForFunction(()=>document.querySelector('[data-bb-history]')?.textContent.includes('Actual outstanding shares'));
await page.locator('select[data-bb-filter]').selectOption('review');
assert.equal(await page.evaluate(()=>JSON.parse(localStorage.getItem('ssi-buyback-coverage-v2')).filter),'review');
await page.locator('.bb-saved-tools > summary').click();
await page.locator('[data-bb-screen-name]').fill('Review queue');
await page.locator('[data-bb-screen-save]').click();
assert.ok(await page.evaluate(()=>JSON.parse(localStorage.getItem('ssi-buyback-saved-screens-v2'))['Review queue']));
await page.locator('[data-bb-filter]').selectOption('all');
await page.locator('[data-bb-saved]').selectOption('Review queue');
assert.equal(await page.locator('[data-bb-filter]').inputValue(),'review');
await page.screenshot({path:path.join(shotDir,'buyback-desktop.png'),fullPage:true});
await page.setViewportSize({width:390,height:844});
await page.locator('#detail').scrollIntoViewIfNeeded();
const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
assert.equal(overflow,false,'page overflow on mobile');
await page.screenshot({path:path.join(shotDir,'buyback-mobile.png'),fullPage:true});
// Real browser exercises the reason gate, save, and same-observation persistence.
await page.evaluate(()=>{
 const row={ticker:'FIXTURE',issuer_id:'cik:test',company:'Browser test fixture',shares_end:'2026-06-30',change_1y_pct:3,change_5y_pct:-20,data_status:'verified',issuance_cause:'unresolved'};
 window.drawSignals=()=>{const host=document.getElementById('signals');host.innerHTML=BuybackViz.renderSignals([row],{});BuybackViz.attachSignals(host,window.drawSignals);};drawSignals();
});
await page.locator('[data-bb-disposition]').selectOption('dismiss');
await page.locator('[data-bb-save-disposition]').click();
assert.equal(await page.evaluate(()=>localStorage.getItem('ssi-buyback-dispositions-v2')),null);
await page.locator('[data-bb-reason]').fill('Acquisition shares confirmed in filing');
await page.locator('[data-bb-save-disposition]').click();
await page.waitForFunction(()=>localStorage.getItem('ssi-buyback-dispositions-v2')?.includes('Acquisition shares'));
await page.evaluate(()=>{
 document.getElementById('events').innerHTML=BuybackViz.renderEventDetails({event_type:'issuer_tender',price_low:23,price_high:23,terms_verified:true});
 BuybackViz.attachScenarios(document.getElementById('events'));
});
await page.locator('.bb-scenario summary').last().click();
const form=page.locator('[data-bb-scenario="tender"]');
for(const [k,v] of Object.entries({purchase:20,offer:23,acceptance:.5,unaccepted:18,fees:.1,days:30}))await form.locator('[name="'+k+'"]').fill(String(v));
await form.locator('button').click();assert.match(await form.locator('output').innerText(),/2.0%/);
assert.deepEqual(errors,[]);
console.log(JSON.stringify({ticker:selected.ticker,snapshot:m.snapshot_id,desktop:true,mobile:true,dispositions:true,tender:true,pageErrors:errors.length}));
await browser.close();
})().catch(e=>{console.error(e.stack);process.exit(1);});
