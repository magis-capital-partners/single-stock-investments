"""Source-grounded analyst review, separate from quantitative selection."""

from copy import deepcopy


def _book(key, title, author, drive_id, status="reference_only", locator=""):
    return {"id": key, "title": title, "author": author,
            "url": f"https://drive.google.com/file/d/{drive_id}/view",
            "review_status": status, "review_locator": locator}


BOOKS = [
    _book("einhorn", "Fooling Some of the People All of the Time", "David Einhorn", "1CgHeyVeI5taKT5zMXqKsEmW-kkvBVVCl", "selected_sections_reviewed", "Getting the Green Light, pp. 16-17; Value Investing through the Internet Bubble, pp. 34-35; Rewarding Shareholders, p. 129"),
    _book("asensio", "Sold Short", "Manuel Asensio and Jack Barth", "1z-DzSjXJbs1dlGaSwE75zzkVciYyNTB7"),
    _book("richard", "Confidence Game", "Christine Richard", "1GuPl-h4TPDDLH4FFHMhH7AiNOTdDr6Yo"),
    _book("lewis", "The Big Short", "Michael Lewis", "1512KDS5eLbpoSg8erqIsaZ3-Eb8KMSJG"),
    _book("zuckerman", "The Greatest Trade Ever", "Gregory Zuckerman", "19KSh9Eb8ahGrVttRuC98a9gVxma3j20h"),
    _book("schultz", "Bear Market Investing Strategies", "Harry Schultz", "1bzhptd_cJqyYgSAVPEnuFkfH-DXpS0TF"),
    _book("schilit_perler", "Financial Shenanigans, third edition (2010)", "Howard Schilit and Jeremy Perler", "1lrgSrA9X3a9hEP2cPSyuYva0diAhf5Au", "selected_sections_reviewed", "Ch. 3, pp. 73-74; ch. 2, pp. 25-26; cash-flow and key-metric taxonomy, parts 3-4"),
    _book("schilit_older", "Financial Shenanigans, older edition", "Howard Schilit", "1gcw8VdD_G9J1Pw1IIC86rLDJip7p0fLt"),
    _book("oglove", "Quality of Earnings", "Thornton O'glove", "1hId6LnkK6bsCIalOjc9JnNbAaZRwva5Z", "readable_text_unavailable"),
    _book("numbers", "The Financial Numbers Game", "Mulford and Comiskey", "1pIN9aahqp3_Ri23hhWtcBJFo1XKlmWvd"),
    _book("creative_cash", "Creative Cash Flow Reporting", "Mulford and Comiskey", "1teaw2sXGodJrw6PBGqkLuLJSs9kx6VR-"),
    _book("jones", "Creative Accounting, Fraud and International Accounting Scandals", "Michael Jones", "1O465KG8FKjg4yxBOg5CNsyXd1QoFa1DV"),
    _book("singleton", "Fraud Auditing and Forensic Accounting", "Tommie and Aaron Singleton", "17WOS9H7RtanuTph4zSFpe3x_Yu6pXFvH"),
    _book("spann", "Fraud Analytics", "Delena Spann", "16HPgaszjIDqTNIVCoss-v4kyy3zlqxTm"),
    _book("leder", "Financial Fine Print", "Michelle Leder", "1NoTskXE0qlLxe18YfmfPUwilKFMwIJMM", "selected_sections_reviewed", "Ch. 2, pp. 25, 29-30: comparable filings, related parties and policy changes"),
    _book("smith", "Accounting for Growth", "Terry Smith", "1CO4K_-PVpixQVx0-pjI6j_hnHrvuEarx"),
    _book("enron", "The Smartest Guys in the Room", "Bethany McLean and Peter Elkind", "1qpcGH5u8OXj6eYa0_n9kjZFeLGxqQiW3"),
    _book("eichenwald", "Conspiracy of Fools", "Kurt Eichenwald", "1YFen8bxvTEkhUYmCAwGA3df_vwKJkDOd"),
    _book("fcf", "Free Cash Flow: Seeing Through the Accounting Fog Machine", None, "1neuoLfBcOQ4bA1sYsDI1zssgxhpqY2rm"),
    _book("lev_gu", "The End of Accounting", "Baruch Lev and Feng Gu", "1BAsDihIPfFcMZ61TROahzEQamEmAtS6Y"),
]


LENSES = [
    {"id": "earnings_quality", "label": "Earnings and revenue quality",
     "frameworks": ["accounting", "revenue_recognition", "earnings_vs_cash", "working_capital"],
     "question": "Are booked earnings supported by collectible revenue and cash, or by changing recognition assumptions?",
     "checks": "Compare receivables and contract assets with sales; reconcile collections, payment terms, revenue policies, allowances and customer concentration across comparable filings.",
     "weakening_evidence": "Collections catch up, balances normalize, or a documented seasonal or contract explanation resolves the discrepancy.",
     "sources": ["schilit_perler", "leder"]},
    {"id": "cash_and_financing", "label": "Cash quality and financing pressure",
     "frameworks": ["cash_burn", "leverage_refinancing", "dilution_financing", "off_balance_sheet", "capitalization_reserves"],
     "question": "How much usable cash remains after correcting cash-flow presentation and meeting unavoidable obligations?",
     "checks": "Bridge operating cash to economic cash generation; review capitalized operating costs, receivable sales, supplier financing, acquisitions, restricted cash, maturities, covenants and actual funding terms.",
     "weakening_evidence": "Sustainable cash generation or committed financing extends runway without the expected damage to common equity.",
     "sources": ["schilit_perler"], "ssi_partition": "Financial oxygen"},
    {"id": "operating_impairment", "label": "Operating impairment",
     "frameworks": ["cycle_mean_reversion", "supply_side", "margin_contraction", "secular_obsolescence", "fad_single_product"],
     "question": "What operating mechanism will make future equity economics worse than the market expects?",
     "checks": "Separate temporary cycle weakness from durable deterioration; test price, volume, margins, customer losses, competitive supply and cash economics. A reverse split alone supplies no answer.",
     "weakening_evidence": "Durable demand, pricing or unit economics improves enough to contradict the stated failure mechanism.",
     "sources": ["einhorn"], "ssi_partition": "Operating failure mode"},
    {"id": "disclosures_and_control", "label": "Disclosures, incentives and control",
     "frameworks": ["reporting_integrity", "governance_related_party", "promotion_insider_selling", "acquisition_nongaap_kpi"],
     "question": "What changed in the disclosures, and whose economic interests do the transactions serve?",
     "checks": "Diff accounting policies, related-party notes, commitments, adjusted metrics and auditor disclosures; reconcile management claims to filed facts and preserve management's explanation.",
     "weakening_evidence": "Primary documents resolve the discrepancy, show ordinary arm's-length terms, or demonstrate that the apparent change is a required disclosure update.",
     "sources": ["leder", "schilit_perler"], "ssi_partition": "Governance/legal"},
    {"id": "valuation_and_payoff", "label": "Valuation and common-equity payoff",
     "frameworks": ["leverage_refinancing", "dilution_financing"],
     "question": "Is there enough downside at the entry price after all claims, dilution and the cost of waiting?",
     "checks": "Build bear/base/bull common-equity values with debt, preferreds, warrants and converts; state the mispriced market belief, financing assumptions and upside loss. Expensive valuation alone is insufficient.",
     "weakening_evidence": "The impairment is already priced in, recovery or financing improves per-share value, or carry consumes the plausible downside.",
     "sources": ["einhorn"], "ssi_partition": "Identity and instrument"},
    {"id": "catalyst_and_path", "label": "Catalyst, falsifier and survivable path",
     "frameworks": ["regulatory", "borrow_and_carry", "crowding_squeeze", "path_and_timing", "issuer_retaliation"],
     "question": "What dated event can expose the impairment, and can the account survive until it happens?",
     "checks": "Record a dated catalyst and measurable falsifier before entry; document locate approval, fees, recalls, crowding and adverse-gap dollar losses against shared-account margin. Cover or re-review when the original mechanism fails.",
     "weakening_evidence": "The catalyst is delayed beyond affordable carry, the falsifier occurs, borrow disappears, or joint squeeze losses exceed the declared risk budget.",
     "sources": ["einhorn"], "ssi_partition": "Market mechanics and timing"},
]


def playbook():
    return deepcopy({
        "schema_version": "short_research_playbook.v1", "version_date": "2026-10-09",
        "purpose": "Assess a reverse-split lead using fundamental mechanisms, primary evidence and the feasible equity payoff.",
        "books": BOOKS, "lenses": LENSES,
        "source_scope": "Selected sections of three supplied books were reviewed. Other links are reading references; Quality of Earnings yielded no readable text. No book files or full text are stored in this repository.",
        "score_rule": "The existing 0-100 deterioration score is a quantitative triage signal. Analyst judgments remain unscored until dated primary evidence, contradictory evidence and a falsifier are recorded; there is no calibrated composite conviction score.",
        "fraud_rule": "Accounting warnings, reverse splits and qualitative grades do not establish fraud. A conclusion requires the filing-furnace evidence and analyst-review contract.",
        "performance_validation": "The original RSI-1.0 proposal is evaluated with a new prospective decision ledger. Michael's records are not needed to develop it. Executed paper fills, costs, daily equity and capital flows are needed before reporting its risk-adjusted returns.",
        "assessment_states": ["unreviewed", "unresolved", "supported", "contradicted"],
        "evidence_fields": ["known_at", "primary_source", "locator", "claim", "prior_value", "new_value", "short_impact", "contradictory_evidence", "falsifier", "review_status"],
    })


def empty_lens_reviews():
    return [{"lens_id": lens["id"], "frameworks": list(lens["frameworks"]),
             "status": "unreviewed", "known_at": None, "mechanism": "",
             "supporting_evidence": [], "contradictory_evidence": [],
             "falsifier": "", "reviewed_at": None} for lens in LENSES]
