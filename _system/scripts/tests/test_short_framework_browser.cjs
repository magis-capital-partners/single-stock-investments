// Optional real-browser QA using installed Chromium/Edge and native CDP; no npm dependencies.
'use strict';
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const http = require('node:http'), { spawn } = require('node:child_process'), assert = require('node:assert/strict');
const ROOT = path.resolve(__dirname, '../../..');
async function main() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'short-framework-browser-'));
  const allowed = new Set(['short-framework-engine.js', 'short-framework-viz.js', 'short-profit-program.js', 'short-profit-program.css',
    'data/short_framework/manifest.json', 'data/short_framework/summary.json',
    'data/short_profit_program/manifest.json', 'data/short_profit_program/summary.json']);
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, 'http://localhost').pathname.slice(1);
    if (!name) { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/short-profit-program.css"><style>body{background:#10151c;color:#e6edf4;font:14px system-ui;margin:24px}main{max-width:1280px;margin:auto}</style></head><body><main class="spp" id="app"></main><script src="/short-framework-engine.js"></script><script src="/short-framework-viz.js"></script><script src="/short-profit-program.js"></script><script>app.innerHTML=ShortProfitProgram.render();ShortProfitProgram.attach(app);</script></body></html>'); return; }
    if (!allowed.has(name)) { res.writeHead(404); res.end(); return; }
    res.setHeader('Content-Type', name.endsWith('.js') ? 'application/javascript' : name.endsWith('.css') ? 'text/css' : 'application/json');
    res.end(fs.readFileSync(path.join(ROOT, 'dashboard', name)));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const executable = process.env.SHORT_FRAMEWORK_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const child = spawn(executable, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + path.join(dir, 'profile'), 'about:blank'], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let socket;
  try {
    const endpoint = await new Promise((resolve, reject) => {
      let buffer = '';
      const done = value => { clearTimeout(timer); clearInterval(probe); resolve(value); };
      const timer = setTimeout(() => { clearInterval(probe); reject(new Error('Browser startup timed out')); }, 15000);
      // Windows GUI builds write the endpoint file instead of console stderr.
      const probe = setInterval(() => {
        const filename = path.join(dir, 'profile', 'DevToolsActivePort');
        if (!fs.existsSync(filename)) return;
        const [port, endpointPath] = fs.readFileSync(filename, 'utf8').trim().split(/\r?\n/);
        if (port && endpointPath) done('ws://127.0.0.1:' + port + endpointPath);
      }, 100);
      child.on('error', error => { clearTimeout(timer); clearInterval(probe); reject(error); });
      child.stderr.on('data', chunk => { buffer += chunk; const found = buffer.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (found) done(found[1]); });
    });
    socket = new WebSocket(endpoint); await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Browser debugging connection timed out')), 8000);
      socket.onopen = () => { clearTimeout(timer); resolve(); }; socket.onerror = error => { clearTimeout(timer); reject(error); };
    });
    let seq = 0; const pending = new Map(), errors = [];
    socket.onmessage = event => { const message = JSON.parse(event.data);
      if (message.id) { const waiter = pending.get(message.id); pending.delete(message.id); if (waiter) message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result); }
      if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
    };
    const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => { const id = ++seq;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error('Browser command timed out: ' + method)); }, 8000);
      pending.set(id, { resolve: value => { clearTimeout(timer); resolve(value); }, reject: error => { clearTimeout(timer); reject(error); } });
      socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })); });
    const target = await send('Target.createTarget', { url: 'about:blank' }), attached = await send('Target.attachToTarget', { targetId: target.targetId, flatten: true }), session = attached.sessionId;
    const call = (method, params) => send(method, params, session);
    const evaluate = async expression => { const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value; };
    await call('Runtime.enable'); await call('Page.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: 1400, height: 1050, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: 'http://127.0.0.1:' + server.address().port + '/' });
    for (let n = 0; n < 100; n++) { if (await evaluate("!!document.querySelector('[data-spp-tab=framework]')")) break; await new Promise(resolve => setTimeout(resolve, 100)); }
    await evaluate("document.querySelector('[data-spp-tab=framework]').click()");
    for (let n = 0; n < 100; n++) { if (await evaluate("!!document.querySelector('[data-sf-control]')")) break; await new Promise(resolve => setTimeout(resolve, 100)); }
    assert.equal(await evaluate("document.querySelectorAll('.sf-gates article').length"), 10);
    assert.equal(await evaluate("document.querySelector('[data-sf-control=evidence]').value"), 'verified');
    assert.equal(await evaluate("document.querySelectorAll('.sf .spp-scroll table')[0].tBodies[0].rows.length"), 5);
    await evaluate("(()=>{const e=document.querySelector('[data-sf-control=evidence]');e.value='conditional';e.dispatchEvent(new Event('change',{bubbles:true}));})()");
    assert.match(await evaluate('document.body.innerText'), /assume borrowing and execution/);
    const desktop = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); fs.writeFileSync(path.join(dir, 'desktop.png'), Buffer.from(desktop.data, 'base64'));
    await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth + 1'), false, 'mobile page overflow');
    const mobile = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); fs.writeFileSync(path.join(dir, 'mobile.png'), Buffer.from(mobile.data, 'base64'));
    assert.deepEqual(errors, []);
    process.stdout.write(JSON.stringify({ desktop: true, mobile: true, filters: true, page_errors: errors, screenshots: dir }) + '\n');
  } finally {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ id: 999999, method: 'Browser.close' }));
    socket?.close(); child.kill(); await new Promise(resolve => server.close(resolve));
  }
}
main().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; });
