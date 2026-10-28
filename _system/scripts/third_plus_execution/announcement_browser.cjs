// Optional full-SPA check with an installed Playwright runtime; all data is local.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SSI_PLAYWRIGHT_MODULE||'playwright');
const ROOT=path.resolve(__dirname,'../../..'),dashboard=path.join(ROOT,'dashboard');
async function main(){
 const shots=fs.mkdtempSync(path.join(os.tmpdir(),'third-plus-announcement-'));
 const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(u.hostname!=='dashboard.test')return route.abort();
  const rel=decodeURIComponent(u.pathname).replace(/^\//,'')||'index.html',file=path.resolve(dashboard,rel);
  if(rel==='data/core.json')return route.fulfill({json:{generated_at:new Date().toISOString(),summary:{ticker_count:0},tickers:[],watchlist:[]}});
  if(rel==='buyback-viz.js')return route.fulfill({body:'window.BuybackViz=null;',contentType:'application/javascript'});
  if(!file.startsWith(dashboard+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile())return route.fulfill({status:404,body:'{}',contentType:'application/json'});
  return route.fulfill({body:fs.readFileSync(file),contentType:({'.html':'text/html','.js':'application/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream'});
 });
 try{
  await page.goto('https://dashboard.test/#/ideas/short-alpha/backtest');
  await page.getByRole('link',{name:/New: short from the announcement/}).waitFor({timeout:45000});
  await page.getByRole('link',{name:/New: short from the announcement/}).click();
  await page.locator('[data-tpa-control="ordinal"]').waitFor({timeout:45000});
  assert.equal(await page.locator('[data-tpa-control="ordinal"]').inputValue(),'all');
  assert.equal(await page.locator('[data-tpa-control="size"]').count(),0);
  assert.match(await page.locator('.tps-metrics').innerText(),/−\$180,017/);
  await page.locator('[data-tpa-control="ordinal"]').selectOption('first');
  assert.match(await page.locator('.tps-metrics').innerText(),/−\$296,472/);
  await page.locator('[data-tpa-ordinal="second"]').click();
  assert.match(await page.locator('.tps-metrics').innerText(),/\$46,057/);
  await page.locator('[data-tpa-ordinal="third_plus"]').click();
  assert.match(await page.locator('.tps-metrics').innerText(),/\$109,952/);
  await page.locator('[data-tpa-control="ordinal"]').selectOption('all');
  await page.locator('[data-tpa-filter="burn_dilution"]').click();
  assert.match(await page.locator('.tps-metrics').innerText(),/\$134,675/);
  assert.equal(await page.locator('[data-tpa-control="filter"] option').count(),49);
  await page.locator('[data-tpa-timing="next_open"]').click();
  assert.match(await page.locator('.tps-metrics').innerText(),/Next regular-session open/);
  await page.locator('[data-tpa-control="holding"]').selectOption('scheduled_split20');
  assert.equal(await page.locator('[data-tpa-control="holding"]').inputValue(),'scheduled_split20');
  await page.locator('[data-tpa-control="cohort"]').selectOption('completed_matched');
  assert.equal(await page.locator('[data-tpa-timing]').count(),4);
  await page.locator('[data-tpa-control="scenario"]').selectOption('stress');
  await page.locator('[data-tpa-control="capacity"]').selectOption('unlimited');
  await page.locator('[data-tpa-control="capacity"]').selectOption('three');
  await page.locator('[data-tpa-control="scenario"]').selectOption('base');
  await page.locator('[data-tpa-control="holding"]').selectOption('entry20');
  await page.locator('[data-tpa-control="cohort"]').selectOption('scheduled_disclosures');
  await page.locator('[data-tpa-timing="announce_now"]').click();
  const download=page.waitForEvent('download');await page.locator('[data-tpa-export]').click();
  assert.equal((await download).suggestedFilename(),'announcement-short-comparison.csv');
  await page.screenshot({path:path.join(shots,'desktop.png'),fullPage:true});
  await page.screenshot({path:path.join(shots,'desktop-top.png')});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'mobile overflow');
  await page.screenshot({path:path.join(shots,'mobile.png'),fullPage:true});
  await page.getByRole('link',{name:'Forward observations',exact:true}).click();
  await page.locator('[data-tpf-policy]').waitFor({timeout:45000});
  await page.getByRole('link',{name:'Historical backtest',exact:true}).click();
  await page.getByRole('link',{name:/New: short from the announcement/}).waitFor({timeout:45000});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({desktop:true,mobile:true,six_controls:true,timing_selection:true,csv:true,routes:true,page_errors:errors,screenshots:shots}));
 }catch(e){console.error(JSON.stringify({page_errors:errors,url:page.url(),body:(await page.locator('body').innerText()).slice(0,3000)}));await page.screenshot({path:path.join(shots,'failure.png'),fullPage:true});console.error('Browser screenshot: '+path.join(shots,'failure.png'));throw e;}finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
