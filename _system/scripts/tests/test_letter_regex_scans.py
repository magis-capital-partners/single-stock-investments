"""The letter-scan fast paths must return exactly what the plain regexes did.

build_superinvestor_insights runs these scans for every letter on every
intake-full run, so they are rewritten for speed; the original patterns are
kept here as the oracle.
"""
from __future__ import annotations

import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_superinvestor_insights as bsi  # noqa: E402
import ticker_identity as ti  # noqa: E402

TRICKY = list("aAiIsSkKmM0 9-._/&\n") + ["\u0130", "\u0131", "\u017f", "\u212a", "\u00e9"]


def _theme_oracle(text: str, keyword: str) -> list[tuple[int, int]]:
    clean = keyword.strip()
    if not clean:
        return []
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(clean)}(?![A-Za-z0-9])", re.I)
    return [m.span() for m in pattern.finditer(text)]


def _ticker_oracle(text: str, base: str) -> list[int]:
    pattern = rf"(?<![A-Z0-9.\-]){re.escape(base)}(?![A-Z0-9.\-])"
    return [m.start() for m in re.finditer(pattern, text, re.I)]


def _random_text(rng: random.Random, words: list[str], size: int) -> str:
    parts = []
    while sum(map(len, parts)) < size:
        if rng.random() < 0.5:
            parts.append(rng.choice(words))
        else:
            parts.append("".join(rng.choice(TRICKY) for _ in range(rng.randint(1, 4))))
    return "".join(parts)


def test_ignorecase_fold_covers_every_code_point_matching_ascii():
    ascii_alnum = re.compile(r"[a-z0-9]", re.I)
    outside = {chr(c) for c in range(0x80, 0x110000) if ascii_alnum.fullmatch(chr(c))}
    folded = {ch for ch in outside if ch.translate(bsi._IGNORECASE_ASCII_FOLD) != ch}
    assert outside == folded


def test_theme_keyword_matches_equal_regex_oracle():
    rng = random.Random(1805)
    keywords = sorted({kw for kws in bsi.THEME_KEYWORDS.values() for kw in kws}) + ["ss", "kk", "ai", " ai "]
    for _ in range(300):
        keyword = rng.choice(keywords)
        variants = [keyword, keyword.upper(), keyword.title(), keyword.replace("s", "\u017f").replace("i", "\u0131")]
        text = _random_text(rng, variants, rng.randint(1, 400))
        got = [m.span() for m in bsi._theme_keyword_matches(text, keyword)]
        assert got == _theme_oracle(text, keyword), (keyword, text)


def test_paragraph_index_equals_prefix_count():
    rng = random.Random(1807)
    for _ in range(200):
        text = "".join(rng.choice(["\n", "\n\n", "a", " ", "\n\n\n"]) for _ in range(rng.randint(0, 60)))
        ends = bsi._paragraph_break_ends(text)
        for pos in range(len(text) + 1):
            assert bsi.bisect.bisect_right(ends, pos) == text.count("\n\n", 0, pos)


def test_extract_themes_unchanged_on_sample_letter():
    text = (
        "Artificial intelligence demand supports NVDA.\n\nWe also see AI capex "
        "and data center power needs. \u0130NFLATION and inflation remain.\n\n"
        "Bank credit quality is fine at JPM; banks look cheap."
    )
    themes = bsi.extract_themes(text, ["NVDA", "JPM"])
    assert {row["theme"] for row in themes} >= {"AI"}
    for row in themes:
        assert row["hit_count"] >= 2


def test_ticker_token_starts_equal_regex_oracle():
    rng = random.Random(1762 + 1)
    bases = ["A", "MSB", "BRK", "T", "K", "SI", ""]
    for _ in range(400):
        base = rng.choice(bases)
        variants = [base, base.lower(), "." + base, base + "-", "NYSE: " + base]
        text = _random_text(rng, variants, rng.randint(0, 300))
        assert list(ti._ticker_token_starts(text, base)) == _ticker_oracle(text, base), (base, text)


def test_large_document_exchange_pairs_parsed_once(monkeypatch):
    calls = []
    real = ti._exchange_pairs

    def counting(text):
        calls.append(len(text))
        return real(text)

    monkeypatch.setattr(ti, "_exchange_pairs", counting)
    monkeypatch.setattr(ti, "_large_text_pairs", None)
    book = ("Mesoblast Limited (ASX: MSB) and Mesabi Trust (NYSE: MSB). " * 2000)
    assert len(book) > 65536
    for ticker in ["MSB", "AAPL", "MSB", "BRK.B"]:
        assert ti.explicit_exchange_mentions(book, ticker) == [
            exchange for symbol, exchange in real(book) if symbol in {ticker.split(".")[0], ticker}
        ]
    assert calls == [len(book)]
    other = book + " Mesoblast (ASX: MSB)"
    expected = [exchange for symbol, exchange in real(other) if symbol == "MSB"]
    assert ti.explicit_exchange_mentions(other, "MSB") == expected
    assert len(expected) == len(ti.explicit_exchange_mentions(book, "MSB")) + 1
    assert len(calls) == 3
