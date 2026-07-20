#!/usr/bin/env python3
"""Lint deep dives for decision-stack report structure and prose rules.

Usage:
  python _system/scripts/lint_deep_dive.py              # all tickers, latest dive each
  python _system/scripts/lint_deep_dive.py ICE        # latest ICE dive
  python _system/scripts/lint_deep_dive.py --all ICE    # all ICE dives
  python _system/scripts/lint_deep_dive.py ICE --legacy # skip 2026 prose sections
  python _system/scripts/lint_deep_dive.py ICE --strict # prose warnings fail too
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_SECTIONS = [
    (r"## What this business is", "What this business is"),
    (r"## Why the market might be wrong", "Why the market might be wrong"),
    (r"## Executive summary", "Executive summary"),
    (r"## (Business & moat|Business overview)", "Business & moat (or legacy Business overview)"),
    (r"## (Payoff & return|Lawrence IRR)", "Payoff & return (or legacy Lawrence IRR)"),
    (r"## (Risks & inversion|Risks)", "Risks & inversion"),
    (r"## Valuation & IRR \(assumption ledger\)", "Valuation & IRR (assumption ledger)"),
    (r"## Classification", "Classification"),
    (r"## \[HUMAN REVIEW\]", "[HUMAN REVIEW]"),
]

ASSUMPTION_LEDGER = re.compile(r"### Assumption ledger \(base case\)", re.IGNORECASE)
VALUATION_SECTION = re.compile(r"## Valuation & IRR \(assumption ledger\)", re.IGNORECASE)

FORBIDDEN = [
    (r"\*\*Thesis status:\*\*", "Legacy thesis status — use Classification table"),
    (r"## Thesis status", "Legacy Thesis status section"),
]

EXEC_SUMMARY_LABEL_OPEN = re.compile(
    r"^\s*\*\*(Archetype|Stahl|Munger|Pabrai|Lawrence|Dhando|Moat)\b",
    re.IGNORECASE | re.MULTILINE,
)

TIER2_HEADER = re.compile(r"### Tier 2 prompts", re.IGNORECASE)
MENTAL_MODELS = re.compile(r"### Mental models\b", re.IGNORECASE)
MENTAL_MODELS_LEGACY = re.compile(r"### Mental models in plain English", re.IGNORECASE)
RETURN_MATH = re.compile(r"#### Return math in plain English", re.IGNORECASE)
IRR_ARITHMETIC = re.compile(r"#### IRR arithmetic \(show your work\)", re.IGNORECASE)
AI_INFRA = re.compile(r"#### AI infrastructure\b", re.I)
THEMATIC_CONTEXT = re.compile(r"#### Thematic context\b", re.I)
SYNTHESIS_SECTION = re.compile(r"### Total synthesis IRR \(all sources\)", re.IGNORECASE)
RETURNS_STATEMENT = re.compile(
    r"\*\*Returns statement:\*\*[^\n]*?\*\*(-?\d+(?:\.\d+)?)\s*%\*\*",
    re.IGNORECASE,
)
SYNTHESIS_RETURNS = re.compile(
    r"\*\*Returns statement \(synthesis\):\*\*[^\n]*?\*\*(-?\d+(?:\.\d+)?)\s*%\*\*",
    re.IGNORECASE,
)
EXEC_SUMMARY_IRR = re.compile(
    r"## Executive summary\s*\n+"
    r"(?:.*?\n)*?"
    r".*?(?:expect|annual|return|IRR|per year)[^\n]{0,120}?\*\*(-?\d+(?:\.\d+)?)\s*%\*\*",
    re.IGNORECASE | re.DOTALL,
)
UPSIDE_DOWN = re.compile(r"\*\*Upside / downside from price:\*\*", re.IGNORECASE)
PRIMARY_RISK = re.compile(r"\*\*Primary risk:\*\*", re.IGNORECASE)
HOLDING_CO = re.compile(r"\*\*Archetype\*\*.*holding_co", re.IGNORECASE)
LOOKTHROUGH_OR_SOTP = re.compile(
    r"#### (Look-through snapshot|Sum-of-parts or NAV)", re.IGNORECASE
)
CATALYST_PATH = re.compile(r"#### Catalyst path", re.IGNORECASE)
LENS_FAILURE = re.compile(r"\*\*Lens failure mode:\*\*", re.IGNORECASE)
PAYOFF_LENS = re.compile(r"\*\*Payoff lens\*\*", re.IGNORECASE)

EM_DASH = "\u2014"  # —
EXEC_SUMMARY_MAX_WORDS = 220
EM_DASH_MAX = 1

AI_HYPERSCALERS = frozenset({"GOOGL", "AMZN", "META", "MSFT"})
SEGMENT_MAP = re.compile(r"#### Segment map\b", re.IGNORECASE)
SEGMENT_BUILD = re.compile(r"### Segment cash-flow build\b", re.IGNORECASE)
BOOK_ESTIMATE_SECTION = re.compile(
    r"### Current book value estimate \(mark-to-market\)", re.IGNORECASE
)
MIAX_FILING_MISALIGN = re.compile(
    r"13,917,000.*51\.42|51\.42.*13,917|270,563.*51\.42|fair value.*51\.42.*2026-05",
    re.IGNORECASE,
)
BARE_UPLIFT_PCT = re.compile(
    r"(?:\d+\s*%\s*higher\s+than\s+GAAP|"
    r"Economic value\s+\d+\s*%\s*higher|Incremental on book:\s*\d+\.\d+\s*[x×]\s*\d+\s*%)",
    re.IGNORECASE,
)
INVESTMENT_A_3G = re.compile(r"\*\*3g-5\.\s*Investment A", re.IGNORECASE)
BOTTOM_UP_UPLIFT = re.compile(
    r"bottom-up|Bottom-up|derived blended|holdco_uplift|Why the model uses",
    re.IGNORECASE,
)


def ticker_from_dive_path(path: Path) -> str | None:
    parts = path.parts
    for i, p in enumerate(parts):
        if p == "research" and i > 0:
            return parts[i - 1]
    return None


def load_valuation(ticker: str) -> dict:
    val_path = ROOT / ticker / "research" / "valuation.json"
    if not val_path.exists():
        return {}
    return json.loads(val_path.read_text(encoding="utf-8"))


def registry_flags(ticker: str) -> dict:
    reg = ROOT / "_system" / "portfolio" / "registry.json"
    if not reg.exists():
        return {}
    data = json.loads(reg.read_text(encoding="utf-8"))
    holding = (data.get("holdings") or {}).get(ticker) or {}
    return holding.get("valuation_flags") or {}


def latest_dive(ticker_dir: Path) -> Path | None:
    dives = sorted(ticker_dir.glob("deep_dive_*.md"))
    return dives[-1] if dives else None


def body_before_classification(text: str) -> str:
    idx = text.find("## Classification")
    return text[:idx] if idx >= 0 else text


def extract_executive_summary(text: str) -> str | None:
    m = re.search(
        r"## Executive summary\s*\n+(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def extract_section(text: str, heading: str) -> str | None:
    m = re.search(
        rf"## {re.escape(heading)}\s*\n+(.*?)(?=\n## |\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def word_count(s: str) -> int:
    return len(re.findall(r"\b[\w']+\b", s))


_SHADOW_NEEDLES = re.compile(
    r"\b(zero[- ]mark|marked at zero|at zero|to zero|shadow(?:-|\s+)(?:nav|net asset)|"
    r"level[- ]?3|sanction|frozen|write[- ]?off|carried at zero|valued at zero|"
    r"zeros? (?:russia|the|a) )\b",
    re.IGNORECASE,
)
_THIN_REPORTED_LEAD = re.compile(
    r"(trade[sd]?|trading)\s+at\s+[+\-]?\d+(?:\.\d+)?%\s+(vs|to|below|above)\s+reported",
    re.IGNORECASE,
)


def lint_shadow_fund_nav(rel: Path, text: str, val: dict) -> list[str]:
    """Catch CEE-class failure: classic CEF discount story burying a zero-marked sleeve."""
    errors: list[str] = []
    overlay = val.get("fund_nav_overlay") if isinstance(val, dict) else None
    if not isinstance(overlay, dict):
        return errors
    sleeves = overlay.get("zero_marked_sleeves") or []
    edge = str(overlay.get("edge") or "").lower()
    if edge != "shadow" and not sleeves:
        return errors

    why = extract_section(text, "Why the market might be wrong") or ""
    exec_sum = extract_executive_summary(text) or ""
    valuation = extract_section(text, "Valuation & IRR (assumption ledger)") or ""

    if not _SHADOW_NEEDLES.search(why):
        errors.append(
            f"{rel}: fund shadow/zero-marked sleeve — "
            "'Why the market might be wrong' must name the zero mark / sanctions / Level-3 understatement "
            "(optionality_valuation.md § D); do not lead with a thin reported-NAV discount alone"
        )
    elif _THIN_REPORTED_LEAD.search(why.split("\n")[0] if why else "") and not _SHADOW_NEEDLES.search(
        why.split("\n")[0]
    ):
        errors.append(
            f"{rel}: fund shadow edge — first sentence of Q5 leads with reported-NAV discount; "
            "lead with the accounting mark (optionality_valuation.md § D)"
        )

    if not _SHADOW_NEEDLES.search(exec_sum):
        errors.append(
            f"{rel}: fund shadow/zero-marked sleeve — Executive summary must name the zero-marked sleeve "
            "and that reported NAV excludes it"
        )

    if not re.search(r"reported\s+net asset value|reported NAV|three (views|NAVs)", valuation, re.I):
        errors.append(
            f"{rel}: fund shadow edge — Valuation must present reported vs economic/illustration NAV "
            "(three-NAV table or equivalent)"
        )

    if sleeves and not re.search(r"Option scan|zero[- ]mark|Russia|Level", text, re.I):
        errors.append(
            f"{rel}: zero_marked_sleeves in valuation.json but dive lacks Option scan / zero-mark discussion"
        )

    if re.search(r"almost at (NAV|net asset value)|no (real |meaningful )?edge", text, re.I) and edge == "shadow":
        errors.append(
            f"{rel}: forbidden 'almost at NAV' / 'no edge' framing while fund_nav_overlay.edge is shadow"
        )

    return errors


_CRYPTO_NAV_NEEDLES = re.compile(
    r"\b(look[- ]through|crypto\s+NAV|mNAV|book\s+(?:value\s+)?(?:discount|per share)|"
    r"discount\s+to\s+(?:book|NAV|net asset|crypto)|below\s+(?:book|NAV)|"
    r"digital[- ]asset|bitcoin\s+(?:treasury|holdings)|marked\s+bitcoin)\b",
    re.IGNORECASE,
)
_NO_OPTIONS_CLAIM = re.compile(
    r"no material (?:options?|optionality)|option scan:\s*none|no (?:significant )?options?",
    re.IGNORECASE,
)


def _crypto_holdings_map() -> dict:
    path = ROOT / "_system" / "portfolio" / "holdings_crypto.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    holdings = data.get("holdings") if isinstance(data, dict) else None
    return holdings if isinstance(holdings, dict) else {}


def _material_crypto_book_discount(val: dict) -> bool:
    """True when valuation shows price meaningfully below book / crypto look-through."""
    be = val.get("book_estimate") if isinstance(val, dict) else None
    if isinstance(be, dict):
        for key in ("discount_to_book_pct", "price_to_book", "discount_pct"):
            raw = be.get(key)
            if raw is None:
                continue
            try:
                x = float(raw)
            except (TypeError, ValueError):
                continue
            if key == "price_to_book":
                if x > 0 and x < 0.85:
                    return True
            elif x >= 15:  # percent discount
                return True
        # Nested current vs price fields used by current_book_estimate.py
        price = be.get("price") or (val.get("inputs") or {}).get("price")
        book = be.get("current_book_per_share") or be.get("book_per_share")
        try:
            if price is not None and book is not None:
                p, b = float(price), float(book)
                if b > 0 and (b - p) / b >= 0.15:
                    return True
        except (TypeError, ValueError):
            pass
    # Explicit agent flag
    flags = val.get("classification_inputs") if isinstance(val, dict) else None
    if isinstance(flags, dict) and flags.get("crypto_nav_discount"):
        return True
    overlay = val.get("btc_overlay") if isinstance(val, dict) else None
    if isinstance(overlay, dict) and overlay.get("lookthrough_discount_pct") is not None:
        try:
            return float(overlay["lookthrough_discount_pct"]) >= 15
        except (TypeError, ValueError):
            pass
    return False


def lint_crypto_nav_discount(rel: Path, text: str, val: dict, ticker: str) -> list[str]:
    """Catch CMSG-class failure: cash IRR story burying look-through crypto/book NAV discount."""
    errors: list[str] = []
    holdings = _crypto_holdings_map()
    if ticker not in holdings:
        return errors
    if not _material_crypto_book_discount(val):
        # Soft: still require Bitcoin economics section when overlay present
        return errors

    why = extract_section(text, "Why the market might be wrong") or ""
    exec_sum = extract_executive_summary(text) or ""

    if not _CRYPTO_NAV_NEEDLES.search(why):
        errors.append(
            f"{rel}: crypto look-through NAV discount — "
            "'Why the market might be wrong' must lead with discount to book / crypto NAV "
            "(crypto_economics_valuation.md); do not lead only with owner-cash IRR"
        )
    if not _CRYPTO_NAV_NEEDLES.search(exec_sum):
        errors.append(
            f"{rel}: crypto look-through NAV discount — Executive summary must name "
            "the discount to book or crypto NAV"
        )
    if _NO_OPTIONS_CLAIM.search(text):
        errors.append(
            f"{rel}: forbidden 'no material options' while holdings_crypto + book/crypto "
            "NAV discount apply (option_treatment.md row 1c)"
        )
    return errors


def lint_file(path: Path, *, legacy: bool, strict: bool) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    errors: list[str] = []
    warnings: list[str] = []
    rel = path.relative_to(ROOT)

    for pattern, name in REQUIRED_SECTIONS:
        if legacy and name in (
            "What this business is",
            "Why the market might be wrong",
        ):
            continue
        if not re.search(pattern, text, re.IGNORECASE):
            errors.append(f"{rel}: missing section — {name}")

    for pattern, msg in FORBIDDEN:
        if re.search(pattern, text):
            errors.append(f"{rel}: {msg}")

    if "## Classification" in text and "Implied 7yr IRR" not in text and "Implied 10yr IRR" not in text:
        errors.append(f"{rel}: Classification table missing Implied 7yr IRR (decision stack)")

    if legacy:
        return errors, warnings

    body = body_before_classification(text)

    if TIER2_HEADER.search(text) and (MENTAL_MODELS.search(text) or MENTAL_MODELS_LEGACY.search(text)):
        warnings.append(
            f"{rel}: has both Tier 2 prompts and Mental models — consolidate per deep_dive_structure.md"
        )
    if not (MENTAL_MODELS.search(text) or MENTAL_MODELS_LEGACY.search(text)):
        errors.append(f"{rel}: missing ### Mental models (deep_dive_structure.md)")

    if not VALUATION_SECTION.search(text):
        errors.append(
            f"{rel}: missing ## Valuation & IRR (assumption ledger) — must be at end (irr_assumption_ledger.md)"
        )
    if not ASSUMPTION_LEDGER.search(text):
        errors.append(
            f"{rel}: missing ### Assumption ledger (base case) (irr_assumption_ledger.md)"
        )
    if not IRR_ARITHMETIC.search(text):
        errors.append(
            f"{rel}: missing #### IRR arithmetic (show your work) (lawrence_irr.md § F)"
        )
    elif RETURN_MATH.search(text):
        warnings.append(
            f"{rel}: legacy #### Return math in plain English — rename to #### IRR arithmetic (show your work)"
        )
    elif IRR_ARITHMETIC.search(text) and VALUATION_SECTION.search(text):
        irr_pos = IRR_ARITHMETIC.search(text).start()
        val_pos = VALUATION_SECTION.search(text).start()
        if irr_pos < val_pos:
            errors.append(
                f"{rel}: IRR arithmetic must be inside ## Valuation & IRR section at end of report"
            )
        biz_end = text.find("## Valuation & IRR")
        if biz_end > 0 and IRR_ARITHMETIC.search(text[:biz_end]):
            warnings.append(
                f"{rel}: IRR arithmetic still in overview — run refresh_deep_dive_v2.py"
            )
    if not UPSIDE_DOWN.search(text):
        errors.append(f"{rel}: missing **Upside / downside from price:** (Hohn essentials)")
    if not PRIMARY_RISK.search(text):
        errors.append(f"{rel}: missing **Primary risk:** in Risks section (Hohn essentials)")

    if not legacy:
        if not PAYOFF_LENS.search(text):
            warnings.append(f"{rel}: Classification missing Payoff lens (analysis_arsenal.md)")

    if HOLDING_CO.search(text):
        if not LOOKTHROUGH_OR_SOTP.search(text):
            errors.append(
                f"{rel}: holding_co — missing #### Look-through snapshot or #### Sum-of-parts or NAV"
            )
        if not CATALYST_PATH.search(text):
            (errors if strict else warnings).append(
                f"{rel}: holding_co — missing #### Catalyst path (dated events)"
            )

    ticker = ticker_from_dive_path(path)
    if ticker and (ROOT / ticker / "research" / "book_estimate_config.json").exists():
        if not BOOK_ESTIMATE_SECTION.search(text):
            errors.append(
                f"{rel}: missing ### Current book value estimate (mark-to-market) — "
                "required when book_estimate_config.json exists (current_book_estimate.md)"
            )
    if MIAX_FILING_MISALIGN.search(text):
        errors.append(
            f"{rel}: MIAX fair value tied to post-quarter price (~$51.42 / May 2026) — "
            "use measurement-date price ~$42.60 on 2026-02-27 (mark_date_alignment.md)"
        )

    if BARE_UPLIFT_PCT.search(text):
        has_bottom_up = BOTTOM_UP_UPLIFT.search(text)
        val = load_valuation(ticker) if ticker else {}
        sotp = ((val.get("scenarios") or {}).get("base") or {}).get("sotp_build") or {}
        ledger = sotp.get("assumption_ledger") or {}
        ia = ledger.get("investment_a_lookthrough") or {}
        has_components = bool(ia.get("components"))
        if not has_bottom_up and not has_components:
            errors.append(
                f"{rel}: bare % uplift on opaque sleeve (e.g. 64% higher than GAAP) — "
                "require bottom-up 3g sub-table per holdco_uplift_explanation.md"
            )
        elif has_components and INVESTMENT_A_3G.search(text) and not has_bottom_up:
            errors.append(
                f"{rel}: Investment A 3g-5 missing bottom-up sub-table — "
                "valuation.json has components[]; render per holdco_uplift_explanation.md"
            )

    em_count = body.count(EM_DASH)
    if em_count > EM_DASH_MAX:
        msg = f"{rel}: {em_count} em dashes in body (max {EM_DASH_MAX}); use periods or parentheses"
        (errors if strict else warnings).append(msg)

    exec_sum = extract_executive_summary(text)
    if exec_sum:
        if EXEC_SUMMARY_LABEL_OPEN.search(exec_sum):
            msg = f"{rel}: executive summary opens with framework label — lead with the business"
            (errors if strict else warnings).append(msg)
        wc = word_count(exec_sum)
        if wc > EXEC_SUMMARY_MAX_WORDS:
            msg = f"{rel}: executive summary is {wc} words (target ≤{EXEC_SUMMARY_MAX_WORDS})"
            (errors if strict else warnings).append(msg)

    ticker = ticker_from_dive_path(path)
    if ticker and not legacy:
        val = load_valuation(ticker)
        errors.extend(lint_shadow_fund_nav(rel, text, val))
        errors.extend(lint_crypto_nav_discount(rel, text, val, ticker))
        overlay = val.get("valuation_overlay")
        if overlay == "segment_cashflow":
            if not SEGMENT_MAP.search(text):
                errors.append(
                    f"{rel}: valuation_overlay segment_cashflow — missing #### Segment map"
                )
            if not SEGMENT_BUILD.search(text):
                errors.append(
                    f"{rel}: valuation_overlay segment_cashflow — missing ### Segment cash-flow build"
                )
        flags = registry_flags(ticker) if ticker else {}
        need_ai = (
            val.get("ai_overlay") is not None
            or flags.get("ai_hyperscaler")
            or ticker in AI_HYPERSCALERS
        )
        if need_ai and not AI_INFRA.search(text):
            msg = (
                f"{rel}: AI hyperscaler or ai_overlay — missing "
                "#### AI infrastructure — model coverage (ai_infrastructure_valuation.md)"
            )
            (errors if strict else warnings).append(msg)

        if val.get("context_overlay", {}).get("themes") and not THEMATIC_CONTEXT.search(text):
            warnings.append(
                f"{rel}: context_overlay present — missing #### Thematic context (run refresh_deep_dive_v2.py)"
            )

        ps = str((val.get("inputs") or {}).get("price_source") or "")
        if re.search(r"placeholder|confirm via fetch_market", ps, re.I):
            errors.append(f"{rel}: placeholder equity price in valuation.json — run fetch_equity_prices.py")

        if val.get("btc_overlay", {}).get("themes") and not re.search(
            r"#### (?:Bitcoin|Stablecoin) economics — model coverage", text, re.I
        ):
            warnings.append(
                f"{rel}: btc_overlay present — missing crypto economics section (run refresh_deep_dive_v2.py)"
            )

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from optionality_evidence_common import has_evidence_refresh_config, synthesis_in_dive

        base_pct = (val.get("implied_return") or {}).get("base_pct")
        if base_pct is not None:
            tol = 0.25
            rs = RETURNS_STATEMENT.search(text)
            if rs and abs(float(rs.group(1)) - float(base_pct)) > tol:
                errors.append(
                    f"{rel}: Returns statement {rs.group(1)}% vs valuation.json base {base_pct}% (tol {tol}pp)"
                )
            exec_body = extract_executive_summary(text) or ""
            es = EXEC_SUMMARY_IRR.search(exec_body) if exec_body else None
            if not es:
                m = re.search(
                    r"(?:Lawrence|base is|expect)[^\n]{0,80}?(-?\d+(?:\.\d+)?)\s*%\s*(?:\(|per year)",
                    exec_body,
                    re.I,
                )
                if m:
                    es_pct = float(m.group(1))
                    if abs(es_pct - float(base_pct)) > tol:
                        errors.append(
                            f"{rel}: Executive summary ~{es_pct}% vs valuation.json base {base_pct}% (tol {tol}pp)"
                        )
            elif abs(float(es.group(1)) - float(base_pct)) > tol:
                errors.append(
                    f"{rel}: Executive summary {es.group(1)}% vs valuation.json base {base_pct}% (tol {tol}pp)"
                )

        syn = val.get("synthesis") or {}
        if val.get("method") == "yield_curve" and has_evidence_refresh_config(val):
            if SYNTHESIS_RETURNS.search(text) and not synthesis_in_dive(val):
                errors.append(
                    f"{rel}: synthesis returns statement present but evidence_refresh.synthesis_in_dive is false"
                )
            if SYNTHESIS_SECTION.search(text) and not synthesis_in_dive(val):
                errors.append(
                    f"{rel}: Total synthesis IRR section must not appear when synthesis_in_dive is false (yield_curve)"
                )
        elif syn.get("status") == "complete" and synthesis_in_dive(val):
            if not SYNTHESIS_SECTION.search(text):
                errors.append(
                    f"{rel}: valuation.json synthesis complete — missing "
                    "### Total synthesis IRR (all sources) (total_synthesis_irr.md)"
                )
            elif IRR_ARITHMETIC.search(text) and SYNTHESIS_SECTION.search(text):
                irr_pos = IRR_ARITHMETIC.search(text).start()
                syn_pos = SYNTHESIS_SECTION.search(text).start()
                if syn_pos < irr_pos:
                    errors.append(
                        f"{rel}: Total synthesis IRR must follow #### IRR arithmetic (total_synthesis_irr.md)"
                    )

    return errors, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint deep dive structure and prose")
    parser.add_argument("ticker", nargs="?", help="Ticker to lint")
    parser.add_argument("--all", action="store_true", help="Lint all dives for ticker")
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Skip What/Why sections and prose checks (pre-refresh dives)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat prose warnings as errors",
    )
    parser.add_argument(
        "--milly",
        action="store_true",
        help="Also run lint_adversarial.py on same ticker(s)",
    )
    args = parser.parse_args()

    paths: list[Path] = []
    if args.ticker:
        research = ROOT / args.ticker / "research"
        if args.all:
            paths = sorted(research.glob("deep_dive_*.md"))
        else:
            d = latest_dive(research)
            if d:
                paths = [d]
    else:
        for td in sorted(ROOT.iterdir()):
            if td.is_dir() and (td / "research").is_dir():
                d = latest_dive(td / "research")
                if d:
                    paths.append(d)

    if not paths:
        print("No deep dives found.")
        sys.exit(0)

    all_errors: list[str] = []
    all_warnings: list[str] = []
    for p in paths:
        errs, warns = lint_file(p, legacy=args.legacy, strict=args.strict)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    for w in all_warnings:
        print(f"WARN: {w}")
    if all_errors:
        for e in all_errors:
            print(f"LINT: {e}")
        sys.exit(1)

    if args.milly:
        import subprocess

        py = sys.executable
        adv_script = Path(__file__).resolve().parent / "lint_adversarial.py"
        cmd = [py, str(adv_script)]
        if args.ticker:
            cmd.append(args.ticker)
        if args.strict:
            cmd.append("--strict")
        print("--- Milly / adversarial lint ---")
        r = subprocess.run(cmd, cwd=ROOT)
        if r.returncode != 0:
            sys.exit(r.returncode)

    suffix = ""
    if args.legacy:
        suffix = " (legacy mode)"
    elif all_warnings:
        suffix = f" ({len(all_warnings)} warning(s))"
    print(f"OK: {len(paths)} deep dive(s){suffix}")


if __name__ == "__main__":
    main()
