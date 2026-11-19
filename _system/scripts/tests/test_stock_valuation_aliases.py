"""A reused ticker must not create a second company or overwrite original research."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stock_valuation_aliases import consolidate_aliases, legacy_libraries

def test_existing_echo_consolidates_sats_and_preserves_private_hardlink(tmp_path):
    ref=tmp_path/'_system/reference/stock-research/ticker-aliases.json';ref.parent.mkdir(parents=True)
    ref.write_text(json.dumps({'schema_version':'stock-research-aliases.v1','aliases':{'SATS':{'ticker':'ECHO','company':'EchoStar','effective_date':'2026-06-24','issuer_cik':'1415404','excluded_cik':'1920406','source_ref':'https://ir.echostar.com/ticker-change'}}}),encoding='utf-8')
    data=tmp_path/'site/data';(data/'tickers').mkdir(parents=True)
    original=tmp_path/'original.json';original.write_text('{"ticker":"SATS","old_value":100}',encoding='utf-8')
    os.link(original,data/'tickers/SATS.json')
    (data/'tickers/ECHO.json').write_text('{"ticker":"ECHO"}',encoding='utf-8')
    (data/'core.json').write_text(json.dumps({'tickers':[{'ticker':t,'detail_shard':f'data/tickers/{t}.json'} for t in ('SATS','ECHO','TEST')]}),encoding='utf-8')
    consolidate_aliases(tmp_path,data)
    core=json.loads((data/'core.json').read_text(encoding='utf-8'))
    assert [r['ticker'] for r in core['tickers']]==['ECHO','TEST']
    assert core['ticker_aliases']=={'SATS':'ECHO'}
    assert core['summary']['ticker_count']==2
    assert json.loads((data/'tickers/SATS.json').read_text(encoding='utf-8'))['redirect_ticker']=='ECHO'
    assert json.loads(original.read_text(encoding='utf-8'))['old_value']==100
    assert legacy_libraries(tmp_path,'ECHO')[0]['ticker']=='SATS'
    consolidate_aliases(tmp_path,data)
    assert json.loads((data/'core.json').read_text(encoding='utf-8'))==core
