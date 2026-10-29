"""Quarter folders resolve by name under Letters, not a trashed id."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from letter_quarter_folders import (  # noqa: E402
    CANONICAL_LETTERS_ID,
    PREFERRED_LETTER_QUARTERS,
    STALE_LETTER_QUARTER_IDS,
    choose_quarter_keeper,
    parse_quarter_name,
)


class LetterQuarterFolderTest(unittest.TestCase):
    def test_stale_q3_id_is_not_preferred(self) -> None:
        preferred = PREFERRED_LETTER_QUARTERS[("2026", "3")]
        self.assertNotIn(preferred, STALE_LETTER_QUARTER_IDS)
        self.assertEqual(preferred, "1GcMdQfFSDMTAjmVQsjGPKb3dLOndqCiD")

    def test_named_live_child_beats_trashed_id_with_more_files(self) -> None:
        stale = next(iter(STALE_LETTER_QUARTER_IDS))
        chosen = choose_quarter_keeper(
            "2026",
            "3",
            [
                {"id": stale, "name": "2026 Q3", "parents": [CANONICAL_LETTERS_ID], "_child_count": 500},
                {
                    "id": "1GcMdQfFSDMTAjmVQsjGPKb3dLOndqCiD",
                    "name": "2026 Q3",
                    "parents": [CANONICAL_LETTERS_ID],
                    "_child_count": 5,
                },
            ],
        )
        self.assertEqual(chosen["id"], "1GcMdQfFSDMTAjmVQsjGPKb3dLOndqCiD")

    def test_named_live_child_beats_a_stale_preferred_hint(self) -> None:
        stale = next(iter(STALE_LETTER_QUARTER_IDS))
        chosen = choose_quarter_keeper(
            "2026",
            "3",
            [
                {"id": stale, "name": "2026 3Q", "_child_count": 900},
                {
                    "id": "live-by-name",
                    "name": "2026 Q3",
                    "parents": [CANONICAL_LETTERS_ID],
                    "_child_count": 2,
                },
            ],
        )
        self.assertEqual(chosen["id"], "live-by-name")

    def test_hint_still_wins_when_parent_ids_are_absent(self) -> None:
        q2 = PREFERRED_LETTER_QUARTERS[("2026", "2")]
        chosen = choose_quarter_keeper(
            "2026",
            "2",
            [
                {"id": "other", "_child_count": 99},
                {"id": q2, "_child_count": 1},
            ],
        )
        self.assertEqual(chosen["id"], q2)

    def test_alias_parse(self) -> None:
        self.assertEqual(parse_quarter_name("2026 3Q Letters"), ("2026", "3"))
        self.assertEqual(parse_quarter_name("2026 Q3"), ("2026", "3"))


if __name__ == "__main__":
    unittest.main()
