"""Exercise the integrated strategy dashboard against a local static preview.

Reads published snapshots only; never opens a broker or market-data connection.
Requires Playwright and an installed Chrome browser.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright


async def check(base_url, output, chrome):
    output.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=chrome, headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
        live_event = {"id":"qa-event","ticker":"QAONLY","company":"Browser test fixture — not a live announcement", "cik":"123", "status":"scheduled", "ratio":10,"effective_date":"2026-11-02","published_at":"2026-10-29T13:00:00Z","first_seen_at":"2026-10-29T13:00:30Z","analyzed_at":"2026-10-29T13:00:40Z","result":"passes_screen","ordinal_min":2,"financials":{"score":75,"period":"2026-06-30","signals":{"cash_burn":{"value":0.5,"score":1,"weight":1.2}},"evidence":[]},"checks":{"repeat":{"state":"pass","reason":"One documented prior split"}},"sources":[],"evidence":[]}
        async def live_api(route):
            path = route.request.url.split('/api/v1/reverse-splits/')[1].split('?')[0]
            if path == 'health':
                body = {"status":"healthy","state":{"last_completed_tick":"2026-10-29T13:00:00Z"},"counts":[{"result":"passes_screen","count":1}],"jobs":[],"sources":[],"scope":"Browser test fixture only"}
            elif path == 'events':
                body = {"policy":{"authority":"none","research_only":True},"events":[live_event],"next_cursor":None}
            else:
                body = {"event":live_event,"decisions":[]}
            await route.fulfill(status=200,content_type='application/json',body=json.dumps(body))
        await page.route('**/api/v1/reverse-splits/**',live_api)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base_url + "/#/strategies/reverse-split/overview")
        host = page.locator("#reverse-split-strategy-panel [data-reverse-split-strategy]")
        await host.locator('[data-rss-section="trades"]').first.wait_for(timeout=45000)
        assert await host.get_attribute("data-scenario") == "announcement_h5_raw_target_base"
        assert "6,265,797" in await host.inner_text()
        await page.screenshot(path=str(output / "overview.png"), full_page=True)
        await host.locator('[data-rss-section="trades"]').first.click()
        assert page.url.endswith("/trades")
        assert await host.locator("[data-rss-trade]").count() == 21
        await host.locator("[data-rss-trade]").first.click()
        await host.locator("[data-rss-detail]").wait_for()
        detail = await host.locator("[data-rss-detail]").inner_text()
        for text in ["Every modeled execution", "Score evidence available before entry", "Every cash flow", "Every position mark"]:
            assert text in detail, text
        await page.screenshot(path=str(output / "trade-detail.png"), full_page=True)
        await host.locator("[data-rss-close-trade]").click()
        await host.locator('[data-rss-search="query"]').fill("NOT_A_REAL_TICKER")
        assert await host.locator("[data-rss-trade]").count() == 0
        await host.locator('[data-rss-search="query"]').fill("")
        assert await host.locator("[data-rss-trade]").count() == 21
        async with page.expect_download() as info:
            await host.locator('[data-rss-export="trades"]').click()
        download = await info.value
        await download.save_as(str(output / download.suggested_filename))
        assert len((output / download.suggested_filename).read_text().splitlines()) == 22
        for section in ["metrics", "assumptions", "comparisons", "screen", "provenance"]:
            await host.locator(f'[data-rss-section="{section}"]').first.click()
            assert page.url.endswith("/" + section)
            assert len(await host.locator("[data-rss-body]").inner_text()) > 200
            assert await host.locator('[role="alert"]').count() == 0
        await host.locator('[data-rss-section="overview"]').first.click()
        for control, value, scenario in [
            ("mode", "constrained", "announcement_h5_constrained_base"),
            ("h", "20", "announcement_h20_constrained_base"),
            ("timing", "post_split", "post_split_h20_constrained_base"),
            ("cost", "stress", "post_split_h20_constrained_stress"),
        ]:
            await host.locator(f'[data-rss-control="{control}"]').select_option(value)
            await page.wait_for_function("id => document.querySelector('#reverse-split-strategy-panel [data-reverse-split-strategy]').dataset.scenario === id", arg=scenario)
            if scenario == "announcement_h5_constrained_base":
                assert "−$133" in await host.inner_text()
        await page.goto(base_url + "/#/strategies/reverse-split/trades")
        await page.reload()
        await page.wait_for_function("document.querySelector('#reverse-split-strategy-panel [data-reverse-split-strategy]')?.dataset.rssReady === 'true'")
        assert await host.locator("[data-rss-trade]").count() == 21
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(output / "mobile-trades.png"), full_page=True)
        for section in ["trades", "overview"]:
            await host.locator(f'[data-rss-section="{section}"]').first.click()
            dimensions = await page.evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")
            assert dimensions["scroll"] <= dimensions["width"] + 1, dimensions
        await page.screenshot(path=str(output / "mobile-overview.png"), full_page=True)
        await page.set_viewport_size({"width": 1440, "height": 1100})
        await page.goto(base_url + "/#/ideas/short-alpha/backtest")
        research = page.locator('[data-rsr-research]')
        await research.get_by_text('First versus second versus third-or-later split',exact=True).wait_for(timeout=45000)
        assert page.url.endswith('/strategies/reverse-split/research')
        assert await page.locator('[data-spp-tab]').count() == 0
        assert await page.locator('#ideas-subnav a[data-view="short-alpha"]').count() == 0
        assert await page.locator('#strategies-subnav a[data-view="systematic-shorts"]').count() == 0
        await research.locator('[data-rsr-control="annTiming"]').select_option('announce_5m')
        await research.locator('[data-rsr-control="annFilter"]').select_option('only_S4')
        await research.locator('[data-rsr-control="annCost"]').select_option('stress')
        announcement_table = research.locator('table').filter(has=page.locator('caption',has_text='Announcement-entry results by documented split count'))
        assert await announcement_table.locator('tbody tr').count() == 4
        assert 'Net excluding imputed-price entries' in await announcement_table.text_content()
        await research.locator('[data-rsr-control="cost"]').select_option('stress')
        assert await research.locator('tbody tr').count() > 20
        await page.screenshot(path=str(output / 'research-comparisons.png'),full_page=True)
        await page.goto(base_url + '/#/strategies/systematic-shorts/forward')
        await page.wait_for_url('**/strategies/reverse-split/live')
        await host.locator('[data-rss-section="live"]').click()
        live = page.locator('[data-rsl-live]')
        await live.locator('[data-rsl-event="qa-event"]').wait_for(timeout=15000)
        await live.locator('[data-rsl-event="qa-event"]').click()
        await live.locator('[data-rsl-detail]').wait_for()
        assert 'Each strategy gate' in await live.inner_text()
        await page.screenshot(path=str(output / 'live-fixture.png'),full_page=True)
        await page.set_viewport_size({"width":390,"height":844})
        dimensions = await page.evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")
        assert dimensions['scroll'] <= dimensions['width']+1, dimensions
        await page.screenshot(path=str(output / 'mobile-live-fixture.png'),full_page=True)
        await host.locator('[data-rss-section="research"]').click()
        await page.locator('[data-rsr-research] h3').first.wait_for()
        dimensions = await page.evaluate("({width:innerWidth, scroll:document.documentElement.scrollWidth})")
        assert dimensions['scroll'] <= dimensions['width']+1, dimensions
        loaded = await page.evaluate("performance.getEntriesByType('resource').map(r=>r.name)")
        assert not any('/short-profit-program.js' in r or '/short-framework-viz.js' in r for r in loaded)
        assert not errors, errors
        result = {"ok": True, "browser_errors": errors, "trade_count": 21, "sections": 9,
                  "csv_rows": 21, "legacy_route_redirect": True, "live_fixture":True, "mobile_document_width": dimensions}
        (output / "browser-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--output", type=Path, default=Path("_system/data/reverse_splits/local/strategy_dashboard_qa"))
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"))
    args = parser.parse_args()
    asyncio.run(check(args.base_url.rstrip("/"), args.output, args.chrome))
