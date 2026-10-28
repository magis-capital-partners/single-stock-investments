// Optional full-SPA browser verification using an installed Playwright runtime.
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const {chromium}=require(process.env.SSI_PLAYWRIGHT_MODULE||'playwright');
const ROOT=path.resolve(__dirname,'../../..'),dashboard=path.join(ROOT,'dashboard');
async function main(){
 const shots=fs.mkdtempSync(path.join(os.tmpdir(),'third-plus-forward-'));
 const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());if(u.hostname!=='dashboard.test')return route.abort();
  const rel=decodeURIComponent(u.pathname).replace(/^\//,'')||'index.html',file=path.resolve(dashboard,rel);
  // Protected unrelated portfolio data is represented by an empty local fixture.
  if(rel==='data/core.json')return route.fulfill({json:{generated_at:new Date().toISOString(),summary:{ticker_count:0},tickers:[],watchlist:[]}});
  if(rel==='buyback-viz.js')return route.fulfill({body:'window.BuybackViz=null;',contentType:'application/javascript'});
  if(!file.startsWith(dashboard+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile())return route.fulfill({status:404,body:'{}',contentType:'application/json'});
  return route.fulfill({body:fs.readFileSync(file),contentType:({'.html':'text/html','.js':'application/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream'});
 });
 try{
  await page.goto('https://dashboard.test/#/ideas/short-alpha/forward');
  await page.locator('[data-tpf-policy]').waitFor({timeout:45000});
  assert.match(await page.locator('[data-third-plus-forward]').innerText(),/20-session/i);
  await page.locator('[data-tpf-policy]').selectOption('burn_control_h20');
  assert.equal(await page.locator('[data-tpf-policy]').inputValue(),'burn_control_h20');
  await page.locator('[data-tpf-search]').fill('no-such-forward-company');
  assert.match(await page.locator('[data-tpf-table]').innerText(),/No candidates match|No dated candidates/);
  await page.locator('[data-tpf-search]').fill('');
  await page.locator('[data-tpf-decision]').selectOption('before_policy');
  await page.locator('[data-tpf-decision]').selectOption('');
  const download=page.waitForEvent('download');await page.locator('[data-tpf-export]').click();
  assert.equal((await download).suggestedFilename(),'third-plus-forward-decisions.csv');
  await page.screenshot({path:path.join(shots,'desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'mobile overflow');
  await page.screenshot({path:path.join(shots,'mobile.png'),fullPage:true});
  await page.getByRole('link',{name:'Historical backtest',exact:true}).click();
  await page.getByRole('link',{name:/Follow the frozen 20-session policy/}).waitFor({timeout:45000});
  await page.getByRole('link',{name:/Follow the frozen 20-session policy/}).click();
  await page.locator('[data-tpf-policy]').waitFor({timeout:45000});
  assert.match(page.url(),/\/short-alpha\/forward$/);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({desktop:true,mobile:true,search:true,policy_switch:true,csv:true,routes:true,page_errors:errors,screenshots:shots}));
 }catch(error){console.error(JSON.stringify({page_errors:errors,url:page.url(),body:(await page.locator('body').innerText()).slice(0,2500)}));await page.screenshot({path:path.join(shots,'failure.png'),fullPage:true});console.error('Browser failure screenshot: '+path.join(shots,'failure.png'));throw error;}finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
