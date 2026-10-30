"""One tool-free, ephemeral underwriting session using the owner's Codex login."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from underwriting_contract import digest, require

DISABLED = ('shell_tool', 'apps', 'plugins', 'hooks', 'multi_agent', 'browser_use',
            'browser_use_external', 'computer_use', 'image_generation', 'view_image', 'sleep_tool')


def executable():
    found = shutil.which('codex')
    if found:
        return found
    directory = Path(os.environ.get('LOCALAPPDATA', ''))/'OpenAI/Codex/bin'
    candidates = list(directory.glob('*/codex.exe'))
    require(candidates, 'Signed-in Codex CLI is not installed')
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


def preflight(run=subprocess.run):
    result = run([executable(), 'login', 'status'], capture_output=True, text=True, timeout=30, check=False)
    require(result.returncode == 0 and 'ChatGPT' in result.stdout+result.stderr,
            'Sign in to the local Codex CLI with ChatGPT before underwriting')
    cache = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'models_cache.json'
    if cache.is_file():
        models = json.loads(cache.read_text(encoding='utf-8')).get('models') or []
        model = next((m for m in models if m.get('slug') == 'gpt-6.1-sol'), None)
        require(model and any(r.get('effort') == 'high' for r in model.get('supported_reasoning_levels') or []),
                'Local Codex catalog does not offer GPT-6.1 Sol High')
    return {'provider': 'codex-local', 'model': 'gpt-6.1-sol', 'reasoning_effort': 'high', 'login': 'ChatGPT'}


def command(binary, directory, output):
    args = [binary, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--model', 'gpt-6.1-sol', '--json', '--color', 'never',
            '--config', 'model_reasoning_effort="high"', '--config', 'forced_login_method="chatgpt"',
            '--config', 'approval_policy="never"', '--config', 'web_search="disabled"',
            '--config', 'mcp_servers={}', '--cd', str(directory), '--output-last-message', str(output)]
    for feature in DISABLED:
        args += ['--disable', feature]
    return args+['-']


def events(text):
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='replace')
    rows = []
    for line in (text or '').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def execute_stage(*, model, effort, stage, prompt_path, output_path, receipt_path, timeout=1200, run=subprocess.run):
    from underwriting_pipeline import write
    require(model == 'gpt-6.1-sol' and effort == 'high' and stage in ('author', 'challenger'),
            'Local underwriting requires GPT-6.1 Sol High and a judgment role')
    # No controller secrets, Cursor key, GitHub credential or API-key override
    # enter the model process. It reuses the existing signed-in Codex account.
    permitted = {'PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
                 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'CODEX_HOME'}
    env = {k: v for k, v in os.environ.items() if k in permitted}
    receipt = {'schema_version': 'underwriting-call/1', 'provider': 'codex-local', 'stage': stage,
               'model': model, 'reasoning_effort': effort, 'status': 'starting',
               'started_at': datetime.now(timezone.utc).isoformat(), 'tools_disabled': True}
    write(receipt_path, receipt)
    with tempfile.TemporaryDirectory(prefix='ssi-codex-underwriting-') as temporary:
        directory = Path(temporary)
        require(directory.resolve().parent == Path(tempfile.gettempdir()).resolve()
                and directory.name.startswith('ssi-codex-underwriting-'), 'Unsafe isolated session directory')
        answer = directory/'answer.json'
        args = command(executable(), directory, answer)
        timed_out = False
        try:
            result = run(args, input=prompt_path.read_text(encoding='utf-8'), capture_output=True,
                         encoding='utf-8', errors='replace', env=env, timeout=timeout, check=False)
            stdout, code = result.stdout, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, code, timed_out = exc.stdout, -1, True
        rows = events(stdout)
        receipt['agent_id'] = next((r.get('thread_id') for r in rows if r.get('type') == 'thread.started'), None)
        receipt['run_id'] = receipt['agent_id']  # Exactly one prompt per ephemeral CLI session.
        receipt['events_hash'] = digest(rows)
        receipt['usage'] = next((r.get('usage') for r in rows if r.get('type') == 'turn.completed'), None)
        finished = any(r.get('type') == 'turn.completed' for r in rows)
        forbidden = any((r.get('item') or {}).get('type') in
                        ('command_execution', 'file_change', 'mcp_tool_call', 'web_search') for r in rows)
        receipt['status'] = ('timeout_cancel_requested' if timed_out else
                             'finished' if code == 0 and finished and receipt['agent_id'] and not forbidden else 'failed')
        if receipt['status'] != 'finished':
            receipt['failure_events'] = [r for r in rows if r.get('type') in ('error', 'turn.failed')][-3:]
            receipt['process_exit_code'] = code
        receipt['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(receipt_path, receipt)
        require(receipt['status'] == 'finished', 'Local Codex stage did not finish without tools: '+receipt['status']
                +' '+json.dumps(receipt.get('failure_events') or [],ensure_ascii=False)[:1500])
        text = answer.read_text(encoding='utf-8')
        require(len(text) <= 500_000, 'Oversized local stage JSON')
        text = re.sub(r'^```(?:json)?\s*\n([\s\S]*)\n```$', r'\1', text.strip())
        value = json.loads(text)
        require(isinstance(value, dict), 'Local stage must return one JSON object')
        write(output_path, value)
