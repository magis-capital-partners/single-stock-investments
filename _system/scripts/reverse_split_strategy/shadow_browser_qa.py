"""Verify the shadow dashboard using browser-only synthetic responses."""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright


async def check(base, output, chrome):
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    policies = [
        {'id': 'rs_immediate.v1', 'label': 'Immediate intraday · primary', 'primary': True},
        {'id': 'rs_wait5m.v1', 'label': 'Wait five minutes'},
    ]
    track = {'id': 'qa-track', 'event_id': 'qa-event', 'policy_id': 'rs_immediate.v1', 'ticker': 'QAONLY', 'cik': '123', 'company': 'Browser fixture only <img src=x onerror="window.fixtureExecuted=true">', 'state': 'open', 'reason': 'quote_bounded_simulated_entry', 'first_seen_at': now, 'published_at': now, 'signal_at': now, 'entry_at': now, 'exit_due_at': now, 'entry_shares': 100, 'remaining_shares': 100, 'entry_price': 10, 'mark_price': 9, 'mark_at': now, 'net_pnl': 90, 'borrow_cost': 8, 'commissions': 2, 'fills': [{'side': 'short', 'at': now, 'shares': 100, 'price': 10, 'commission': 1}], 'feasibility': {'state': 'unverified'}, 'decision_snapshot': {'score': 75, 'ordinal_min': 2, 'sources': []}}
    summary = {'started_at': now, 'observed_events': 1, 'median_analysis_seconds': 4, 'p95_analysis_seconds': 4, 'market_data': {'status': 'available', 'quote_access': 'received'}, 'policies': [{**p, 'entered': 1, 'issuers': 1, 'open': 1, 'closed': 0, 'missed': 0, 'known_net_pnl': 90, 'unresolved_marks': 0, 'stale_marks': 0} for p in policies], 'limitations': ['Browser-only fixture. No production observations are seeded.']}
    mode = {'unavailable': False}
    hits = []

    async def api(route):
        url = route.request.url
        hits.append(url)
        path = url.split('/api/v1/reverse-splits/')[1].split('?')[0]
        envelope = {'research_only': True, 'authority': 'none'}
        if mode['unavailable']:
            await route.fulfill(status=503, content_type='application/json', body='{}')
            return
        if path == 'shadow':
            body = {**envelope, 'policies': policies, 'summary': summary, 'runtime': {'heartbeat_at': now, 'interval_seconds': 15, 'status': 'running'}, 'daily': [{'day': '2026-11-04', 'policy_id': 'rs_immediate.v1', 'known_net_pnl': 90}]}
        elif path == 'shadow/tracks':
            body = {**envelope, 'tracks': [] if 'NO_MATCH' in url else [track], 'next_cursor': None}
        elif path.startswith('shadow/tracks/'):
            body = {**envelope, 'track': track, 'records': [{'id': 'one', 'kind': 'enrolled', 'recorded_at': now, 'payload': {'reason': 'signal_pass'}}, {'id': 'two', 'kind': 'simulated_short', 'recorded_at': now, 'payload': {'side': 'short'}}], 'evidence': [], 'next_cursor': None}
        elif path == 'health':
            body = {'status': 'healthy', 'state': {'last_completed_tick': now}, 'counts': [], 'jobs': [], 'sources': []}
        else:
            body = {'policy': envelope, 'events': [], 'next_cursor': None}
        await route.fulfill(status=200, content_type='application/json', body=json.dumps(body))

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome, headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100}, accept_downloads=True, service_workers='block')
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.route('**/api/v1/reverse-splits/**', api)
        await page.goto(base + '/#/strategies/reverse-split/shadow')
        host = page.locator('[data-rss-shadow]')
        try:
            await host.locator('[data-rss-shadow-track]').wait_for(timeout=45000)
        except Exception:
            (output / 'failure.json').write_text(json.dumps({'hits': hits, 'errors': errors, 'body': await page.locator('body').inner_text()}), encoding='utf-8')
            await page.screenshot(path=str(output / 'failure.png'))
            raise
        assert 'Immediate intraday' in await host.inner_text()
        assert await page.evaluate('Boolean(window.fixtureExecuted)') is False
        await page.screenshot(path=str(output / 'shadow-desktop.png'), full_page=True)
        await host.locator('[data-rss-shadow-track]').click()
        await host.locator('[data-rss-shadow-detail]').wait_for()
        assert 'No broker execution is verified' in await host.inner_text()
        assert await host.locator('[data-rss-shadow-detail] tbody tr').count() >= 6
        await page.screenshot(path=str(output / 'shadow-audit.png'), full_page=True)
        async with page.expect_download() as info:
            await host.locator('[data-rss-shadow-export="detail"]').click()
        await (await info.value).save_as(str(output / 'displayed-audit.json'))
        await host.locator('[data-rss-shadow-close]').click()
        async with page.expect_download() as info:
            await host.locator('[data-rss-shadow-export="csv"]').click()
        await (await info.value).save_as(str(output / 'displayed.csv'))
        assert len((output / 'displayed.csv').read_text().splitlines()) == 2
        await host.locator('[data-rss-shadow-query]').fill('NO_MATCH')
        await host.locator('[data-rss-shadow-search]').click()
        await page.wait_for_function("!document.querySelector('[data-rss-shadow-track]')")
        assert 'No decisions match' in await host.inner_text()
        await host.locator('[data-rss-shadow-query]').fill('')
        await host.locator('[data-rss-shadow-search]').click()
        await host.locator('[data-rss-shadow-track]').wait_for()
        mode['unavailable'] = True
        await host.locator('[data-rss-shadow-refresh]').click()
        await host.locator('[role="alert"]').wait_for()
        assert await host.locator('[data-rss-shadow-track]').count() == 1
        mode['unavailable'] = False
        await host.locator('[data-rss-shadow-refresh]').click()
        await page.wait_for_function("!document.querySelector('[data-rss-shadow] [role=alert]')")
        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.screenshot(path=str(output / 'shadow-mobile.png'), full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
        await page.locator('[data-rss-section="live"]').first.click()
        await page.locator('[data-rsl-live]').wait_for()
        await page.locator('[data-rss-section="shadow"]').first.click()
        await page.locator('[data-rss-shadow-track]').wait_for()
        assert page.url.endswith('/shadow')
        assert not errors, errors
        await browser.close()
    print(json.dumps({'browser_checks': 'passed', 'screenshots': str(output), 'page_errors': errors}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8871')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--chrome', default='C:/Program Files/Google/Chrome/Application/chrome.exe')
    args = parser.parse_args()
    asyncio.run(check(args.base_url, args.output, args.chrome))
