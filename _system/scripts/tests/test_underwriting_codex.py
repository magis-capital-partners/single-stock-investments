"""The local process never inherits cloud secrets or tools; session IDs are real."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_codex as codex


@pytest.fixture(autouse=True)
def isolated_native_catalog_fixture(tmp_path,monkeypatch):
    home=tmp_path/'native-home'
    home.mkdir()
    catalog={'models':[{'slug':'gpt-6.1-sol','context_window':500000,'max_context_window':872000,
        'tool_mode':'code_mode_only','experimental_supported_tools':['clock','send_user_message_async'],
        'apply_patch_tool_type':'freeform','supports_search_tool':True,
        'web_search_tool_type':'text','base_instructions':'Original native instructions',
        'supported_reasoning_levels':[{'effort':'high','description':'High'}]}]}
    (home/'models_cache.json').write_text(json.dumps(catalog),encoding='utf-8')
    monkeypatch.setenv('CODEX_HOME',str(home))
    return home,catalog


def test_tool_free_local_command_uses_the_exact_model_and_keeps_user_auth():
    args = codex.command('codex',Path('empty-workspace'),Path('answer.json'))
    assert args[args.index('--model')+1] == 'gpt-6.1-sol'
    assert 'model_reasoning_effort="high"' in args
    assert 'forced_login_method="chatgpt"' in args
    assert '--ignore-user-config' in args and '--ephemeral' in args
    assert args[args.index('--sandbox')+1] == 'read-only'
    assert 'shell_tool' in args and 'plugins' in args and 'apps' in args
    assert 'web_search="disabled"' in args and 'mcp_servers={}' in args
    assert '--dangerously-bypass-approvals-and-sandbox' not in args


def test_input_admission_counts_windows_stdin_and_unicode_without_starting_a_session():
    assert codex.input_characters('first\nsecond',newline='\r\n')==13
    assert codex.input_characters('日本語🙂',newline='\n')==5
    assert codex.validate_input('a'*codex.MAX_INPUT_CHARACTERS)['input_characters']==codex.MAX_INPUT_CHARACTERS
    with pytest.raises(ValueError,match='local_input_too_large'):
        codex.validate_input('a'*(codex.MAX_INPUT_CHARACTERS+1))


def test_direct_native_execution_checks_size_before_creating_a_receipt(tmp_path):
    prompt=tmp_path/'prompt.txt'
    prompt.write_text('a'*(codex.MAX_INPUT_CHARACTERS+1),encoding='utf-8')
    with pytest.raises(ValueError,match='local_input_too_large'):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
            output_path=tmp_path/'output.json',receipt_path=tmp_path/'receipt.json',
            run=lambda *a,**kw:pytest.fail('Oversize prompt launched a native session'))
    assert not (tmp_path/'receipt.json').exists()


def test_local_receipt_retains_the_real_session_and_excludes_controller_secrets(tmp_path,monkeypatch):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    monkeypatch.setenv('CURSOR_API_KEY','cursor-secret')
    monkeypatch.setenv('GH_TOKEN','github-secret')
    monkeypatch.setenv('OPENAI_API_KEY','api-override')
    prompt,output,receipt = (tmp_path/n for n in ('prompt.txt','out.json','receipt.json'))
    prompt.write_text('Frozen issuer evidence',encoding='utf-8')
    def run(args,**kw):
        assert not {'CURSOR_API_KEY','GH_TOKEN','OPENAI_API_KEY'} & set(kw['env'])
        assert not (Path(kw.get('cwd') or args[args.index('--cd')+1])/'.git').exists()
        Path(args[args.index('--output-last-message')+1]).write_text('{"ok":true}',encoding='utf-8')
        rows=[{'type':'thread.started','thread_id':'actual-session'}, {'type':'turn.completed','usage':{'output_tokens':12}}]
        return subprocess.CompletedProcess(args,0,'\n'.join(json.dumps(r) for r in rows),'')
    codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
                         output_path=output,receipt_path=receipt,run=run)
    saved=json.loads(receipt.read_text())
    assert saved['agent_id'] == 'actual-session' and saved['status'] == 'finished'
    assert saved['provider'] == 'codex-local' and saved['reasoning_effort'] == 'high'
    assert json.loads(output.read_text()) == {'ok':True}


def test_finished_native_response_survives_a_failed_last_message_file_write(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, 'executable', lambda: 'codex')
    prompt, output, receipt = (tmp_path/n for n in ('prompt.txt', 'output.json', 'receipt.json'))
    prompt.write_text('Frozen issuer evidence', encoding='utf-8')
    answer = {'status': 'evidence_gap', 'gaps': [{'code': 'contract_terms', 'detail': 'Retrieve the operative agreement.'}]}
    usage = {'input_tokens': 123, 'output_tokens': 45}
    def run(args, **kwargs):
        # The real completed native trace retained its response on stdout, but
        # reported a failed --output-last-message write and created no file.
        rows = [{'type': 'thread.started', 'thread_id': 'paid-finished-session'},
                {'type': 'turn.started'},
                {'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'agent_message', 'text': json.dumps(answer)}},
                {'type': 'turn.completed', 'usage': usage}]
        return subprocess.CompletedProcess(args, 0, '\n'.join(json.dumps(r) for r in rows),
                                           'Failed to write last message file: path not found (os error 3)')
    codex.execute_stage(model='gpt-6.1-sol', effort='high', stage='author', prompt_path=prompt,
                        output_path=output, receipt_path=receipt, run=run)
    assert json.loads(output.read_text()) == answer
    saved = json.loads(receipt.read_text())
    assert saved['status'] == 'finished' and saved['usage'] == usage
    assert saved['agent_id'] == 'paid-finished-session'


def completed_rows(answer):
    return [{'type': 'thread.started', 'thread_id': 'one-session'},
            {'type': 'item.completed', 'item': {'id': 'item_0', 'type': 'agent_message', 'text': json.dumps(answer)}},
            {'type': 'turn.completed', 'usage': {'output_tokens': 12}}]


def test_native_file_and_stream_must_agree_without_losing_numeric_identity():
    value, source = codex.completed_output(completed_rows({'ok': True}), '{ "ok" : true }')
    assert value == {'ok': True} and source['source'] == 'last_message_file'
    with pytest.raises(ValueError, match='sources disagree'):
        codex.completed_output(completed_rows({'amount': 1}), '{"amount":1.0}')


@pytest.mark.parametrize('change', ['missing', 'multiple', 'after_turn', 'non_object', 'oversized'])
def test_native_final_message_recovery_rejects_incomplete_or_ambiguous_outputs(change):
    rows = completed_rows({'ok': True})
    if change == 'missing':
        rows.pop(1)
    elif change == 'multiple':
        rows.insert(1, rows[1])
    elif change == 'after_turn':
        rows[1], rows[2] = rows[2], rows[1]
    elif change == 'non_object':
        rows[1]['item']['text'] = '[]'
    else:
        rows[1]['item']['text'] = 'x' * 500001
    with pytest.raises(ValueError):
        codex.completed_output(rows)


def test_native_stream_recovery_keeps_the_tool_use_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, 'executable', lambda: 'codex')
    prompt = tmp_path/'prompt.txt'
    prompt.write_text('Evidence', encoding='utf-8')
    rows = completed_rows({'ok': True})
    rows.insert(1, {'type': 'item.completed', 'item': {'type': 'command_execution'}})
    with pytest.raises(ValueError, match='without tools'):
        codex.execute_stage(model='gpt-6.1-sol', effort='high', stage='author', prompt_path=prompt,
            output_path=tmp_path/'out.json', receipt_path=tmp_path/'receipt.json',
            run=lambda args, **kw: subprocess.CompletedProcess(args, 0, '\n'.join(map(json.dumps, rows)), ''))
    assert not (tmp_path/'out.json').exists()
    assert json.loads((tmp_path/'receipt.json').read_text())['usage'] == {'output_tokens': 12}


def test_disagreeing_native_outputs_preserve_both_private_sources_before_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, 'executable', lambda: 'codex')
    prompt = tmp_path/'prompt.txt'
    prompt.write_text('Evidence', encoding='utf-8')
    rows = completed_rows({'ok': True})
    def run(args, **kw):
        Path(args[args.index('--output-last-message')+1]).write_text('{"ok":false}', encoding='utf-8')
        return subprocess.CompletedProcess(args, 0, '\n'.join(map(json.dumps, rows)), '')
    with pytest.raises(ValueError, match='sources disagree'):
        codex.execute_stage(model='gpt-6.1-sol', effort='high', stage='author', prompt_path=prompt,
                            output_path=tmp_path/'out.json', receipt_path=tmp_path/'receipt.json', run=run)
    saved = json.loads((tmp_path/'receipt.json').read_text())
    diagnostics = json.loads((tmp_path/saved['diagnostics']['file']).read_text())
    assert diagnostics['last_message_file'] == '{"ok":false}'
    assert diagnostics['stdout'] == '\n'.join(map(json.dumps, rows))
    assert saved['status'] == 'finished' and saved['usage'] == {'output_tokens': 12}


def test_local_timeout_retains_a_started_session(tmp_path,monkeypatch):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    prompt=tmp_path/'prompt.txt'
    prompt.write_text('Evidence')
    def run(args,**kw):
        raise subprocess.TimeoutExpired(args,20,output=b'{"type":"thread.started","thread_id":"slow-session"}\n')
    with pytest.raises(ValueError,match='timeout_cancel_requested'):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='challenger',prompt_path=prompt,
                             output_path=tmp_path/'out.json',receipt_path=tmp_path/'receipt.json',run=run)
    assert json.loads((tmp_path/'receipt.json').read_text())['agent_id'] == 'slow-session'


def test_failed_local_session_retains_provider_failure_in_its_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    prompt = tmp_path/'prompt.txt'
    prompt.write_text('Evidence',encoding='utf-8')
    def run(args,**kw):
        return subprocess.CompletedProcess(args,1,json.dumps({'type':'turn.failed','error':{'message':'Provider temporarily unavailable'}}),'')
    with pytest.raises(ValueError,match='Provider temporarily unavailable'):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
                            output_path=tmp_path/'out.json',receipt_path=tmp_path/'receipt.json',run=run)
    saved=json.loads((tmp_path/'receipt.json').read_text(encoding='utf-8'))
    assert saved['process_exit_code']==1 and saved['failure_events'][0]['type']=='turn.failed'


@pytest.mark.parametrize('timeout', [False, True])
def test_private_native_diagnostics_survive_failure_without_a_json_error_event(tmp_path,monkeypatch,timeout):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    prompt=tmp_path/'prompt.txt'
    prompt.write_text('Evidence',encoding='utf-8')
    stdout='{"type":"thread.started","thread_id":"failed-native-session"}\n'
    stderr='Native failure visible only on stderr: fixture diagnostic\n'
    def run(args,**kw):
        if timeout:
            raise subprocess.TimeoutExpired(args,20,output=stdout.encode(),stderr=stderr.encode())
        return subprocess.CompletedProcess(args,1,stdout,stderr)
    receipt=tmp_path/'receipt.json'
    with pytest.raises(ValueError):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
                            output_path=tmp_path/'out.json',receipt_path=receipt,run=run)
    saved=json.loads(receipt.read_text(encoding='utf-8'))
    diagnostics=json.loads((receipt.parent/saved['diagnostics']['file']).read_text(encoding='utf-8'))
    assert diagnostics['stdout']==stdout and diagnostics['stderr']==stderr
    assert diagnostics['timed_out'] is timeout
    assert saved['diagnostics']['sha256']==codex.digest(diagnostics)
    assert saved['usage'] is None and saved['agent_id']=='failed-native-session'
    assert not (tmp_path/'out.json').exists()


def test_completed_native_json_after_plain_progress_requires_the_matching_last_file():
    rows = completed_rows({'status': 'evidence_gap', 'gaps': []})
    rows.insert(1, {'type': 'item.completed', 'item': {'id': 'progress', 'type': 'agent_message',
        'text': 'I will reconcile the primary evidence.'}})
    value, source = codex.completed_output(rows, '{"status":"evidence_gap","gaps":[]}')
    assert value == {'status': 'evidence_gap', 'gaps': []}
    assert source['ignored_progress_message_ids'] == ['progress']
    with pytest.raises(ValueError):
        codex.completed_output(rows)


@pytest.mark.parametrize('prior', ['{"ok":true}', '{"ok":false}', '[]', '{unfinished', 'null'])
def test_progress_separation_never_selects_between_json_candidates(prior):
    rows = completed_rows({'ok': True})
    rows.insert(1, {'type': 'item.completed', 'item': {'id': 'prior', 'type': 'agent_message', 'text': prior}})
    with pytest.raises(ValueError):
        codex.completed_output(rows, '{"ok":true}')


@pytest.mark.parametrize('change', ['after_final', 'after_turn', 'duplicate_id', 'multiple_turns', 'file_mismatch'])
def test_progress_cannot_hide_final_order_or_native_source_identity_errors(change):
    rows = completed_rows({'ok': True})
    progress = {'type': 'item.completed', 'item': {'id': 'progress', 'type': 'agent_message', 'text': 'Checking evidence.'}}
    rows.insert(1, progress)
    file = '{"ok":true}'
    if change == 'after_final':
        rows[1], rows[2] = rows[2], rows[1]
    elif change == 'after_turn':
        rows.append(rows.pop(1))
    elif change == 'duplicate_id':
        progress['item']['id'] = 'item_0'
    elif change == 'multiple_turns':
        rows.append({'type': 'turn.completed'})
    else:
        file = '{"ok":false}'
    with pytest.raises(ValueError):
        codex.completed_output(rows, file)


def test_catalog_copy_changes_only_explicit_tool_surface_fields(tmp_path,isolated_native_catalog_fixture):
    home,original=isolated_native_catalog_fixture
    original['models'].append({'slug':'other-model','tool_mode':'code_mode_only','context_window':17})
    (home/'models_cache.json').write_text(json.dumps(original),encoding='utf-8')
    before=(home/'models_cache.json').read_bytes()
    path,proof=codex.isolated_tool_catalog(tmp_path)
    copy=json.loads(path.read_text(encoding='utf-8'))
    allowed={'tool_mode','experimental_supported_tools','apply_patch_tool_type','supports_search_tool'}
    assert {k:v for k,v in copy['models'][0].items() if k not in allowed} == {k:v for k,v in original['models'][0].items() if k not in allowed}
    assert copy['models'][1:]==original['models'][1:]
    assert copy['models'][0]['tool_mode']=='direct'
    assert copy['models'][0]['experimental_supported_tools']==[]
    assert copy['models'][0]['apply_patch_tool_type'] is None
    assert (home/'models_cache.json').read_bytes()==before
    assert proof['source_catalog_hash']==codex.digest(original)
    assert proof['isolated_catalog_hash']==codex.digest(copy)
    assert proof['model_identity_context_and_instructions_unchanged']


@pytest.mark.parametrize('role',['author','challenger'])
def test_both_native_roles_receive_isolated_catalog_before_any_model_call(tmp_path,monkeypatch,role):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    prompt=tmp_path/'prompt.txt';prompt.write_text('All original evidence',encoding='utf-8')
    def run(args,**kw):
        option=next(v for v in args if v.startswith('model_catalog_json='))
        path=Path(json.loads(option.split('=',1)[1]))
        model=json.loads(path.read_text(encoding='utf-8'))['models'][0]
        assert model['slug']=='gpt-6.1-sol' and model['tool_mode']=='direct'
        assert model['experimental_supported_tools']==[] and model['apply_patch_tool_type'] is None
        assert model['context_window']==500000 and model['max_context_window']==872000
        assert kw['input']=='All original evidence'
        assert 'tools.experimental_request_user_input.enabled=false' in args
        assert 'tools.update_plan.enabled=false' in args
        assert all(name in args for name in ('goals','remote_plugin','code_mode_host'))
        rows=completed_rows({'ok':True})
        return subprocess.CompletedProcess(args,0,'\n'.join(map(json.dumps,rows)),'')
    receipt=tmp_path/'receipt.json'
    codex.execute_stage(model='gpt-6.1-sol',effort='high',stage=role,prompt_path=prompt,
        output_path=tmp_path/'answer.json',receipt_path=receipt,run=run)
    saved=json.loads(receipt.read_text())
    assert saved['tool_isolation']['model']=='gpt-6.1-sol'
    assert (tmp_path/'receipt.tools-catalog.json').is_file()


@pytest.mark.parametrize('defect',['missing','malformed','wrong_model','duplicate'])
def test_catalog_identity_failure_stops_before_model_execution(tmp_path,isolated_native_catalog_fixture,defect):
    home,catalog=isolated_native_catalog_fixture
    path=home/'models_cache.json'
    if defect=='missing':path.unlink()
    elif defect=='malformed':path.write_text('{')
    else:
        if defect=='wrong_model':catalog['models'][0]['slug']='different-model'
        else:catalog['models'].append(dict(catalog['models'][0]))
        path.write_text(json.dumps(catalog))
    prompt=tmp_path/'prompt.txt';prompt.write_text('Evidence')
    with pytest.raises((ValueError,json.JSONDecodeError)):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
            output_path=tmp_path/'out.json',receipt_path=tmp_path/'receipt.json',
            run=lambda *a,**kw:pytest.fail('Invalid catalog launched a native session'))


@pytest.mark.parametrize('tool',['list_mcp_resources','list_mcp_resource_templates'])
def test_empty_mcp_discovery_is_still_rejected_and_usage_preserved(tmp_path,monkeypatch,tool):
    monkeypatch.setattr(codex,'executable',lambda:'codex')
    prompt=tmp_path/'prompt.txt';prompt.write_text('Evidence')
    rows=completed_rows({'status':'evidence_gap','gaps':[]})
    rows.insert(1,{'type':'item.completed','item':{'type':'mcp_tool_call','server':'codex','tool':tool,
        'result':{'content':[{'type':'text','text':'{"resources":[]}'}]}}})
    with pytest.raises(ValueError,match='without tools'):
        codex.execute_stage(model='gpt-6.1-sol',effort='high',stage='author',prompt_path=prompt,
            output_path=tmp_path/'out.json',receipt_path=tmp_path/'receipt.json',
            run=lambda args,**kw:subprocess.CompletedProcess(args,0,'\n'.join(map(json.dumps,rows)),''))
    saved=json.loads((tmp_path/'receipt.json').read_text())
    assert saved['status']=='failed' and saved['usage']=={'output_tokens':12}
    assert not (tmp_path/'out.json').exists()
