#!/usr/bin/env python3
"""Scan Horizon Kinetics extracts (+ optional full vault) for ticker-relevant material.

Outputs:
  {TICKER}/third-party-analyses/hk_scan_{date}.json
  {TICKER}/third-party-analyses/hk_scan_{date}.md

Usage:
  python _system/scripts/scan_hk_sources.py TPL
  python _system/scripts/scan_hk_sources.py SJT MSB ICE --write-references
  python _system/scripts/scan_hk_sources.py TPL --strict   # exit 1 if no hits

Environment:
  HK_PDFS_ROOT — path to full hk_pdfs vault (400+ PDFs) when not on Windows workspace
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WISDOM = ROOT / "_system" / "reference" / "investment-wisdom"
INDEX_PATH = WISDOM / "hk_ticker_index.json"
PATHS_PATH = WISDOM / "hk_paths.json"
HK_EXTRACTS = WISDOM / "horizon-kinetics"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hk_vault_paths import load_paths_cfg, resolve_vault_root  # noqa: E402

HK_SCAN_BEGIN = "<!-- HK_SCAN_BEGIN -->"
HK_SCAN_END = "<!-- HK_SCAN_END -->"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compile_patterns(patterns: list[str], exclude: list[str]) -> tuple[list[re.Pattern], list[re.Pattern]]:
    compiled = [re.compile(p, re.I) for p in patterns]
    excl = [re.compile(p, re.I) for p in exclude]
    return compiled, excl


def line_excluded(line: str, excl: list[re.Pattern]) -> bool:
    return any(p.search(line) for p in excl)


def scan_text_lines(
    rel_path: str,
    text: str,
    patterns: list[re.Pattern],
    exclude: list[re.Pattern],
    *,
    max_hits: int = 8,
) -> list[dict]:
    hits: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if line_excluded(line, exclude):
            continue
        if not any(p.search(line) for p in patterns):
            continue
        snippet = line.strip()[:200]
        hits.append({"path": rel_path, "line": i, "snippet": snippet})
        if len(hits) >= max_hits:
            break
    return hits


def scan_file(
    path: Path,
    patterns: list[re.Pattern],
    exclude: list[re.Pattern],
) -> list[dict]:
    if not path.exists():
        return []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return scan_text_lines(rel, text, patterns, exclude)


def scan_extract_dir(
    patterns: list[re.Pattern],
    exclude: list[re.Pattern],
) -> list[dict]:
    hits: list[dict] = []
    if not HK_EXTRACTS.is_dir():
        return hits
    for f in sorted(HK_EXTRACTS.glob("*.txt")):
        hits.extend(scan_file(f, patterns, exclude))
    return hits


def scan_vault_filenames(vault: Path, patterns: list[re.Pattern], exclude: list[re.Pattern]) -> list[dict]:
    hits: list[dict] = []
    for pdf in vault.rglob("*.pdf"):
        name = pdf.name
        if line_excluded(name, exclude):
            continue
        if not any(p.search(name) for p in patterns):
            continue
        hits.append({"path": str(pdf), "line": 0, "snippet": f"PDF filename match: {name}"})
    return hits[:20]


def scan_vault_text(vault: Path, text_subdir: str, patterns: list[re.Pattern], exclude: list[re.Pattern]) -> list[dict]:
    text_dir = vault / text_subdir
    if not text_dir.is_dir():
        return []
    hits: list[dict] = []
    for f in sorted(text_dir.glob("*.txt")):
        hits.extend(scan_file(f, patterns, exclude))
        if len(hits) >= 15:
            break
    return hits


def curated_rows(entry: dict) -> list[dict]:
    rows = []
    for c in entry.get("curated", []):
        p = ROOT / c["path"]
        rows.append(
            {
                "path": c["path"],
                "topic": c.get("topic", ""),
                "use": c.get("use", "Context only; not in base IRR without human approval"),
                "exists": p.exists(),
                "source": "curated",
            }
        )
    for s in entry.get("stahl_pdfs", []):
        p = ROOT / s["path"]
        rows.append(
            {
                "path": s["path"],
                "topic": s.get("topic", ""),
                "use": s.get("use", "Stahl shelf — croupier / exchange framing"),
                "exists": p.exists(),
                "source": "stahl",
            }
        )
    return rows


def merge_dynamic_hits(curated_paths: set[str], dynamic: list[dict]) -> list[dict]:
    extra = []
    for h in dynamic:
        if h["path"] in curated_paths:
            continue
        extra.append(
            {
                "path": h["path"],
                "topic": f"Line {h['line']}: {h['snippet'][:120]}",
                "use": "Auto-discovered — review and add to hk_ticker_index.json if material",
                "exists": True,
                "source": "scan",
                "line": h.get("line"),
            }
        )
    return extra


def scan_ticker(ticker: str, index: dict, paths_cfg: dict) -> dict:
    ticker = ticker.upper()
    entry = index.get("tickers", {}).get(ticker)
    if not entry:
        return {
            "ticker": ticker,
            "status": "no_index_entry",
            "sources": [],
            "mental_models": [],
            "vault_scanned": False,
            "cross_check": None,
        }

    patterns_raw = entry.get("patterns", [])
    exclude_raw = entry.get("exclude_patterns", [])
    patterns, exclude = compile_patterns(patterns_raw, exclude_raw)

    curated = curated_rows(entry)
    curated_paths = {r["path"] for r in curated}

    dynamic = scan_extract_dir(patterns, exclude)
    vault_root = resolve_vault_root(paths_cfg)
    vault_hits: list[dict] = []
    if vault_root:
        vault_hits = scan_vault_filenames(vault_root, patterns, exclude)
        text_sub = paths_cfg.get("vault_text_subdir", "book/build/text")
        vault_hits.extend(scan_vault_text(vault_root, text_sub, patterns, exclude))

    extra = merge_dynamic_hits(curated_paths, dynamic + vault_hits)

    return {
        "ticker": ticker,
        "company": entry.get("company", ""),
        "status": "ok",
        "mental_models": entry.get("mental_models", []),
        "sources": curated + extra,
        "vault_scanned": vault_root is not None,
        "vault_root": str(vault_root) if vault_root else None,
        "cross_check": entry.get("cross_check"),
        "scan_date": date.today().isoformat(),
    }


def write_scan_outputs(ticker: str, result: dict, out_date: str) -> tuple[Path, Path]:
    tp = ROOT / ticker / "third-party-analyses"
    tp.mkdir(parents=True, exist_ok=True)
    json_path = tp / f"hk_scan_{out_date}.json"
    md_path = tp / f"hk_scan_{out_date}.md"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# {ticker} — Horizon Kinetics scan",
        "",
        f"**Date:** {out_date}",
        f"**Vault scanned:** {'yes' if result.get('vault_scanned') else 'no (set HK_PDFS_ROOT or use Windows path)'}",
        "",
    ]
    if result.get("mental_models"):
        lines.append(f"**Mental models:** {', '.join(result['mental_models'])}")
        lines.append("")
    if result.get("cross_check"):
        lines.append(f"**Approved cross-check:** `{result['cross_check']}`")
        lines.append("")
    lines.extend(
        [
            "| Source | Topic | Use in Marvin work |",
            "|--------|-------|-------------------|",
        ]
    )
    for s in result.get("sources", []):
        status = "" if s.get("exists", True) else " **[MISSING FILE]**"
        lines.append(f"| `{s['path']}`{status} | {s.get('topic', '')} | {s.get('use', '')} |")
    if not result.get("sources"):
        lines.append("| (none) | — | Add ticker to hk_ticker_index.json or widen patterns |")
    lines.append("")
    lines.append(
        "HK commentaries are **context tier** — cite in narrative and cross-checks; "
        "do not fold into base IRR without human approval (`third_party_sources.md`)."
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def hk_block_markdown(result: dict) -> str:
    if result.get("status") != "ok" or not result.get("sources"):
        return ""
    rows = []
    for s in result["sources"][:12]:
        topic = (s.get("topic") or "")[:80]
        rows.append(f"| `{s['path']}` | {topic} | Context — not in base IRR |")
    cc = result.get("cross_check")
    cc_line = f"\n**Cross-check:** `{cc}`\n" if cc else ""
    models = ", ".join(result.get("mental_models") or [])
    scan_date = result.get("scan_date", date.today().isoformat())
    return (
        f"{HK_SCAN_BEGIN}\n"
        f"### Horizon Kinetics cross-reference\n\n"
        f"Auto-scan `{result['ticker']}/third-party-analyses/hk_scan_{scan_date}.md`. "
        f"Mental models: {models or 'see mental_models.md'}.\n"
        f"{cc_line}\n"
        f"| HK / Stahl source | Topic | Status |\n"
        f"|-----------------|-------|--------|\n"
        + "\n".join(rows)
        + f"\n\n{HK_SCAN_END}"
    )


def _hk_table_body(result: dict) -> str:
    block = hk_block_markdown(result)
    if not block:
        return ""
    inner = block.replace(HK_SCAN_BEGIN, "").replace(HK_SCAN_END, "").strip()
    return inner


def patch_references_md(ticker: str, result: dict) -> None:
    ref = ROOT / ticker / "third-party-analyses" / "references.md"
    if not ref.exists():
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_text(f"# {ticker} — Third-party references\n\n", encoding="utf-8")
    text = ref.read_text(encoding="utf-8")
    section_header = "## Horizon Kinetics (HK scan)"
    body = _hk_table_body(result)
    if section_header in text:
        start = text.index(section_header)
        rest = text[start + len(section_header) :]
        next_sec = rest.find("\n## ")
        if next_sec >= 0:
            text = text[:start] + section_header + "\n\n" + body + "\n" + rest[next_sec:]
        else:
            text = text[:start] + section_header + "\n\n" + body + "\n"
    else:
        text = text.rstrip() + f"\n\n{section_header}\n\n{body}\n"
    ref.write_text(text, encoding="utf-8")


def inject_dive_primary_sources(ticker: str, result: dict, dive_date: str) -> bool:
    research = ROOT / ticker / "research"
    dive = research / f"deep_dive_{dive_date}.md"
    if not dive.exists():
        alts = sorted(research.glob("deep_dive_*.md"))
        if not alts:
            return False
        dive = alts[-1]
    block = hk_block_markdown(result)
    if not block:
        return False
    text = dive.read_text(encoding="utf-8")
    if HK_SCAN_BEGIN in text and HK_SCAN_END in text:
        pre = text[: text.index(HK_SCAN_BEGIN)]
        post = text[text.index(HK_SCAN_END) + len(HK_SCAN_END) :]
        text = pre + block + post
    elif "## Primary sources reviewed" in text:
        idx = text.index("## Primary sources reviewed")
        next_h2 = text.find("\n## ", idx + 5)
        if next_h2 == -1:
            text = text.rstrip() + "\n\n" + block + "\n"
        else:
            text = text[:next_h2].rstrip() + "\n\n" + block + "\n" + text[next_h2:]
    else:
        return False
    dive.write_text(text, encoding="utf-8")
    return True


def load_latest_scan(ticker: str) -> dict | None:
    tp = ROOT / ticker / "third-party-analyses"
    scans = sorted(tp.glob("hk_scan_*.json"))
    if not scans:
        return None
    return json.loads(scans[-1].read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan HK / Stahl sources for ticker relevance")
    parser.add_argument("tickers", nargs="+", help="Ticker symbol(s)")
    parser.add_argument("--date", default=date.today().isoformat(), help="Scan date YYYY-MM-DD")
    parser.add_argument("--write-references", action="store_true", help="Update references.md HK section")
    parser.add_argument("--inject-dive", action="store_true", help="Inject HK block into deep dive Primary sources")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if indexed ticker has zero sources")
    args = parser.parse_args()

    if not INDEX_PATH.exists():
        print(f"ERROR: missing {INDEX_PATH}")
        return 1
    index = load_json(INDEX_PATH)
    paths_cfg = load_json(PATHS_PATH) if PATHS_PATH.exists() else {}

    failed = False
    for raw in args.tickers:
        ticker = raw.upper()
        result = scan_ticker(ticker, index, paths_cfg)
        _jpath, mpath = write_scan_outputs(ticker, result, args.date)
        n = len(result.get("sources", []))
        print(f"OK {ticker}: {n} sources -> {mpath.relative_to(ROOT)}")
        if args.write_references and result.get("status") == "ok":
            patch_references_md(ticker, result)
            print(f"  updated {ticker}/third-party-analyses/references.md")
        if args.inject_dive:
            if inject_dive_primary_sources(ticker, result, args.date):
                print(f"  injected HK block into deep dive")
        if args.strict and result.get("status") == "ok" and n == 0:
            print(f"STRICT FAIL {ticker}: zero HK sources")
            failed = True
        if result.get("status") == "no_index_entry":
            print(f"WARN {ticker}: not in hk_ticker_index.json — add entry or use dynamic-only scan")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
