"""Offline announcement-clock financial scores; never download or connect."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '_system' / 'scripts'))
import build_short_quant_screen as screen
from reverse_splits.fundamental_data import enrich


def build(source_root: Path, request_file: Path, output_file: Path) -> None:
    requests = json.loads(request_file.read_text(encoding='utf-8'))
    grouped: dict[str, list] = {}
    for request in requests:
        grouped.setdefault(str(int(request['cik'])), []).append(request)
    rows, receipts = {}, {}
    for i, (cik, entries) in enumerate(grouped.items()):
        file = source_root / '_system/data/reverse_splits/local/raw/companyfacts' / ('CIK' + cik.zfill(10) + '.json')
        if not file.exists():
            continue
        content = file.read_bytes()
        raw = json.loads(content)
        if int(raw['cik']) != int(cik):
            raise ValueError('Financial issuer mismatch')
        receipts[cik] = hashlib.sha256(content).hexdigest()
        for request in entries:
            result = enrich({'cik': cik, 'known_at': request['at']}, raw, [], screen)['fundamental']
            rows[cik + '|' + request['day']] = {key: result.get(key) for key in ('score', 'legacy_score', 'period', 'status', 'coverage')}
        if (i + 1) % 100 == 0:
            print('Announcement financial scores', i + 1, '/', len(grouped), flush=True)
    sources = {}
    for module in list(sys.modules.values()):
        file = getattr(module, '__file__', None)
        if file:
            file = Path(file).resolve()
            if file.suffix == '.py' and file.is_relative_to(ROOT):
                sources[file.relative_to(ROOT).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    sources[Path(__file__).relative_to(ROOT).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output_file.write_text(json.dumps({'rows': rows, 'receipts': receipts, 'sources': sources}, separators=(',', ':')) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--requests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.source_root, args.requests, args.output)
