"""Render the production BTC component with dashboard styles and real data.

Requires Playwright + Chromium. Uses only a local HTTP server. Screenshots and
the interaction report are written outside the repository by default.
"""
import argparse
import functools
import http.server
import json
import re
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir())/'ssi-btc-model-2033')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    head = (ROOT/'dashboard/index.html').read_text(encoding='utf-8').split('</head>')[0]
    head = re.sub(r'<script\b[^>]*>.*?</script>', '', head, flags=re.S)
    head = head.replace('<head>','<head><base href="/dashboard/">')
    html = head + '</head><body><main id="mount" style="max-width:1320px;margin:20px auto;padding:16px"></main></body></html>'

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                body = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

        def log_message(self,*args):
            pass

    handler = functools.partial(Handler,directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    doc = json.loads((ROOT/'dashboard/data/hk_snowball_model.json').read_text(encoding='utf-8'))
    errors = []
    report = {'in_base_irr':False, 'checks':[], 'screenshots':[]}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(url,wait_until='networkidle')
            page.add_script_tag(url=url+'/dashboard/btc-model-viz.js')
            page.add_script_tag(url=url+'/dashboard/insights-viz.js')
            page.evaluate('''doc => {
                document.querySelector('#mount').innerHTML=InsightsViz.renderHkSnowballPanel(doc);
                InsightsViz.attachWorldModelHistoryHandlers(document.querySelector('#mount'));
            }''',doc)
            assert page.locator('[data-btc-panel]').count()==1
            assert page.locator('[data-btc-chart]').inner_text().find('HK Q3')>=0
            for viewport,name in [({'width':1440,'height':1000},'desktop'),({'width':390,'height':844},'mobile')]:
                page.set_viewport_size(viewport)
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),name+' page overflow'
                screenshot=args.output/f'{name}.png'
                page.screenshot(path=str(screenshot),full_page=True)
                report['screenshots'].append(str(screenshot))
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('button',name='Supply through 2028').click()
            assert page.locator('[data-btc-chart] svg').get_attribute('aria-label').endswith('2028')
            assert 'HK Q3 ≈ $1M' not in page.locator('[data-btc-chart]').inner_text()
            page.get_by_role('button',name='Demand through 2033').click()
            page.get_by_label('Show free fit').check()
            assert 'Unconstrained demand diagnostic' in page.locator('[data-btc-chart]').inner_text()
            page.get_by_label('BTC power case').select_option('proxy')
            assert 'Production cost · power proxy' in page.locator('[data-btc-chart]').inner_text()
            page.get_by_label('Full history').check()
            assert '2011' in page.locator('[data-btc-chart]').inner_text()
            page.get_by_label('BTC power case').select_option('hk')
            page.get_by_label('Cost layers (HK power)').check()
            assert 'Electricity only' in page.locator('[data-btc-chart]').inner_text()
            page.get_by_text('Hardware costs and the $117k–$149k comparison',exact=True).click()
            assert page.get_by_role('link',name='Antminer S23 Hyd',exact=True).is_visible()
            assert page.locator('[data-btc-chart] svg').locator('path').count()>6
            assert not re.search(r'NaN|Infinity',page.locator('[data-btc-chart]').inner_html())
            assert not errors,errors
            report['checks']=['Production Insights renderer and event binding','Desktop/mobile layout without page overflow',
                              '2028/2033 horizon switch','Unconstrained overlay','Power proxy switch','Full history',
                              'Optional legacy cost layers','Hardware detail expansion','Finite chart geometry','No browser errors']
            browser.close()
    finally:
        server.shutdown()
    (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
