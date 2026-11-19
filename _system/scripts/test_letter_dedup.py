#!/usr/bin/env python3
from __future__ import annotations

import random
import sys
import tempfile
import time
import unittest
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from build_insights import dedupe_canonical_letters  # noqa: E402
from letter_dedup import (  # noqa: E402
    _longest_match,
    _near_duplicate,
    _similarity_ratio,
    deduplicate_letter_files,
)


class LetterDedupTests(unittest.TestCase):
    def test_exact_normalized_duplicates_choose_clean_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / "Starfort Letter Q1 2026.txt"
            copy = root / "Starfort Letter (1) Q1 2026.txt"
            clean.write_text("Dear Partners,\n\nThe fund returned 4%." * 30, encoding="utf-8")
            copy.write_text("Dear Partners,  The fund returned 4%." * 30, encoding="utf-8")
            files, metadata, audit = deduplicate_letter_files([copy, clean])
            self.assertEqual(files, [clean])
            self.assertEqual(audit["exact_duplicates_suppressed"], 1)
            row = metadata[str(clean.resolve()).lower()]
            self.assertEqual(row["duplicate_count"], 1)
            self.assertTrue(row["canonical_document_id"].startswith("letter-"))

    def test_conservative_near_duplicate_detection(self) -> None:
        base = ("The portfolio owns a durable compounder with recurring revenue. " * 30).strip()
        variant = base.replace("durable compounder", "durable  compounder", 1)
        unrelated = ("A completely different investor letter about energy markets. " * 30).strip()
        self.assertTrue(_near_duplicate(base.lower(), variant.lower()))
        self.assertFalse(_near_duplicate(base.lower(), unrelated.lower()))

    def test_longest_match_equals_difflib_including_ties_and_windows(self) -> None:
        rng = random.Random(1820)
        for _ in range(1500):
            alphabet = rng.choice(["ab", "abc", "ab ", "abcdefgh"])
            a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            alo = rng.randint(0, len(a))
            ahi = rng.randint(alo, len(a))
            blo = rng.randint(0, len(b))
            bhi = rng.randint(blo, len(b))
            expected = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(alo, ahi, blo, bhi)
            self.assertEqual(_longest_match(a, alo, ahi, b, blo, bhi), tuple(expected), (a, b, alo, ahi, blo, bhi))

    def test_similarity_ratio_is_bit_identical_to_difflib(self) -> None:
        rng = random.Random(44515184240)
        words = ["fund", "returned", "the", "portfolio", "compounder", "q3", "4.2%", "and", "of", "a"]
        for _ in range(300):
            base = " ".join(rng.choice(words) for _ in range(rng.randint(0, 120)))
            chars = list(base)
            for _edit in range(rng.randint(0, 12)):
                if not chars:
                    break
                pos = rng.randrange(len(chars))
                op = rng.random()
                if op < 0.4:
                    chars[pos] = rng.choice("abcdefghij .%")
                elif op < 0.7:
                    del chars[pos]
                else:
                    chars.insert(pos, rng.choice("abcdefghij .%"))
            variant = "".join(chars)
            expected = SequenceMatcher(None, base, variant, autojunk=False).ratio()
            self.assertEqual(_similarity_ratio(base, variant), expected)
            self.assertEqual(_similarity_ratio(variant, base), SequenceMatcher(None, variant, base, autojunk=False).ratio())

    def test_near_duplicate_check_is_linear_on_letter_sized_ocr_twins(self) -> None:
        rng = random.Random(7)
        words = [f"word{idx}" for idx in range(400)] + ["the", "and", "of", "fund", "portfolio"]
        base = " ".join(rng.choice(words) for _ in range(16000))
        variant = base.replace(" the ", " teh ", 30).replace(" fund ", " fnud ", 20)
        self.assertGreater(len(base), 100_000)
        started = time.perf_counter()
        self.assertTrue(_near_duplicate(base, variant))
        # difflib.SequenceMatcher.ratio() needs over a minute on this pair.
        self.assertLess(time.perf_counter() - started, 10.0)

    def test_downstream_guard_keeps_one_canonical_document(self) -> None:
        rows, suppressed = dedupe_canonical_letters(
            [
                {"canonical_document_id": "letter-abc", "source_file": "a.txt"},
                {"canonical_document_id": "letter-abc", "source_file": "b.txt"},
                {"canonical_document_id": "letter-def", "source_file": "c.txt"},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(suppressed, 1)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
