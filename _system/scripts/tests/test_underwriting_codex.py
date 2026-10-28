"""The local process never inherits cloud secrets or tools; session IDs are real."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import underwriting_codex as codex


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
