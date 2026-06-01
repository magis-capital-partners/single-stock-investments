"""Locate Darwin 1Q26 investor letter PDF anywhere in the repo."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAULT = ROOT / "_system" / "reference" / "quant-evolution"
DEST = VAULT / "Darwin_AI_Investments_1Q26.pdf"
INCOMING = VAULT / "INCOMING"
FRAMEWORKS = ROOT / "_system" / "frameworks"

EXACT_NAMES = (
    "Darwin AI Investments - 1Q26.pdf",
    "Darwin_AI_Investments_1Q26.pdf",
    "Darwin AI Investments 1Q26.pdf",
)


def _glob_frameworks() -> list[Path]:
    found: list[Path] = []
    if not FRAMEWORKS.is_dir():
        return found
    for pattern in ("*Darwin*.pdf", "*darwin*.pdf", "*1Q26*.pdf"):
        found.extend(sorted(FRAMEWORKS.glob(pattern)))
    # De-dupe while preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for p in found:
        if p.is_file() and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def find_darwin_pdf() -> Path | None:
    """Return first existing Darwin letter PDF (vault copy preferred)."""
    if DEST.is_file():
        return DEST
    for base in (INCOMING, FRAMEWORKS):
        for name in EXACT_NAMES:
            p = base / name
            if p.is_file():
                return p
    for p in _glob_frameworks():
        return p
    env = __import__("os").environ.get("DARWIN_PDF_SOURCE")
    if env:
        ep = Path(env)
        if ep.is_file():
            return ep
    return None


def ensure_vault_copy() -> Path:
    """Copy discovered PDF to gitignored vault path if needed."""
    src = find_darwin_pdf()
    if src is None:
        raise FileNotFoundError(
            "Darwin PDF not found. Drop at _system/frameworks/ "
            "(e.g. Darwin AI Investments - 1Q26.pdf), INCOMING/, or set DARWIN_PDF_SOURCE."
        )
    if src.resolve() != DEST.resolve():
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_bytes(src.read_bytes())
    return DEST
