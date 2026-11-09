import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_dashboard_data as validator


class ConflictMarkers(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'podcasts.json'
            path.write_text(text, encoding='utf8')
            with patch.object(validator, 'ROOT', root):
                return validator._check_merge_conflict_markers(path)

    def test_valid_episode_description_separator_does_not_block_publication(self):
        text = json.dumps({'description': 'Episode notes about companies. ========'})
        self.assertEqual(json.loads(text)['description'][-8:], '========')
        self.assertIsNone(self.check(text))

    def test_real_conflict_marker_lines_still_block_publication(self):
        for text in ['<<<<<<< HEAD\n{}\n=======\n{}\n>>>>>>> branch\n', '  <<<<<<< HEAD\r\n{}\r\n', '=======\n{}\n']:
            with self.subTest(text=text):
                self.assertIn('unresolved git merge conflict markers', self.check(text))

    def test_quoted_discussion_of_git_markers_is_regular_json_content(self):
        self.assertIsNone(self.check(json.dumps({'note': 'An example uses <<<<<<< HEAD and >>>>>>> branch.'})))


if __name__ == '__main__':
    unittest.main()
