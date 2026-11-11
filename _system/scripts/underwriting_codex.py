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
MAX_INPUT_CHARACTERS = 1_048_576


def input_characters(prompt, newline=None):
    # Windows text-mode stdin expands LF to CRLF. Count surrogate pairs
    # conservatively as well; never admit more than the native turn/start cap.
    separator = os.linesep if newline is None else newline
    return len(prompt.encode('utf-16-le'))//2 + prompt.count('\n')*(len(separator)-1)


def validate_input(prompt):
    count = input_characters(prompt)
    require(count <= MAX_INPUT_CHARACTERS,
            f'local_input_too_large: {count} characters exceeds {MAX_INPUT_CHARACTERS}; complete evidence retained')
    return {'input_characters':count, 'maximum_input_characters':MAX_INPUT_CHARACTERS}


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


def validate_context_window(context_window,subject=None):
    if context_window is None:return {}
    require(subject=='CPRT' and type(context_window) is int and context_window==872000,
            'Only the explicit CPRT native context exception is supported')
    cache=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'models_cache.json'
    require(cache.is_file(),'Current native model context catalog is required before admission')
    raw=cache.read_bytes();catalog=json.loads(raw);models=catalog.get('models') or []
    model=next((item for item in models if item.get('slug')=='gpt-6.1-sol'),None) or {}
    maximum=model.get('max_context_window');default=model.get('context_window')
    require(type(maximum) is int and type(default) is int and default<=context_window<=maximum,
            'Requested context is not advertised by the current native model catalog')
    return {'model_context_window':context_window,'catalog_default_context_window':default,
            'catalog_max_context_window':maximum,'catalog_hash':digest(catalog),'subject':'CPRT'}


def command(binary, directory, output, *, context_window=None, subject=None):
    args = [binary, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--model', 'gpt-6.1-sol', '--json', '--color', 'never',
            '--config', 'model_reasoning_effort="high"', '--config', 'forced_login_method="chatgpt"',
            '--config', 'approval_policy="never"', '--config', 'web_search="disabled"',
            '--config', 'mcp_servers={}', '--cd', str(directory), '--output-last-message', str(output)]
    if context_window is not None:
        validate_context_window(context_window,subject)
        args += ['--config','model_context_window='+str(context_window)]
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


def completed_output(rows, file_text=None):
    """Import one completed native response, including a failed file delivery."""
    def object_value(text):
        require(isinstance(text, str) and len(text) <= 500_000, 'Invalid or oversized local stage JSON')
        text = re.sub(r'^```(?:json)?\s*\n([\s\S]*)\n```$', r'\1', text.strip())
        value = json.loads(text)
        require(isinstance(value, dict), 'Local stage must return one JSON object')
        return value
    messages = [(index, row['item']) for index, row in enumerate(rows)
                if row.get('type') == 'item.completed' and (row.get('item') or {}).get('type') == 'agent_message']
    progress_ids = []
    if len(messages) > 1:
        # Native progress and the final answer share an event type. Only the
        # final JSON may agree with the independently saved last-message file;
        # never choose between duplicate, conflicting or malformed JSON drafts.
        require(file_text is not None, 'Multiple native messages require the saved final file')
        ids = [item.get('id') for _, item in messages]
        require(all(ids) and len(set(ids)) == len(ids), 'Ambiguous native message identities')
        for _, item in messages[:-1]:
            text = item.get('text')
            require(isinstance(text, str) and len(text) <= 500_000
                    and not text.lstrip().startswith(('{', '[', '```')),
                    'Ambiguous native JSON candidates')
            try:
                json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                require(False, 'Ambiguous native JSON candidates')
            progress_ids.append(item['id'])
    stream_value, message_id = None, None
    if messages:
        threads = [row for row in rows if row.get('type') == 'thread.started' and row.get('thread_id')]
        finished = [index for index, row in enumerate(rows) if row.get('type') == 'turn.completed']
        require(len(threads) == len(finished) == 1
                and all(index < finished[0] for index, _ in messages),
                'Native final message has no unique completed turn')
        stream_value = object_value(messages[-1][1].get('text'))
        message_id = messages[-1][1].get('id')
    file_value = object_value(file_text) if file_text is not None else None
    require(file_value is not None or stream_value is not None, 'No complete native final message or answer file')
    if file_value is not None and stream_value is not None:
        require(digest(file_value) == digest(stream_value), 'Native output sources disagree')
    value = file_value if file_value is not None else stream_value
    provenance = {'source': 'last_message_file' if file_value is not None else 'native_agent_message',
                  'message_id': message_id, 'output_hash': digest(value)}
    if progress_ids:
        provenance['ignored_progress_message_ids'] = progress_ids
    return value, provenance


def execute_stage(*, model, effort, stage, prompt_path, output_path, receipt_path, timeout=1200, run=subprocess.run, context_window=None, subject=None):
    from underwriting_pipeline import write
    require(model == 'gpt-6.1-sol' and effort == 'high' and stage in ('author', 'challenger'),
            'Local underwriting requires GPT-6.1 Sol High and a judgment role')
    prompt = prompt_path.read_text(encoding='utf-8')
    input_admission = {**validate_input(prompt),**validate_context_window(context_window,subject)}
    # No controller secrets, Cursor key, GitHub credential or API-key override
    # enter the model process. It reuses the existing signed-in Codex account.
    permitted = {'PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
                 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'CODEX_HOME'}
    env = {k: v for k, v in os.environ.items() if k in permitted}
    receipt = {'schema_version': 'underwriting-call/1', 'provider': 'codex-local', 'stage': stage,
               'model': model, 'reasoning_effort': effort, 'status': 'starting',
               'started_at': datetime.now(timezone.utc).isoformat(), 'tools_disabled': True,
               'input_admission':input_admission}
    write(receipt_path, receipt)
    with tempfile.TemporaryDirectory(prefix='ssi-codex-underwriting-') as temporary:
        directory = Path(temporary)
        require(directory.resolve().parent == Path(tempfile.gettempdir()).resolve()
                and directory.name.startswith('ssi-codex-underwriting-'), 'Unsafe isolated session directory')
        answer = directory/'answer.json'
        args = command(executable(), directory, answer, context_window=context_window, subject=subject)
        timed_out = False
        try:
            result = run(args, input=prompt, capture_output=True,
                         encoding='utf-8', errors='replace', env=env, timeout=timeout, check=False)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code, timed_out = exc.stdout, exc.stderr, -1, True
        def decoded(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value or ''
        # Ephemeral sessions remove their scratch directory. Preserve both
        # native streams privately before validation or cleanup: an exit 1 can
        # contain only thread.started on stdout and its real error on stderr.
        # A hash of parsed events cannot recover that lost failure explanation.
        file_text, file_error = None, None
        try:
            if answer.is_file():
                file_text = answer.read_text(encoding='utf-8')
        except OSError as exc:
            file_error = str(exc)
        diagnostics = {'stdout': decoded(stdout), 'stderr': decoded(stderr),
                       'process_exit_code': code, 'timed_out': timed_out}
        if file_text is not None:
            diagnostics['last_message_file'] = file_text
        if file_error:
            diagnostics['last_message_file_error'] = file_error
        diagnostic_path = receipt_path.with_name(receipt_path.stem+'.diagnostics.json')
        write(diagnostic_path, diagnostics)
        receipt['diagnostics'] = {'file': diagnostic_path.name, 'sha256': digest(diagnostics)}
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
                +' '+json.dumps(receipt.get('failure_events') or [],ensure_ascii=False)[:1500]
                +' (private diagnostics: '+diagnostic_path.name+')')
        value, provenance = completed_output(rows, file_text)
        write(output_path, value)
        receipt['output_import'] = provenance
        write(receipt_path, receipt)
