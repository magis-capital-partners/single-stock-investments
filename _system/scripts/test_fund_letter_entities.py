from __future__ import annotations

import sqlite3

import fund_letter_entities as fe
import fund_letters as fl
import summarize_fund_letter_reader as reader


def resolve(ticker: str, idea: str, source: str = "") -> list[tuple[str, str | None, str]]:
    return [(row["status"], row["ticker"], row["reason"]) for row in fe.resolve_idea(ticker, idea, source or idea)]


def test_finance_acronyms_are_dropped_unless_the_company_is_named():
    assert resolve("FCF", "Free cash flow", "Free cash flow (FCF) rose to $40 million.") == [("dropped", None, "acronym")]
    assert resolve("ROIC", "Capital returns", "Return on invested capital (ROIC) reached 18%.") == [("dropped", None, "acronym")]
    assert resolve("EBITDA, NAV", "Valuation", "EBITDA grew; NAV per share rose.") == [("dropped", None, "acronym"), ("dropped", None, "acronym")]
    # The same letters are a security when the topic is the company the security master gives them.
    assert resolve("LNG", "Cheniere Energy short", "The fund was short Cheniere Energy (LNG).") == [("resolved", "LNG", "name")]
    assert resolve("LNG", "Gas exports", "Liquefied natural gas (LNG) exports will double.") == [("dropped", None, "acronym")]
    assert resolve("PM", "Philip Morris International", "Philip Morris International (PM) began trading in 2008.") == [("resolved", "PM", "name")]
    assert resolve("RMBS", "Rambus", "The fund was short Rambus (RMBS) ahead of the verdict.") == [("resolved", "RMBS", "name")]
    assert resolve("RMBS", "Non-agency mortgages", "Non-agency RMBS spreads tightened during the quarter.") == [("dropped", None, "acronym")]


def test_word_like_tickers_need_the_company():
    assert resolve("KEY", "KeyCorp", "KeyCorp was discussed in previous letters.") == [("resolved", "KEY", "name")]
    assert resolve("TECH", "Techne", "The fund remained short Techne (TECH).") == [("resolved", "TECH", "name")]
    # ALL is Allstate in the security master; this letter means América Latina Logística.
    assert resolve("ALL", "América Latina Logística", "The railway line of ALL is expected to raise margins.")[0][:2] == ("unresolved", None)


def test_a_ticker_used_by_a_different_company_today_is_not_counted():
    cases = [
        ("EP", "El Paso / Kinder Morgan", "El Paso (EP) contributed 30 basis points."),
        ("WTW", "Weight Watchers", "Weight Watchers (WTW) remains a top position."),
        ("NEM", "Neo Material Technologies", "Neo Material Technologies (TSX: NEM) was the largest contributor."),
        ("SJM", "SJM Holdings", "SJM Holdings was a winner in July."),
        ("UP", "Union Pacific", "For the quarter, revenues were UP 16%."),
    ]
    for ticker, idea, source in cases:
        rows = fe.resolve_idea(ticker, idea, source)
        assert [row["status"] for row in rows] == ["unresolved"], ticker
        assert rows[0]["ticker"] is None


def test_bloomberg_codes_share_classes_and_names_resolve_to_one_entity():
    assert resolve("TW, LN", "Taylor Wimpey PLC", "Taylor Wimpey (TW/ LN) is a UK house builder.") == [("resolved", "TW.L", "name")]
    rows = fe.resolve_idea("5019 JP, 5007 JP", "Japanese refineries", "The fund bought Idemitsu (5019 JP) and Cosmo Oil (5007 JP).")
    assert [(r["status"], r["ticker"], r["exchange"]) for r in rows] == [("resolved", "5019.T", "JP"), ("resolved", "5007.T", "JP")]
    assert [r["ticker"] for r in fe.resolve_idea("14 HK", "Hysan Development", "Hysan Development (14 HK) was a winner on the short side.")] == ["0014.HK"]
    veolia = fe.resolve_idea("VIE.FP", "Veolia Environment", "We bought Veolia Environment (VIE.FP) in May.")
    assert [(r["status"], r["ticker"]) for r in veolia] == [("resolved", "VIE.PA")]
    assert fe.normalize("600519.SS")[0] == "600519.SS" and fe.normalize("BRK.TO")[0] == "BRK.TO"
    assert resolve("BRK.A, BRK.B", "Berkshire Hathaway", "Berkshire Hathaway BRK.A and BRK.B") == [("resolved", "BRK.B", "name")]
    assert resolve("GOOG", "Google", "Teton has been accumulating Google (GOOG).") == [("resolved", "GOOG", "name")]
    assert resolve("CIT", "CIT Group", "The fund holds bonds in CIT Group Inc.") == [("resolved", "CIT", "name")]
    assert resolve("GOODRICH CORP", "Top positions", "Goodrich Corp") == [("unresolved", None, "not_a_symbol")]


def test_a_letter_printing_the_ticker_resolves_it_when_the_master_has_no_better_name():
    source = "The second strongest long was Venoco (VQ, $10.78, 8% of assets)."
    assert resolve("VQ", "Venoco", source) == [("resolved", "VQ", "printed")]
    assert resolve("VQ", "Venoco", "Venoco was the second strongest long.")[0][0] == "unresolved"


def test_summarizer_keeps_tickers_only_where_the_resolver_would():
    assert reader.verified_ticker({"ticker": "ROIC", "subject": "Returns on capital"}, "Return on invested capital (ROIC) reached 18%.") is None
    assert reader.verified_ticker({"ticker": "RMBS", "subject": "Rambus"}, "The fund was short Rambus (RMBS).") == "RMBS"
    assert reader.verified_ticker({"ticker": "LNG", "subject": "Cheniere Energy", "points": [{"text": "Cheniere is building a terminal."}]}, "Cheniere (LNG) needs capital.") == "LNG"
    assert reader.verified_ticker({"ticker": "LNG", "subject": "Gas exports"}, "LNG exports will double.") is None


def test_themes_need_the_company_or_its_own_description():
    assert fe.idea_themes("long", "Domino's Pizza\nThe manager holds Domino's as a high-quality business.", []) == ["quality"]
    assert fe.idea_themes("update", "Fund performance\nThe fund bought high-quality companies at cheap prices.", []) == []
    assert fe.idea_themes("macro", "Kirby\nA roll-up of the inland market.", ["KEX"]) == []
    assert fe.idea_themes("long", "Kirby\nSimilar to its previous roll-up of the inland market.", ["KEX"]) == ["ma"]
    assert set(fe.idea_themes("update", "Constellation Software\nResults.", ["CSU"])) == {"quality", "ma"}


def test_release_carries_resolved_rows_and_moves_the_pointers_last(tmp_path, monkeypatch):
    archive = fl.connect(tmp_path / "archive.sqlite")
    source = "Cheniere Energy (LNG) needs capital. Free cash flow (FCF) fell. Weight Watchers (WTW) rose."
    archive.execute("INSERT INTO fl_funds(id,name) VALUES('f','Fund')")
    archive.execute("INSERT INTO fl_letters(id,fund_id,content_hash,pipeline_version,reporting_period,ingested_at,source_text,published_revision,status) VALUES('l','f','h','v','2012Q1','2026-11-01',?,'r','published')", (source,))
    archive.execute("INSERT INTO fl_revisions(id,letter_id,created_at,author,status,overview,content_json,checks_json) VALUES('r','l','2026-11-01','a','published','o','{}','{}')")
    for ordinal, (idea_id, ticker, title, kind) in enumerate([("lng", "LNG", "Cheniere Energy", "short"), ("fcf", "FCF", "Cash flow", "macro"), ("wtw", "WTW", "Weight Watchers", "long")]):
        archive.execute("INSERT INTO fl_ideas(id,revision_id,letter_id,title,ticker,idea_type,activity,summary,ordinal) VALUES(?,?,?,?,?,?,?,?,?)", (idea_id, "r", "l", title, ticker, kind, None, title, ordinal))
    archive.commit()
    monkeypatch.setattr(fl, "ROOT", tmp_path)
    output = tmp_path / "_private/releases/one"
    manifest = fl.export_release(archive, output)
    assert manifest["counts"]["fl_idea_entities"] == 2
    lines = (output / "archive.sql").read_text(encoding="utf-8").splitlines()
    assert lines[-1].startswith("UPDATE fl_settings SET value=") and "idea_themes" in lines[-1]
    assert not any(line.startswith("INSERT OR IGNORE INTO fl_idea_entities") and "'FCF'" in line for line in lines)

    replay = sqlite3.connect(":memory:")
    replay.executescript(fl.SCHEMA.read_text(encoding="utf-8") + fl.ENTITY_SCHEMA.read_text(encoding="utf-8"))
    replay.executescript("\n".join(lines))
    assert replay.execute("SELECT idea_id,ticker FROM fl_idea_tickers").fetchall() == [("lng", "LNG")]
    assert replay.execute("SELECT idea_id,status FROM fl_idea_entities WHERE status='unresolved'").fetchall() == [("wtw", "unresolved")]
    # A second release repeats the same rows, which the sync ledger then skips.
    again = fl.export_release(archive, tmp_path / "_private/releases/two")
    assert again["counts"]["fl_idea_entities"] == 2
    assert archive.execute("SELECT count(*) FROM fl_idea_entities").fetchone()[0] == 3
