"""Retry a validated data publication from fresh main; never run judgment models."""
from __future__ import annotations

import json
import os
import subprocess

MAX_PUBLICATION_RETRIES = 2


def request_retry(repo, count, prices_only, *, run=subprocess.run):
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count < MAX_PUBLICATION_RETRIES:
        raise ValueError('Validated publication retry limit reached')
    if not isinstance(prices_only, bool):
        raise ValueError('Refresh mode must be explicit')
    payload = {'event_type': 'refresh-autonomous-compounders', 'client_payload': {
        'prices_only': prices_only, 'publication_retry_count': count+1}}
    run(['gh', 'api', 'repos/'+repo+'/dispatches', '--method', 'POST', '--input', '-'],
        input=json.dumps(payload), text=True, check=True, timeout=60)
    return {'status': 'publication_retry_requested', 'attempt': count+1, 'prices_only': prices_only}


if __name__ == '__main__':
    result = request_retry(os.environ['GITHUB_REPOSITORY'],
        int(os.environ.get('PUBLICATION_RETRY_COUNT') or '0'),
        os.environ['REFRESH_PRICES_ONLY'].lower() == 'true')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write('\nPublication did not complete. A fresh-main retry was requested '
                         f"({result['attempt']}/{MAX_PUBLICATION_RETRIES}); no judgment calls were requested.\n")
    print(json.dumps(result))
