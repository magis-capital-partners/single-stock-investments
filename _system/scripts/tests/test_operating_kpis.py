"""Fixture tests for issuer operating KPIs. No network."""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_kpi_trends import apply_display_cap  # noqa: E402
from operating_kpis.cboe import parse_cboe_xlsx  # noqa: E402
from operating_kpis.cme import parse_cme_release  # noqa: E402
from operating_kpis.ice import parse_ice_release  # noqa: E402
from operating_kpis.miax import parse_miax_text  # noqa: E402
from operating_kpis.model import LayoutError, attach_yoy, make_point  # noqa: E402
from operating_kpis.occ import parse_occ_csv, points_from_months  # noqa: E402
from operating_kpis.trends import select_shard_series  # noqa: E402
from scaffold_industry_kpi_ledgers import merge_template_kpis  # noqa: E402

FIXTURE = ROOT / "_system" / "scripts" / "tests" / "fixtures" / "operating_kpis" / "miax_2026_layout.txt"
FETCHED = "2026-10-20T00:00:00Z"


def _by_kpi(points: list[dict]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for point in points:
        out.setdefault(point["kpi"], {})[point["period"]] = point["value"]
    return out


class MiaxLayoutTests(unittest.TestCase):
    def test_september_levels_and_december_excludes_year_to_date(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        points = parse_miax_text(
            text,
            source_url="https://ir.miaxglobal.com/image/MIH_Volume_and_RPC_Report_10062026.pdf",
            doc="MIH_Volume_and_RPC_Report_10062026.pdf",
            fetched_at=FETCHED,
        )
        values = _by_kpi(points)
        self.assertEqual(values["options_adv"]["2026-09"], 10_712_000)
        self.assertEqual(values["options_industry_adv"]["2026-09"], 64_239_000)
        self.assertEqual(values["options_share"]["2026-09"], 16.7)
        self.assertEqual(values["options_rpc"]["2026-09"], 0.098)
        self.assertEqual(values["equities_adv"]["2026-09"], 103_000_000)
        self.assertEqual(values["equities_share"]["2026-09"], 0.6)
        self.assertEqual(values["equities_capture"]["2026-09"], 0.010)
        self.assertEqual(values["futures_ag_adv"]["2026-09"], 8036)
        self.assertEqual(values["futures_ag_rpc"]["2026-09"], 2.323)
        self.assertEqual(values["futures_financial_adv"]["2026-09"], 2226)
        self.assertEqual(values["futures_financial_rpc"]["2026-09"], -1.432)
        self.assertNotIn("2026-10", values["options_adv"])
        self.assertNotIn("2026-12", values["options_adv"])
        # Year-to-date industry ADV is 64,327 thousand. It must not land on December.
        self.assertNotIn(64_327_000, values["options_industry_adv"].values())
        share = next(point for point in points if point["kpi"] == "options_share")
        self.assertEqual(share["unit"], "share_pct")
        self.assertEqual(share["yoy_basis"], "percentage_points")

    def test_missing_header_is_a_layout_error(self) -> None:
        with self.assertRaises(LayoutError):
            parse_miax_text("no table here\n", source_url="u", doc="d", fetched_at=FETCHED)


class YoyTests(unittest.TestCase):
    def test_share_yoy_is_percentage_points_and_prose_yoy_is_kept(self) -> None:
        points = [
            make_point(
                ticker="MIAX", kpi="options_share", period="2025-09", value=17.6,
                unit="share_pct", source_url="u", doc="d", fetched_at=FETCHED,
                yoy_basis="percentage_points",
            ),
            make_point(
                ticker="MIAX", kpi="options_share", period="2026-09", value=16.7,
                unit="share_pct", source_url="u", doc="d", fetched_at=FETCHED,
                yoy_basis="percentage_points",
            ),
            make_point(
                ticker="CME", kpi="total_adv", period="2026-09", value=31_800_000,
                unit="contracts_per_day", source_url="u", doc="d", fetched_at=FETCHED,
            ),
        ]
        points[-1]["yoy"] = 0.22
        attached = {(row["ticker"], row["period"]): row for row in attach_yoy(points)}
        share = attached[("MIAX", "2026-09")]
        self.assertEqual(share["yoy_basis"], "percentage_points")
        self.assertEqual(share["yoy"], -0.9)
        self.assertEqual(attached[("CME", "2026-09")]["yoy"], 0.22)


def _xlsx(rows: list[list[str]], *, sheet_name: str = "2026") -> bytes:
    def col_name(index: int) -> str:
        name = ""
        index += 1
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row):
            if value == "":
                continue
            ref = f"{col_name(col_index)}{row_index}"
            escaped = (
                value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as book:
        book.writestr("[Content_Types].xml", content_types)
        book.writestr("_rels/.rels", root_rels)
        book.writestr("xl/workbook.xml", workbook)
        book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class CboeWorkbookTests(unittest.TestCase):
    def test_scales_adv_share_and_rpc_and_skips_off_exchange(self) -> None:
        header = ["Period", "Jan-26", "Feb-26", "Mar-26", "Apr-26", "May-26", "Jun-26", "Jul-26", "Aug-26", "Sep-26"]
        rows = [
            header,
            ["ADV/ADNV"],
            ["Multiply-listed options", "1", "1", "1", "1", "1", "1", "1", "1", "15.382"],
            ["Index options", "1", "1", "1", "1", "1", "1", "1", "1", "2"],
            ["Futures - ADV", "1", "1", "1", "1", "1", "1", "1", "1", "0.4"],
            ["U.S. Equities - Exchange - ADV", "1", "1", "1", "1", "1", "1", "1", "1", "1.5"],
            ["U.S. Equities - Off-Exchange - ADV", "9", "9", "9", "9", "9", "9", "9", "9", "9"],
            ["Market Share"],
            ["Multiply-listed options", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.167"],
            ["U.S. Equities - Exchange", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.05"],
            ["U.S. Equities - Off-Exchange", "0.9", "0.9", "0.9", "0.9", "0.9", "0.9", "0.9", "0.9", "0.9"],
            ["Rolling Three-Month RPC"],
            ["Multiply-listed options", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.1", "0.042"],
            ["Index options", "0.2", "0.2", "0.2", "0.2", "0.2", "0.2", "0.2", "0.2", "0.55"],
            ["Futures - per contract", "1", "1", "1", "1", "1", "1", "1", "1", "1.1"],
            ["ADV for Select Products"],
            ["SPX options", "1", "1", "1", "1", "1", "1", "1", "1", "3"],
            ["Mini VIX futures", "9", "9", "9", "9", "9", "9", "9", "9", "9"],
            ["VIX futures", "1", "1", "1", "1", "1", "1", "1", "1", "0.2"],
        ]
        points = parse_cboe_xlsx(_xlsx(rows), source_url="https://cdn.cboe.com/x.xlsx", doc="x.xlsx", fetched_at=FETCHED)
        values = _by_kpi(points)
        self.assertEqual(values["options_multilist_adv"]["2026-09"], 15382)
        self.assertEqual(values["options_multilist_share"]["2026-09"], 16.7)
        self.assertEqual(values["options_multilist_rpc"]["2026-09"], 0.042)
        self.assertEqual(values["us_equities_adv"]["2026-09"], 1_500_000_000)
        self.assertEqual(values["spx_options_adv"]["2026-09"], 3000)
        self.assertEqual(values["vix_futures_adv"]["2026-09"], 200)
        self.assertNotIn(9_000, values["options_multilist_adv"].values())
        self.assertNotIn(90.0, values["us_equities_share"].values())


class OccCsvTests(unittest.TestCase):
    def test_occ_totl_calls_plus_puts(self) -> None:
        text = """
ACTIVITY DATE : 09/30/2026
Calls
OCC-TOTL,456743189,0,0,0,21749675
OCC-TOTAL,999,0,0,0,999
Puts
OCC-TOTL,250190921,0,0,0,11913853
Monthly Totals
OCC-TOTAL,1400000000,0,0,0,999
"""
        parsed = parse_occ_csv(
            text, kind="equity", period="2026-09", source_url="https://marketdata.theocc.com/x", fetched_at=FETCHED
        )
        self.assertEqual(parsed["period"], "2026-09")
        self.assertEqual(parsed["contracts"], 456743189 + 250190921)
        self.assertEqual(parsed["adv"], 21749675 + 11913853)
        etf = dict(parsed)
        etf["kind"] = "etf"
        etf["adv"] = 30_000_000
        etf["contracts"] = 100
        points = points_from_months([parsed, etf], fetched_at=FETCHED)
        adv = next(point for point in points if point["kpi"] == "equity_etf_options_adv")
        self.assertEqual(adv["value"], parsed["adv"] + 30_000_000)
        self.assertEqual(adv["ticker"], "OCC")


class CmeIceTests(unittest.TestCase):
    def test_cme_prose_levels(self) -> None:
        text = (
            "CME Group reported September 2026 volume with 10.5 million contracts, up 12%. "
            "Interest Rate ADV increased 4% to 5.0 million. "
            "Metals ADV of 1.2 million."
        )
        points = parse_cme_release(text, source_url="u", doc="d", fetched_at=FETCHED)
        by_kpi = {point["kpi"]: point for point in points}
        self.assertEqual(by_kpi["total_adv"]["period"], "2026-09")
        self.assertEqual(by_kpi["total_adv"]["value"], 10_500_000)
        self.assertEqual(by_kpi["total_adv"]["yoy"], 0.12)
        self.assertEqual(by_kpi["interest_rate_adv"]["value"], 5_000_000)
        self.assertIsNone(by_kpi["metals_adv"]["yoy"])

    def test_ice_rates_without_levels_produce_no_points(self) -> None:
        text = "ICE September 2026 statistics. Total average daily volume (ADV) up 51% y/y."
        points, note = parse_ice_release(text, source_url="u", doc="d", fetched_at=FETCHED)
        self.assertEqual(points, [])
        self.assertIn("year-over-year", note or "")

    def test_ice_stated_level_is_kept(self) -> None:
        text = "September 2026. Total average daily volume (ADV) of 12.5 million."
        points, note = parse_ice_release(text, source_url="u", doc="d", fetched_at=FETCHED)
        self.assertIsNone(note)
        self.assertEqual(points[0]["kpi"], "total_adv")
        self.assertEqual(points[0]["value"], 12_500_000)


class VisibilityTests(unittest.TestCase):
    def test_operating_series_stay_visible_without_using_the_display_budget(self) -> None:
        metrics = [
            {
                "metric": f"options_{index}",
                "tier": "operating",
                "direction": "steady",
                "signal_type": "operating",
                "display": True,
            }
            for index in range(5)
        ]
        metrics.append(
            {
                "metric": "revenues",
                "tier": "primary",
                "direction": "accelerating",
                "signal_tier": "confirmed",
                "signal_type": "yoy",
                "strength": 2.0,
                "accel": 0.04,
                "threshold": 0.02,
            }
        )
        apply_display_cap(metrics)
        self.assertTrue(all(row["display"] for row in metrics if row["tier"] == "operating"))
        revenue = next(row for row in metrics if row["metric"] == "revenues")
        self.assertTrue(revenue["display"])

    def test_shard_keeps_every_operating_row(self) -> None:
        rows = [{"metric": f"op_{index}", "tier": "operating"} for index in range(4)]
        rows += [{"metric": f"fund_{index}", "tier": "primary"} for index in range(20)]
        selected = select_shard_series(rows)
        self.assertEqual(sum(1 for row in selected if row["tier"] == "operating"), 4)
        self.assertEqual(len(selected), 12)


class TemplateExclusionTests(unittest.TestCase):
    def test_msb_and_gyro_do_not_inherit_the_wrong_proxies(self) -> None:
        msb = {row["kpi_id"] for row in merge_template_kpis(["gold_royalty"], ticker="MSB")}
        peer = {row["kpi_id"] for row in merge_template_kpis(["gold_royalty"], ticker="FNV")}
        gyro = {row["kpi_id"] for row in merge_template_kpis(["water_surface"], ticker="GYRO")}
        water = {row["kpi_id"] for row in merge_template_kpis(["water_surface"], ticker="TPL")}
        self.assertNotIn("gold_spot_proxy", msb)
        self.assertNotIn("gdx_gld_ratio", msb)
        self.assertIn("gold_spot_proxy", peer)
        self.assertNotIn("tpl_water_revenue_m", gyro)
        self.assertIn("tpl_water_revenue_m", water)


if __name__ == "__main__":
    unittest.main()
