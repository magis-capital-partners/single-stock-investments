"""An unavailable overlap API must not lock up an otherwise valid ticker page."""
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parents[3]


def test_missing_overlap_api_settles_without_recursive_microtasks():
    script=r'''
    global.window=global;
    let lookups=0,fetches=0;
    const slot={dataset:{ticker:'MDT'},hidden:true,textContent:''};
    global.document={getElementById(){if(++lookups>10)throw Error('recursive empty response');return slot;}};
    global.fetch=async()=>{fetches++;return {ok:false,status:404};};
    require('./dashboard/overlap-viz.js');
    OverlapViz.fillTicker('MDT');
    setImmediate(()=>process.stdout.write(JSON.stringify({lookups,fetches,hidden:slot.hidden})));
    '''
    run=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert run.returncode==0,run.stderr
    result=json.loads(run.stdout)
    assert result['fetches']==1 and result['lookups']<10
    assert result['hidden'] is True
