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
        strategy_tab = page.locator('[data-spp-tab="strategy"]')
        await strategy_tab.wait_for(timeout=45000)
        await strategy_tab.click()
        nested = page.locator('#short-alpha-content [data-reverse-split-strategy]')
        await nested.locator('[data-rss-section="trades"]').first.wait_for(timeout=45000)
        assert await nested.get_attribute("data-scenario") == "announcement_h5_raw_target_base"
        await nested.locator('[data-rss-section="trades"]').first.click()
        assert await nested.locator("[data-rss-trade]").count() == 21
        assert not errors, errors
        result = {"ok": True, "browser_errors": errors, "trade_count": 21, "sections": 7,
                  "csv_rows": 21, "nested_strategy_tab": True, "mobile_document_width": dimensions}
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
