#!/usr/bin/env python3
"""Offline tests for thematic context layer (fetch_theme_panel + apply_context_overlay)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import apply_context_overlay as overlay  # noqa: E402
import fetch_theme_panel as panel  # noqa: E402


def test_yoy_basic():
    rows = [("2024-06-01", 100.0), ("2025-01-01", 110.0), ("2025-06-01", 120.0)]
    latest, prior, pct = panel.yoy(rows)
    assert latest == 120.0
    assert prior == 100.0
    assert pct == 20.0


def test_yoy_empty():
    assert panel.yoy([]) == (None, None, None)


def test_direction():
    assert panel.direction(20.0) == "up"
    assert panel.direction(-5.0) == "down"
    assert panel.direction(0.2) == "flat"
    assert panel.direction(None) == "flat"


def test_merge_keeps_history():
    """process_series must not drop older cached observations when new data arrives."""
    with tempfile.TemporaryDirectory() as tmp:
        old_dir = panel.THEMES_DIR
        panel.THEMES_DIR = Path(tmp)
        try:
            csv_path = panel.THEMES_DIR / "demo_series.csv"
            panel.write_csv(csv_path, [("2024-06-01", 50.0), ("2025-06-01", 60.0)])
            # Offline run reuses cache; history preserved.
            res = panel.process_series({"id": "demo_series", "source": "fred", "fred_id": "X"}, offline=True)
            assert res["latest"] == 60.0
            rows = panel.read_cached_csv(csv_path)
            assert ("2024-06-01", 50.0) in rows
        finally:
            panel.THEMES_DIR = old_dir


def test_hyperscaler_capex_from_repo():
    """Capex series is derived from in-repo ai_overlay, never fabricated."""
    rows, err, contributors = panel.hyperscaler_capex_guide()
    # In this repo GOOGL et al. carry ai_overlay capex; expect a positive total.
    if rows:
        assert err is None
        assert rows[0][1] > 0
        assert contributors


def test_overlay_preserves_human_base_flag():
    manifest = {
        "as_of": "2026-06-06",
        "themes": {
            "ai_power_land": {
                "label": "AI power land",
                "series": {
                    "wti_crude": {"label": "WTI", "latest": 70.0, "as_of": "2026-06-05", "yoy_pct": 5.0, "direction": "up", "good_for": "permian_cashflow", "source": "fred:DCOILWTICO", "stale": False},
                },
            }
        },
    }
    existing = {"themes": [{"theme_id": "ai_power_land", "indicators": [{"id": "wti_crude", "in_base_irr": True}]}]}
    built = overlay.build_overlay("TPL", ["ai_power_land"], manifest, existing)
    ind = built["themes"][0]["indicators"][0]
    assert ind["in_base_irr"] is True  # human flag preserved
    assert "Lawrence base IRR" in built["disclaimer"]


def test_overlay_defaults_context_only():
    manifest = {
        "as_of": "2026-06-06",
        "themes": {"ai_power_land": {"label": "x", "series": {"wti_crude": {"label": "WTI", "latest": 70.0, "as_of": "2026-06-05", "yoy_pct": 5.0, "direction": "up", "source": "fred:DCOILWTICO", "stale": False}}}},
    }
    built = overlay.build_overlay("LB", ["ai_power_land"], manifest, {})
    assert built["themes"][0]["indicators"][0]["in_base_irr"] is False


def test_sealed_model_context_refresh_does_not_edit_model(tmp_path, monkeypatch):
    monkeypatch.setattr(overlay, 'ROOT', tmp_path)
    research=tmp_path/'SEALED/research';research.mkdir(parents=True)
    model={'underwriting':{'contract_hash':'frozen'},'inputs':{'source':'sealed evidence'}}
    path=research/'valuation.json';path.write_text(json.dumps(model),encoding='utf-8')
    before=path.read_bytes()
    manifest={'as_of':overlay.TODAY,'themes':{'context':{'label':'Context','series':{'signal':{'latest':1,'source':'verified panel'}}}}}
    overlay.apply_ticker('SEALED',['context'],manifest)
    assert path.read_bytes()==before
    context=json.loads((research/'context_overlay.json').read_text(encoding='utf-8'))
    assert context['themes'][0]['indicators'][0]['source']=='verified panel'


def test_sealed_inline_context_is_moved_only_with_exact_builder_binding(tmp_path, monkeypatch):
    from underwriting_contract import digest
    monkeypatch.setattr(overlay, 'ROOT', tmp_path)
    research=tmp_path/'SEALED/research';research.mkdir(parents=True)
    sealed={'underwriting':{'contract_hash':'frozen'},'inputs':{'source':'sealed evidence'}}
    prior={'themes':[{'indicators':[{'id':'signal','in_base_irr':True}]}]}
    path=research/'valuation.json';path.write_text(json.dumps({**sealed,'context_overlay':prior}),encoding='utf-8')
    receipt={'stages':{'builder':{'provider':'deterministic','status':'finished','model_hash':digest(sealed)}}}
    (research/'underwriting_receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
    manifest={'as_of':overlay.TODAY,'themes':{'context':{'label':'Context','series':{'signal':{'latest':1}}}}}
    overlay.apply_ticker('SEALED',['context'],manifest)
    assert json.loads(path.read_text(encoding='utf-8'))==sealed
    assert json.loads((research/'context_overlay.json').read_text(encoding='utf-8'))['themes'][0]['indicators'][0]['in_base_irr'] is True
    # A different sealed input is a real replay failure; never "repair" it by
    # dropping annotations or changing the compiler receipt.
    changed={**sealed,'inputs':{'source':'unexpected change'},'context_overlay':prior}
    path.write_text(json.dumps(changed),encoding='utf-8');before=path.read_bytes()
    overlay.apply_ticker('SEALED',['context'],manifest)
    assert path.read_bytes()==before


def test_sealed_sidecar_context_remains_reportable_and_linted(tmp_path, monkeypatch):
    import refresh_deep_dive_v2 as report
    import lint_context_overlay as lint
    monkeypatch.setattr(overlay,'ROOT',tmp_path)
    monkeypatch.setattr(report,'ROOT',tmp_path)
    monkeypatch.setattr(lint,'ROOT',tmp_path)
    monkeypatch.setattr(lint,'THEMES_MANIFEST',tmp_path/'absent-panel.json')
    research=tmp_path/'SEALED/research';research.mkdir(parents=True)
    path=research/'valuation.json'
    path.write_text(json.dumps({'underwriting':{'contract_hash':'frozen'}}),encoding='utf-8')
    before=path.read_bytes()
    manifest={'as_of':overlay.TODAY,'themes':{'context':{'label':'Context','series':{'signal':{'latest':1,'source':'verified panel'}}}}}
    overlay.apply_ticker('SEALED',['context'],manifest)
    expected=json.loads((research/'context_overlay.json').read_text(encoding='utf-8'))
    assert report.load_valuation('SEALED')['context_overlay']==expected
    assert lint.lint_valuation_overlay('SEALED')==[]
    assert path.read_bytes()==before


def test_theme_map_loads():
    tmap = overlay.theme_map()
    assert "TPL" in tmap
    assert "AZLCZ" in tmap
    assert "ai_power_land" in tmap["TPL"]
    assert "ai_power_land" in tmap["AZLCZ"]
    assert "macro_regime" in tmap["TPL"]


def test_wti_yahoo_fallback():
    rows, err = panel.fetch_yahoo_daily("CL=F", days=30)
    assert rows or err
    if rows:
        assert rows[-1][1] > 0


def _counting_urlopen(monkeypatch, behaviour):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)
        return behaviour(req)

    monkeypatch.setattr(panel.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    panel._reset_run_state()
    return calls


class _Resp:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body


FAKE_KEY = "abcdef0123456789abcdef0123456789"
FREDGRAPH_BODY = b"observation_date,X\n2026-10-01,1.5\n2026-11-01,2.0\n"
API_BODY = json.dumps(
    {
        "observations": [
            {"realtime_start": "2026-11-16", "date": "2026-09-01", "value": "."},
            {"realtime_start": "2026-11-16", "date": "2026-10-01", "value": "1.5"},
            {"realtime_start": "2026-11-16", "date": "2026-11-01", "value": "2.0"},
        ]
    }
).encode()


def _host(url: str) -> str:
    return panel.urlparse(url).hostname or ""


def test_fred_api_used_when_key_set(monkeypatch):
    """With FRED_API_KEY the official API is called and parsed into the fredgraph row format."""
    calls = _counting_urlopen(monkeypatch, lambda req: _Resp(API_BODY))
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    rows, err = panel.fetch_fred("HOUST")
    assert (rows, err) == ([("2026-10-01", 1.5), ("2026-11-01", 2.0)], None)
    assert len(calls) == 1
    q = panel.urllib.parse.parse_qs(panel.urlparse(calls[0]).query)
    assert _host(calls[0]) == "api.stlouisfed.org"
    assert q == {"series_id": ["HOUST"], "api_key": [FAKE_KEY], "file_type": ["json"]}
    panel._reset_run_state()


def test_fred_api_and_fredgraph_rows_match(monkeypatch):
    """Same series, either source: identical rows, so cached CSVs merge cleanly."""
    _counting_urlopen(monkeypatch, lambda req: _Resp(FREDGRAPH_BODY))
    via_csv = panel.fetch_fred("HOUST")
    panel._reset_run_state()
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    monkeypatch.setattr(panel.urllib.request, "urlopen", lambda req, timeout=None: _Resp(API_BODY))
    assert panel.fetch_fred("HOUST") == via_csv
    panel._reset_run_state()


def test_no_key_keeps_fredgraph_only(monkeypatch):
    """Without FRED_API_KEY nothing changes: fredgraph only, never the API host."""
    calls = _counting_urlopen(monkeypatch, lambda req: _Resp(FREDGRAPH_BODY))
    assert panel.fetch_fred("HOUST") == ([("2026-10-01", 1.5), ("2026-11-01", 2.0)], None)
    assert [_host(u) for u in calls] == ["fred.stlouisfed.org"]
    panel._reset_run_state()


def test_no_key_unreachable_fredgraph_still_skips_host(monkeypatch):
    def stall(_req):
        raise TimeoutError("timed out")

    calls = _counting_urlopen(monkeypatch, stall)
    assert panel.fetch_fred("HOUST") == ([], "network")
    assert panel.fetch_fred("PERMIT") == ([], "host_unreachable")
    assert len(calls) == 2
    panel._reset_run_state()


def test_fred_api_http_error_falls_back_to_fredgraph(monkeypatch):
    def api_fails(req):
        if _host(req.full_url) == "api.stlouisfed.org":
            raise panel.urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
        return _Resp(FREDGRAPH_BODY)

    calls = _counting_urlopen(monkeypatch, api_fails)
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    assert panel.fetch_fred("HOUST") == ([("2026-10-01", 1.5), ("2026-11-01", 2.0)], None)
    assert [_host(u) for u in calls] == ["api.stlouisfed.org"] * 2 + ["fred.stlouisfed.org"]
    assert not panel._UNREACHABLE_HOSTS
    panel._reset_run_state()


def test_fred_api_bad_json_falls_back(monkeypatch):
    def api_garbage(req):
        if _host(req.full_url) == "api.stlouisfed.org":
            return _Resp(b"<html>maintenance</html>")
        return _Resp(FREDGRAPH_BODY)

    _counting_urlopen(monkeypatch, api_garbage)
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    assert panel.fetch_fred("HOUST")[0] == [("2026-10-01", 1.5), ("2026-11-01", 2.0)]
    panel._reset_run_state()


def test_api_and_fredgraph_down_reuse_cache_with_host_unreachable(monkeypatch, tmp_path):
    """Both FRED hosts stall: one try each, then cached history marked host_unreachable."""
    def stall(_req):
        raise TimeoutError("timed out")

    calls = _counting_urlopen(monkeypatch, stall)
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    monkeypatch.setattr(panel, "THEMES_DIR", tmp_path)
    panel.write_csv(tmp_path / "old.csv", [("2020-01-01", 1.0)])
    panel.fetch_fred("FIRST")
    assert len(calls) == 4  # two retries per host, once per run
    res = panel.process_series({"id": "old", "source": "fred", "fred_id": "OLD"}, offline=False)
    assert len(calls) == 4
    assert res["latest"] == 1.0
    assert res["error"] == "host_unreachable"
    assert res["stale"] is True
    panel._reset_run_state()


def test_api_key_redacted_from_logs(monkeypatch, capsys):
    """An error that echoes the request URL must not print the key."""
    def leaky(req):
        if _host(req.full_url) == "api.stlouisfed.org":
            raise ValueError(f"cannot fetch {req.full_url}")
        return _Resp(FREDGRAPH_BODY)

    _counting_urlopen(monkeypatch, leaky)
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    rows, err = panel.fetch_fred("HOUST")
    out = capsys.readouterr().out
    assert rows and err is None
    assert FAKE_KEY not in out
    assert "api_key=REDACTED" in out
    assert "falling back to fredgraph" in out
    panel._reset_run_state()


def test_redact_handles_bare_key(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    assert FAKE_KEY not in panel._redact(f"token {FAKE_KEY} leaked")
    assert panel._redact("x?api_key=zzz&file_type=json") == "x?api_key=REDACTED&file_type=json"


def test_fred_api_throttled_under_rate_limit(monkeypatch):
    sleeps = []
    _counting_urlopen(monkeypatch, lambda req: _Resp(API_BODY))
    monkeypatch.setattr("time.sleep", sleeps.append)
    monkeypatch.setenv("FRED_API_KEY", FAKE_KEY)
    for fid in ("A", "B", "C"):
        panel.fetch_fred(fid)
    assert len(sleeps) == 2
    assert all(0 < s <= panel.FRED_API_MIN_INTERVAL_S for s in sleeps)
    panel._reset_run_state()


def test_stalled_host_is_tried_once_per_run(monkeypatch):
    """A host that times out (FRED from GitHub runners) must not cost a full timeout per series."""
    def stall(_req):
        raise TimeoutError("timed out")

    calls = _counting_urlopen(monkeypatch, stall)
    first = panel.fetch_fred("HOUST")
    later = [panel.fetch_fred(fid) for fid in ("PERMIT", "TTLCONS", "WPU1321")]
    assert first == ([], "network")
    assert all(res == ([], "host_unreachable") for res in later)
    assert len(calls) == 2  # retries for the first series only
    panel._reset_run_state()


def test_http_error_does_not_mark_host_unreachable(monkeypatch):
    """A server that answers (404/429) is reachable; other series still get fetched."""
    def not_found(req):
        raise panel.urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)

    calls = _counting_urlopen(monkeypatch, not_found)
    panel.fetch_fred("BAD1")
    panel.fetch_fred("BAD2")
    assert not panel._UNREACHABLE_HOSTS
    assert len(calls) == 4
    panel._reset_run_state()


def test_repeated_series_fetched_once(monkeypatch):
    """Series shared across themes (DGS10, HOUST, ^VIX) hit the source once per run."""
    class Resp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

    def ok(_req):
        return Resp(b"observation_date,X\n2026-10-01,1.5\n2026-11-01,2.0\n")

    calls = _counting_urlopen(monkeypatch, ok)
    a = panel.fetch_fred("HOUST")
    b = panel.fetch_fred("HOUST")
    assert a == b == ([("2026-10-01", 1.5), ("2026-11-01", 2.0)], None)
    a[0].clear()
    assert panel.fetch_fred("HOUST")[0]  # callers cannot corrupt the memo
    assert len(calls) == 1
    panel._reset_run_state()


def test_unreachable_series_keeps_cached_history_and_staleness(monkeypatch, tmp_path):
    """Skipping a dead host reuses the cache; the staleness gate is computed as before."""
    def stall(_req):
        raise TimeoutError("timed out")

    _counting_urlopen(monkeypatch, stall)
    monkeypatch.setattr(panel, "THEMES_DIR", tmp_path)
    panel.write_csv(tmp_path / "old.csv", [("2020-01-01", 1.0)])
    panel.fetch_fred("FIRST")
    res = panel.process_series({"id": "old", "source": "fred", "fred_id": "OLD"}, offline=False)
    assert res["latest"] == 1.0
    assert res["error"] == "host_unreachable"
    assert res["stale"] is True
    panel._reset_run_state()


def test_theme_map_wildcard_macro():
    tmap = overlay.theme_map()
    assert "macro_regime" in tmap.get("CME", [])


if __name__ == "__main__":
    test_yoy_basic()
    test_yoy_empty()
    test_direction()
    test_merge_keeps_history()
    test_hyperscaler_capex_from_repo()
    test_overlay_preserves_human_base_flag()
    test_overlay_defaults_context_only()
    test_theme_map_loads()
    print("OK test_theme_panel")
