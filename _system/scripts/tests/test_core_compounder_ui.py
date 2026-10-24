"""Exercise the existing dashboard renderer with the new research view."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def test_core_compounder_renderer_shows_gaps_math_and_escaped_sources():
    html = (ROOT / "dashboard/index.html").read_text(encoding="utf-8")
    start = html.index("function renderCoreCompounder(t)")
    end = html.index("function renderPricingAnalysis(t)", start)
    renderer = html[start:end]
    script = r'''
const assert = require('node:assert/strict');
const escapeHtml = value => String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
RENDERER
assert.equal(renderCoreCompounder({}), '');
const view = {model_level:'evidence_blocked', driver_to_fcf:'<img src=x>',
  tci_return_bridge:{model_as_of:'2026-06-03',status:'diagnostic',scenarios:{base:{exact_irr_pct:11.194752,fcf_yield_pct:4.51217,per_share_fcf_growth_pct:6.4247,multiple_change_pct:-.1049,reconciliation_gap_pp:.3628}},gaps:['GAP: funded reinvestment']},
  kpi_coverage:[{kpi_id:'adv_total',value:31800000,unit:'contracts_per_day',period:'2026-09',status:'current'}],
  what_missing:[{text:'<script>bad()</script>',source:{ref:'CME/research/valuation.json',claim_type:'opinion',as_of:'2026-06-03'}}]};
const rendered = renderCoreCompounder({compounder_monitor:view});
assert(rendered.includes('11.19%'));
assert(rendered.includes('GAP: funded reinvestment'));
assert(rendered.includes('31800000'));
assert(rendered.includes('&lt;img'));
assert(!rendered.includes('<script>bad'));
assert(rendered.includes('opinion'));
'''.replace('RENDERER', renderer)
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
