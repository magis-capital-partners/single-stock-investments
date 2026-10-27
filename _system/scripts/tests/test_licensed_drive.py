"""Licensed Drive ingest: parsers, public guard, vault writes, org plan."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from expert_call_match import (  # noqa: E402
    CompanyMatcher,
    plan_expert_calls,
    summarize_plan,
)
from licensed_drive_common import (  # noqa: E402
    assert_public_metadata,
    strip_audit,
    strip_filename_index,
)
from licensed_publish import upsert_licensed_sources, valueline_public  # noqa: E402
from licensed_vault import import_documents, prepare_tree  # noqa: E402
from valueline_names import classify_valueline_file, parse_company_report  # noqa: E402

CURRENT = "1Vkxdo3k6HqLkqR0QO6in8KMTkm3r57FJ"
ROOT = SCRIPTS.parents[1]


def _vl(**kwargs):
    base = {
        "name": "Zoetis_ZTS_2026-01-02.pdf",
        "file_id": "file-1",
        "parents": [CURRENT],
        "web_view": "https://drive.google.com/file/d/file-1/view",
        "path": "",
        "registry": {"ZTS": "Zoetis", "IREN": "IREN", "BRK-B": "Berkshire Hathaway"},
        "aliases": {},
        "edition_by_id": {CURRENT: "current"},
    }
    base.update(kwargs)
    return classify_valueline_file(**base)


class ValueLineNameTest(unittest.TestCase):
    def test_industry_slot_still_uses_the_ticker_token(self) -> None:
        parsed = parse_company_report("Digital Infrastructure_IREN_2026-03-04.pdf")
        self.assertEqual(parsed["ticker"], "IREN")
        self.assertEqual(parsed["company"], "Digital Infrastructure")

    def test_hyphenated_ticker_is_not_split(self) -> None:
        parsed = parse_company_report("Berkshire Hathaway_BRK-B_2026-03-04.pdf")
        self.assertEqual(parsed["ticker"], "BRK-B")

    def test_html_ampersand_does_not_change_the_ticker(self) -> None:
        parsed = parse_company_report("Metals &amp; Mining (Div.)_BHP_2026-03-04.pdf")
        self.assertEqual(parsed["ticker"], "BHP")

    def test_unknown_ticker_is_unmatched_not_guessed(self) -> None:
        row = _vl(name="BioXcel Therapeutics_BTAI_2026-03-04.pdf")
        self.assertEqual(row["status"], "unmatched")
        self.assertEqual(row["reason"], "ticker_not_in_registry")
        self.assertEqual(row["parsed_ticker"], "BTAI")
        self.assertEqual(row["ticker"], "")

    def test_alias_maps_only_when_the_target_is_in_the_registry(self) -> None:
        row = _vl(
            name="Old Name_BTAI_2026-03-04.pdf",
            aliases={"BTAI": "ZTS"},
        )
        self.assertEqual(row["status"], "matched")
        self.assertEqual(row["ticker"], "ZTS")
        self.assertEqual(row["reason"], "alias")

    def test_survey_and_monthly_issue_have_no_ticker(self) -> None:
        survey = _vl(
            name="Value Line Investment Survey 2026.9.18.pdf",
            parents=["1_IWMLwwMLu5VUvDzfy33GgkjqxuHrxLO"],
            edition_by_id={"1_IWMLwwMLu5VUvDzfy33GgkjqxuHrxLO": "full_survey"},
        )
        self.assertEqual(survey["status"], "survey")
        self.assertEqual(survey["ticker"], "")
        issue = _vl(
            name="SS_2026-09-18.pdf",
            parents=["1wnqyCJLNXoLMOJcVL7czHh-1fkIizCOu"],
            edition_by_id={"1wnqyCJLNXoLMOJcVL7czHh-1fkIizCOu": "special_situations"},
        )
        self.assertEqual(issue["status"], "special_situation_issue")

    def test_public_label_prefers_the_current_edition(self) -> None:
        rows = [
            _vl(name="Zoetis_ZTS_2020-01-01.pdf", file_id="old", parents=["old-id"], edition_by_id={"old-id": "old"}),
            _vl(),
        ]
        by_ticker, _insights = valueline_public(rows)
        self.assertEqual(by_ticker["ZTS"]["report_date"], "2026-01-02")
        self.assertEqual(by_ticker["ZTS"]["label"], "ValueLine report dated 2026-01-02 available")
        self.assertIn("drive_url", by_ticker["ZTS"])


class ExpertPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = CompanyMatcher(
            {"ZTS": "Zoetis", "FNV": "Franco-Nevada Corporation", "AAA": "Acme Holdings", "BBB": "Acme Group"}
        )

    def _plan(self, rows):
        return plan_expert_calls(rows, self.matcher)

    def test_matched_pair_is_renamed_into_the_ticker_folder(self) -> None:
        plans = self._plan(
            [
                {
                    "Name": "2024-04-26 Director at a Precious Metals Streaming Company  Franco-Nevada Corporation.docx",
                    "Size": 20000,
                    "ID": "docx1",
                },
                {
                    "Name": "2024-04-26 Director at a Precious Metals Streaming Company  Franco-Nevada Corporation.md",
                    "Size": 4000,
                    "ID": "md1",
                },
            ]
        )
        summary = summarize_plan(plans)
        self.assertEqual(summary["ticker_files"], 2)
        self.assertEqual(summary["ticker_folders"], 1)
        md = next(row for row in plans if row["extension"] == "md")
        self.assertEqual(md["dest_folder"], "Expert Calls/FNV")
        self.assertTrue(md["new_name"].startswith("2024-04-26_FNV_"))
        self.assertIn("Franco-Nevada", md["new_name"])
        self.assertNotEqual(md["new_name"], md["original_name"])

    def test_low_confidence_keeps_its_name_in_unmatched(self) -> None:
        plans = self._plan(
            [
                {"Name": "2024-01-01 Analyst at Somewhere  No Such Company Worldwide.docx", "Size": 2000, "ID": "d"},
                {"Name": "2024-01-01 Analyst at Somewhere  No Such Company Worldwide.md", "Size": 2000, "ID": "m"},
            ]
        )
        self.assertTrue(all(row["bucket"] == "unmatched" for row in plans))
        self.assertTrue(all(row["new_name"] == row["original_name"] for row in plans))
        self.assertTrue(all(row["dest_folder"] == "Expert Calls/_Unmatched" for row in plans))

    def test_copy_stub_orphan_and_vic_go_to_their_buckets(self) -> None:
        base = "2024-05-01 Vet at a Clinic  Zoetis"
        plans = self._plan(
            [
                {"Name": f"{base}.docx", "Size": 3000, "ID": "base-docx"},
                {"Name": f"{base}.md", "Size": 3000, "ID": "base-md"},
                {"Name": f"{base} (1).docx", "Size": 3000, "ID": "copy-docx"},
                {"Name": "2024-06-01 Empty note  Zoetis.md", "Size": 40, "ID": "stub-md"},
                {"Name": "2024-06-01 Empty note  Zoetis.docx", "Size": 9000, "ID": "stub-docx"},
                {"Name": "2024-07-01 Orphan note  Zoetis.docx", "Size": 9000, "ID": "orphan"},
                {"Name": "2026-01-01 HQI Hirequest Inc.pdf", "Size": 50000, "ID": "vic"},
            ]
        )
        by_id = {row["file_id"]: row for row in plans}
        self.assertEqual(by_id["copy-docx"]["bucket"], "duplicate")
        self.assertEqual(by_id["copy-docx"]["reason"], "copy_suffix")
        self.assertEqual(by_id["stub-md"]["reason"], "empty_or_stub")
        self.assertEqual(by_id["stub-docx"]["bucket"], "duplicate")
        self.assertEqual(by_id["orphan"]["reason"], "orphan_copy")
        self.assertEqual(by_id["vic"]["bucket"], "misfiled_vic")
        self.assertEqual(by_id["vic"]["dest_folder"], "Admin/Intake/VIC/HQI")
        self.assertEqual(by_id["base-md"]["bucket"], "ticker")

    def test_parenthetical_country_is_not_a_copy(self) -> None:
        plans = self._plan(
            [
                {"Name": "2024-08-01 Guide (US) at a Park  Zoetis.docx", "Size": 3000, "ID": "d"},
                {"Name": "2024-08-01 Guide (US) at a Park  Zoetis.md", "Size": 3000, "ID": "m"},
            ]
        )
        self.assertTrue(all(row["bucket"] == "ticker" for row in plans))

    def test_new_root_upload_is_filed_and_existing_subfolder_is_left(self) -> None:
        name = "2024-09-01 Scientist at a Lab  Zoetis"
        plans = self._plan(
            [
                {"Name": f"{name}.docx", "Size": 3000, "ID": "new-d", "parent_name": "Expert Calls", "parents": ["root"]},
                {"Name": f"{name}.md", "Size": 3000, "ID": "new-m", "parent_name": "Expert Calls", "parents": ["root"]},
                {"Name": "already.docx", "Size": 3000, "ID": "old", "parent_name": "ZTS", "parents": ["zts-folder"]},
            ]
        )
        by_id = {row["file_id"]: row for row in plans}
        self.assertEqual(by_id["new-m"]["bucket"], "ticker")
        self.assertEqual(by_id["new-m"]["source_parents"], ["root"])
        self.assertEqual(by_id["old"]["bucket"], "already_filed")
        self.assertEqual(by_id["old"]["new_name"], "already.docx")

    def test_a_short_prefix_does_not_claim_a_longer_company(self) -> None:
        matcher = CompanyMatcher({"0388.HK": "Hong Kong Exchanges and Clearing Ltd", "A": "Agilent Technologies"})
        long_role = "Former Senior Vice President of Global Operations at a Regional Clearing Office"
        names = {
            "hk-m": f"2025-04-03 {long_role}  Hong Kong.md",
            "a-m": f"2025-10-02 {long_role}  Agilent Technologie.md",
        }
        self.assertGreaterEqual(len(names["hk-m"]), 100)
        self.assertGreaterEqual(len(names["a-m"]), 100)
        plans = plan_expert_calls(
            [
                {"Name": names["hk-m"].replace(".md", ".docx"), "Size": 3000, "ID": "hk-d"},
                {"Name": names["hk-m"], "Size": 3000, "ID": "hk-m"},
                {"Name": names["a-m"].replace(".md", ".docx"), "Size": 3000, "ID": "a-d"},
                {"Name": names["a-m"], "Size": 3000, "ID": "a-m"},
            ],
            matcher,
        )
        by_id = {row["file_id"]: row for row in plans}
        self.assertEqual(by_id["hk-m"]["bucket"], "unmatched")
        self.assertEqual(by_id["a-m"]["bucket"], "ticker")
        self.assertEqual(by_id["a-m"]["ticker"], "A")

    def test_ambiguous_normalized_names_stay_unmatched(self) -> None:
        plans = self._plan(
            [
                {"Name": "2024-01-02 Analyst at a Shop  Acme.docx", "Size": 2000, "ID": "d"},
                {"Name": "2024-01-02 Analyst at a Shop  Acme.md", "Size": 2000, "ID": "m"},
            ]
        )
        self.assertTrue(all(row["bucket"] == "unmatched" for row in plans))


class PublicAndVaultTest(unittest.TestCase):
    def test_public_metadata_rejects_transcripts(self) -> None:
        with self.assertRaises(ValueError):
            assert_public_metadata({"by_ticker": {"ZTS": {"text": "secret transcript"}}})
        with self.assertRaises(ValueError):
            assert_public_metadata({"label": "x" * 401})

    def test_upsert_replaces_one_section_only(self) -> None:
        existing = {"by_ticker": {"ZTS": {"expert_calls": [{"date": "2024-01-01", "label": "Expert call dated 2024-01-01"}]}}}
        merged = upsert_licensed_sources(existing, valueline={"ZTS": {"label": "ValueLine report dated 2026-01-02 available", "report_date": "2026-01-02", "edition": "current", "drive_url": "https://drive.google.com/file/d/x/view"}})
        self.assertIn("expert_calls", merged["by_ticker"]["ZTS"])
        self.assertIn("valueline", merged["by_ticker"]["ZTS"])

    def test_strip_keeps_a_letter_that_mentions_valueline(self) -> None:
        index = {
            "pdf_count": 2,
            "by_filename": {
                "zoetis_zts_2026-01-02.pdf": {
                    "name": "Zoetis_ZTS_2026-01-02.pdf",
                    "id": "vl",
                    "parents": [CURRENT],
                    "webViewLink": "https://drive.google.com/file/d/vl/view",
                },
                "valueline special situations 2018.12.pdf": {
                    "name": "Valueline Special Situations 2018.12.pdf",
                    "id": "letter",
                    "parents": ["1nXJqlnGzigKsss8gNILUyrgrdapTYf42"],
                    "webViewLink": "https://drive.google.com/file/d/letter/view",
                },
            },
        }
        stripped, removed = strip_filename_index(index)
        self.assertEqual(removed, 1)
        self.assertEqual(set(stripped["by_filename"]), {"valueline special situations 2018.12.pdf"})
        audit = {
            "summary": {"drive_pdf_count": 2, "registry_uploaded_count": 0},
            "orphan_drive_pdfs": [
                {"id": "vl", "name": "Zoetis_ZTS_2026-01-02.pdf", "parents": [CURRENT]},
                {"id": "letter", "name": "Valueline Special Situations 2018.12.pdf", "parents": ["1nXJqlnGzigKsss8gNILUyrgrdapTYf42"]},
            ],
            "missing_sha_app_property": [],
            "duplicate_sha": {},
        }
        cleaned, excluded = strip_audit(audit, extra_ids={"vl"})
        self.assertEqual(excluded, 1)
        self.assertEqual(cleaned["summary"]["drive_pdf_count"], 1)
        self.assertEqual(cleaned["orphan_drive_pdfs"][0]["id"], "letter")

    def test_vault_stores_text_and_skips_the_second_time(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = prepare_tree(Path(tmp), "valueline")
            ignore = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("*.pdf", ignore)
            job = {
                "file_id": "abc",
                "relative": "ZTS/current/2026-01-02.txt",
                "meta": {"ticker": "ZTS", "drive_url": "https://drive.google.com/file/d/abc/view"},
            }

            def download(_file_id: str) -> bytes:
                return b"pdf-bytes-not-stored"

            def decode(_data: bytes) -> str:
                return "Value Line company report extract. " * 4

            first = import_documents(root=root, jobs=[job], download=download, decode=decode, dry_run=False)
            self.assertEqual(first["written"], 1)
            text_path = root / "ZTS" / "current" / "2026-01-02.txt"
            self.assertTrue(text_path.exists())
            self.assertEqual(list(root.rglob("*.pdf")), [])
            second = import_documents(root=root, jobs=[job], download=download, decode=decode, dry_run=False)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(second["written"], 0)

    def test_vault_refuses_pdf_bytes_and_the_public_tree(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = prepare_tree(Path(tmp), "expert-calls")
            job = {"file_id": "bad", "relative": "ZTS/note.md", "meta": {}}

            def download(_file_id: str) -> bytes:
                return b"%PDF-1.4 fake"

            def decode(data: bytes) -> str:
                return data.decode("utf-8")

            counts = import_documents(root=root, jobs=[job], download=download, decode=decode, dry_run=False)
            self.assertEqual(counts["errors"], 1)
            self.assertEqual(list(root.rglob("*.md")), [])
        with self.assertRaises(RuntimeError):
            prepare_tree(ROOT / "dashboard", "valueline")

    def test_organize_module_exposes_apply_and_does_not_remove_files(self) -> None:
        text = (SCRIPTS / "organize_expert_calls_drive.py").read_text(encoding="utf-8")
        self.assertIn("--apply", text)
        self.assertNotIn("files().delete", text)
        self.assertNotIn("trash", text.lower())


if __name__ == "__main__":
    unittest.main()
