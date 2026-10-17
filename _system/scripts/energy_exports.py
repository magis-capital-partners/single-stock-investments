"""Static downloads work in ordinary browsers and embedded preview browsers."""
import csv
import io
import os
import tempfile
from pathlib import Path


def scenario_csv(model, bridge, scenario):
    costs = {r['period']: r for s in bridge['scenarios'] if s['id'] == scenario['id'] for r in s['rows']}
    rows = []
    for gas in scenario['rows']:
        btc = costs.get(gas['period'], {})
        row = {'model_id': model['model_id'], 'as_of': model['as_of'], 'scenario': scenario['id'],
               'gas_status': gas['status'], 'btc_status': btc.get('status', 'unavailable'),
               **gas, **btc}
        rows.append({k: v for k, v in row.items() if not isinstance(v, (list, dict)) and k != 'status'})
    fields = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return stream.getvalue()


def write_csv(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name+'.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
