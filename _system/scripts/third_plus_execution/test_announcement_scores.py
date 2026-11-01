"""Exercise announcement-clock scoring with isolated source files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('announcement_scores', Path(__file__).with_name('announcement_scores.py'))
scores = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scores)


class AnnouncementScoresTest(unittest.TestCase):
    def test_future_filing_cannot_score_the_earlier_announcement(self):
        with tempfile.TemporaryDirectory(prefix='announcement-scores-') as directory:
            root = Path(directory)
            folder = root / '_system/data/reverse_splits/local/raw/companyfacts'
            folder.mkdir(parents=True)
            def fact(value, end='2022-12-31', flow=False):
                return {'val': value, 'end': end, 'filed': '2023-01-10', 'form': '10-K', 'accn': '0000000001-23-000001', **({'start': end[:4] + '-01-01'} if flow else {})}
            values = {
                'CashAndCashEquivalentsAtCarryingValue': [fact(100)],
                'Assets': [fact(1000), fact(1100, '2021-12-31')],
                'StockholdersEquity': [fact(-20), fact(100, '2021-12-31')],
                'NetCashProvidedByUsedInOperatingActivities': [fact(-10, flow=True)],
                'NetIncomeLoss': [fact(50, flow=True)],
                'OperatingIncomeLoss': [fact(-20, flow=True), fact(100, '2021-12-31', True)],
                'Revenues': [fact(800, flow=True), fact(1000, '2021-12-31', True)],
            }
            raw = {'cik': 1, 'facts': {'us-gaap': {key: {'units': {'USD': rows}} for key, rows in values.items()}}}
            content = json.dumps(raw).encode()
            (folder / 'CIK0000000001.json').write_bytes(content)
            requests = root / 'requests.json'
            requests.write_text(json.dumps([{'cik': '1', 'day': day, 'at': day + 'T15:00:00Z'} for day in ('2023-01-09', '2023-01-10', '2023-01-11')]))
            output = root / 'result.json'
            scores.build(root, requests, output)
            result = json.loads(output.read_text())
            self.assertIsNone(result['rows']['1|2023-01-09']['score'])
            self.assertIsNone(result['rows']['1|2023-01-10']['score'])
            self.assertIsNotNone(result['rows']['1|2023-01-11']['score'])
            self.assertEqual(result['receipts']['1'], hashlib.sha256(content).hexdigest())
            self.assertFalse(result['rows']['1|2023-01-11']['coverage']['current_debt_complete'])


if __name__ == '__main__':
    unittest.main()
