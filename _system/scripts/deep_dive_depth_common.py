"""Shared depth rubric scoring for lint and portfolio audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PASS_SCORE = 18
MAX_SCORE = 24

PRIMARY_SOURCES = re.compile(r"## Primary sources", re.I)
OPERATING_SNAPSHOT = re.compile(r"#### Operating snapshot", re.I)
THESIS_PILLARS = re.compile(r"#### Thesis pillars", re.I)
OPTION_SCAN = re.compile(r"#### Option scan", re.I)
ASSUMPTION_LEDGER = re.compile(r"### Assumption ledger \(base case\)", re.I)
IRR_ARITHMETIC = re.compile(r"#### IRR arithmetic \(show your work\)", re.I)
EXEC_SUMMARY = re.compile(r"## Executive summary", re.I)
RISKS = re.compile(r"## (Risks & inversion|Risks)\b", re.I)
MENTAL_MODELS = re.compile(r"### Mental models\b", re.I)
LOOKTHROUGH = re.compile(r"#### Look-through snapshot", re.I)
SOTP_NAV = re.compile(r"#### (Sum-of-parts or NAV|Sum-of-the-parts)", re.I)
CATALYST = re.compile(r"#### Catalyst path", re.I)
SEGMENT_MAP = re.compile(r"#### Segment map", re.I)
HK_BLOCK = re.compile(r"#### HK (commentary|cross-reference|scan)", re.I)
VALUATION_SECTION = re.compile(r"## Valuation & IRR", re.I)
VALUATION_END = re.compile(r"\n## (Classification|\[HUMAN REVIEW\])", re.I)

PATH_LIKE = re.compile(
    r"\.pdf|\.htm|10-[KQ]|INDEX\.csv|/research/|investor-documents|_text/",
    re.I,
)
DOLLAR = re.compile(r"\$[\d,]+|\d+\.\d+\s*[MmBb]")
NUMBERED_STEP = re.compile(r"^\s*\d+[\.)]\s+", re.M)


@dataclass
class CriterionScore:
    key: str
    label: str
    score: int
    detail: str


@dataclass
class DepthResult:
    path: Path
    ticker: str | None
    criteria: list[CriterionScore] = field(default_factory=list)
    archetype_errors: list[str] = field(default_factory=list)
    archetype_warnings: list[str] = field(default_factory=list)
    full_tier_count: int = 0

    @property
    def total(self) -> int:
        return sum(c.score for c in self.criteria)

    @property
    def grade(self) -> str:
        t = self.total
        if t >= 22:
            return "gold"
        if t >= PASS_SCORE:
            return "adequate"
        if t >= 12:
            return "thin"
        return "incomplete"

    def passed(self) -> bool:
        return self.total >= PASS_SCORE


def word_count(s: str) -> int:
    return len(re.findall(r"\b[\w']+\b", s))


def section_slice(text: str, header_pat: re.Pattern[str], until: str = r"\n## |\n#### ") -> str:
    m = header_pat.search(text)
    if not m:
        return ""
    start = m.end()
    rest = text[start:]
    end_m = re.search(until, rest)
    return rest[: end_m.start()] if end_m else rest


def count_table_rows(block: str) -> int:
    rows = 0
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|") or s.startswith("|---"):
            continue
        cells = [c.strip() for c in s.split("|")[1:-1]]
        if not cells or all(not c or c in ("—", "-", "N/A", "n/a") for c in cells):
            continue
        if cells[0].lower() in ("tier", "metric", "pillar", "model", "question", "#"):
            continue
        rows += 1
    return rows


def count_bullets(block: str) -> int:
    return sum(1 for line in block.splitlines() if re.match(r"^\s*[-*]\s+\S", line))


def load_classification(ticker: str) -> dict:
    p = ROOT / "_system" / "portfolio" / "classification.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return (data.get("tickers") or {}).get(ticker) or {}


def count_full_tier_evidence(ticker: str) -> int:
    inv = ROOT / ticker / "research" / "evidence" / "document_inventory.json"
    if inv.exists():
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
            docs = data.get("documents") or data.get("files") or []
            if isinstance(docs, list):
                return sum(
                    1
                    for d in docs
                    if isinstance(d, dict)
                    and str(d.get("tier", "")).lower() in ("full", "full_tier")
                )
        except json.JSONDecodeError:
            pass
    text_dir = ROOT / ticker / "research" / "evidence" / "_text"
    if text_dir.is_dir():
        return len(list(text_dir.glob("*.txt")))
    return 0


def latest_adversarial(research: Path) -> Path | None:
    files = sorted(research.glob("adversarial_*.md"))
    return files[-1] if files else None


def score_dive(path: Path, *, archetype_strict: bool = False) -> DepthResult:
    text = path.read_text(encoding="utf-8", errors="ignore")
    parts = path.parts
    ticker = None
    for i, p in enumerate(parts):
        if p == "research" and i > 0:
            ticker = parts[i - 1]
            break

    clf = load_classification(ticker) if ticker else {}
    archetype = (clf.get("archetype") or "").strip().lower()

    val: dict = {}
    if ticker:
        vp = ROOT / ticker / "research" / "valuation.json"
        if vp.exists():
            try:
                val = json.loads(vp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                val = {}

    criteria: list[CriterionScore] = []

    # 1 Primary sources
    ps = section_slice(text, PRIMARY_SOURCES)
    has_full = bool(re.search(r"\bfull\b", ps, re.I))
    has_partial = bool(re.search(r"\bpartial\b", ps, re.I))
    ps_rows = count_table_rows(ps)
    ps_paths = len(PATH_LIKE.findall(ps))
    if ps and has_full and has_partial and ps_rows >= 2 and ps_paths >= 2:
        s1, d1 = 2, f"tiered table ({ps_rows} rows, {ps_paths} paths)"
    elif ps and (has_full or has_partial) and ps_rows >= 1:
        s1, d1 = 1, "primary sources present but thin tiers/paths"
    else:
        s1, d1 = 0, "missing tiered primary sources table"
    criteria.append(CriterionScore("primary_sources", "Primary sources (tiered)", s1, d1))

    # 2 Operating snapshot
    op = section_slice(text, OPERATING_SNAPSHOT, until=r"\n#### ")
    op_rows = count_table_rows(op)
    op_paths = sum(1 for line in op.splitlines() if PATH_LIKE.search(line))
    if op_rows >= 8 or (op_rows >= 6 and op_paths >= 6):
        s2, d2 = 2, f"{op_rows} metrics"
    elif op_rows >= 4 or op_paths >= 4:
        s2, d2 = 1, f"{op_rows} metrics (target ≥8)"
    else:
        s2, d2 = 0, f"{op_rows} metrics"
    criteria.append(CriterionScore("operating_snapshot", "Operating snapshot", s2, d2))

    # 3 Run-rate vs one-off
    biz = section_slice(
        text,
        re.compile(r"## (Business & moat|Business overview)", re.I),
        until=r"\n## (Payoff|Risks|Valuation)",
    )
    run_pat = re.compile(
        r"run[- ]rate|one[- ]off|unrealized|special dividend|normalized|non-recurring|"
        r"recurring owner|owner cash",
        re.I,
    )
    run_heading = re.search(r"\*\*Run-rate vs one-off:\*\*", biz, re.I)
    if run_heading or run_pat.search(biz):
        s3, d3 = 2, "run-rate / one-off separation present"
    elif run_pat.search(text[:8000]):
        s3, d3 = 1, "brief normalization mention"
    else:
        s3, d3 = 0, "no run-rate vs one-off paragraph"
    criteria.append(CriterionScore("run_rate", "Run-rate vs one-off", s3, d3))

    # 4 Thesis pillars
    tp = section_slice(text, THESIS_PILLARS, until=r"\n#### ")
    tp_rows = count_table_rows(tp)
    if tp_rows >= 3:
        s4, d4 = 2, f"{tp_rows} pillars"
    elif tp_rows >= 1:
        s4, d4 = 1, f"{tp_rows} pillar(s)"
    else:
        s4, d4 = 0, "missing thesis pillars"
    criteria.append(CriterionScore("thesis_pillars", "Thesis pillars", s4, d4))

    # 5 Mental models
    mm = section_slice(text, MENTAL_MODELS, until=r"\n### |\n#### |\n## ")
    mm_rows = count_table_rows(mm)
    mm_paths = sum(1 for line in mm.splitlines() if PATH_LIKE.search(line))
    if mm_rows >= 3 and mm_paths >= 2:
        s5, d5 = 2, f"{mm_rows} models with paths"
    elif mm_rows >= 2:
        s5, d5 = 1, f"{mm_rows} models"
    else:
        s5, d5 = 0, "mental models thin"
    criteria.append(CriterionScore("mental_models", "Mental models", s5, d5))

    # 6 Option scan
    os_block = section_slice(text, OPTION_SCAN, until=r"\n#### ")
    os_rows = count_table_rows(os_block)
    if os_rows >= 6:
        s6, d6 = 2, f"{os_rows} rows"
    elif os_rows >= 2:
        s6, d6 = 1, f"{os_rows} rows (target ≥6)"
    else:
        s6, d6 = 0, "option scan incomplete"
    criteria.append(CriterionScore("option_scan", "Option scan", s6, d6))

    # 7 Fieldwork / management
    fw_block = re.search(r"\*\*Fieldwork / management:\*\*([^\n]+)", text, re.I)
    if fw_block and len(fw_block.group(1).strip()) > 40:
        s7, d7 = 2, "fieldwork/management addressed"
    elif re.search(r"fieldwork|management (access|meeting|call)|investor day", text, re.I):
        s7, d7 = 1, "brief fieldwork mention"
    else:
        s7, d7 = 0, "no fieldwork/management block"
    criteria.append(CriterionScore("fieldwork", "Fieldwork / management", s7, d7))

    # 8 Risks
    rk = section_slice(text, RISKS)
    rk_bullets = count_bullets(rk)
    rk_paths = sum(1 for line in rk.splitlines() if PATH_LIKE.search(line))
    has_primary = bool(re.search(r"\*\*Primary risk:\*\*", rk, re.I))
    if has_primary and rk_bullets >= 3 and rk_paths >= 1:
        s8, d8 = 2, f"{rk_bullets} bullets, filing-tied"
    elif has_primary and rk_bullets >= 2:
        s8, d8 = 1, f"{rk_bullets} bullets"
    else:
        s8, d8 = 0, "risks section thin"
    criteria.append(CriterionScore("risks", "Risks", s8, d8))

    # 9 Assumption ledger
    val_m = VALUATION_SECTION.search(text)
    val_sec = ""
    if val_m:
        rest = text[val_m.start() :]
        end_m = VALUATION_END.search(rest)
        val_sec = rest[: end_m.start()] if end_m else rest
    led = section_slice(val_sec, ASSUMPTION_LEDGER, until=r"\n#### ")
    led_rows = count_table_rows(led)
    if led_rows >= 8:
        s9, d9 = 2, f"{led_rows} rows"
    elif led_rows >= 4:
        s9, d9 = 1, f"{led_rows} rows"
    else:
        s9, d9 = 0, f"{led_rows} rows"
    criteria.append(CriterionScore("assumption_ledger", "Assumption ledger", s9, d9))

    # 10 IRR arithmetic
    irr = section_slice(val_sec, IRR_ARITHMETIC, until=r"\n### |\n#### ")
    steps = len(NUMBERED_STEP.findall(irr))
    if IRR_ARITHMETIC.search(text) and steps >= 3:
        s10, d10 = 2, f"{steps} numbered steps"
    elif IRR_ARITHMETIC.search(text):
        s10, d10 = 1, "IRR arithmetic present, few steps"
    else:
        s10, d10 = 0, "missing IRR arithmetic"
    criteria.append(CriterionScore("irr_arithmetic", "IRR arithmetic", s10, d10))

    # 11 Executive summary
    em = EXEC_SUMMARY.search(text)
    if em:
        rest = text[em.end() :]
        end_m = re.search(r"\n## ", rest)
        body = rest[: end_m.start()] if end_m else rest[:2500]
        wc = word_count(body)
        pct_count = len(re.findall(r"\*\*(-?\d+(?:\.\d+)?)\s*%\*\*", body))
        has_formula = bool(re.search(r"P₀|FCF₀|g1|g2|=\s*\(", body))
        if 100 <= wc <= 200 and pct_count >= 1 and not has_formula:
            s11, d11 = 2, f"{wc} words"
        elif wc <= 220 and pct_count >= 1:
            s11, d11 = 1, f"{wc} words (target 120–180)"
        else:
            s11, d11 = 0, f"{wc} words or missing single %"
    else:
        s11, d11 = 0, "missing executive summary"
    criteria.append(CriterionScore("executive_summary", "Executive summary", s11, d11))

    # 12 Milly
    research = path.parent
    adv = latest_adversarial(research)
    linked = bool(
        adv
        and re.search(
            r"adversarial|Adversarial:",
            text[:4000],
            re.I,
        )
    )
    if adv and linked:
        s12, d12 = 2, adv.name
    elif adv:
        s12, d12 = 1, f"{adv.name} exists, weak header link"
    else:
        s12, d12 = 0, "no adversarial pass file"
    criteria.append(CriterionScore("milly", "Milly adversarial", s12, d12))

    result = DepthResult(
        path=path,
        ticker=ticker,
        criteria=criteria,
        full_tier_count=count_full_tier_evidence(ticker) if ticker else 0,
    )

    arch_errors: list[str] = []
    arch_warns: list[str] = []

    if archetype == "holding_co":
        if not LOOKTHROUGH.search(text):
            arch_errors.append("holding_co: missing #### Look-through snapshot")
        if not SOTP_NAV.search(text):
            arch_errors.append("holding_co: missing SOTP/NAV build section")
        if not CATALYST.search(text):
            arch_warns.append("holding_co: missing #### Catalyst path")

    overlay = val.get("valuation_overlay") or ""
    nav = val.get("nav_overlay") is not None
    if archetype in ("optionality", "infrastructure") or nav or val.get("valuation_mode") == "optionality":
        if not re.search(r"GAAP|book value|economic floor|carrying value", text, re.I):
            arch_warns.append("optionality/NAV: GAAP vs economic floor not explained")
        if nav and "nav_overlay" not in text.lower() and "NAV overlay" not in text:
            arch_warns.append("nav_overlay in JSON but not referenced in dive")

    if overlay == "segment_cashflow" or val.get("segment_build"):
        if not SEGMENT_MAP.search(text):
            arch_errors.append("segment_cashflow: missing #### Segment map")

    if archetype == "compounder":
        if not re.search(r"growth|reinvest|ROIC|falsif", biz, re.I):
            arch_warns.append("compounder: weak growth mechanism / falsifier in Business & moat")

    hk_tickers = {"TPL", "ICE", "MSB", "SJT"}
    if ticker in hk_tickers or (ticker and (research / f"cross_check_HK").exists()):
        hk_files = list(research.glob("cross_check_HK_*.md"))
        if not HK_BLOCK.search(text) and not hk_files:
            arch_warns.append("HK: missing HK block and cross_check_HK file")
        elif hk_files and not HK_BLOCK.search(text):
            arch_warns.append("HK: cross_check exists but no HK block in dive")

    result.archetype_errors = arch_errors
    result.archetype_warnings = arch_warns
    if not archetype_strict:
        result.archetype_errors = []

    return result
