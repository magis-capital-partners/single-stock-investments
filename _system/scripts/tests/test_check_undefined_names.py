"""check_undefined_names.py: F821 and parse errors both fail, with no allowance."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_undefined_names.py"
spec = importlib.util.spec_from_file_location("check_undefined_names", SCRIPT)
cun = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cun
spec.loader.exec_module(cun)


def diag(code, filename, row, message):
    return {"code": code, "filename": filename, "location": {"row": row, "column": 1}, "message": message}


def fake_ruff(monkeypatch, diagnostics):
    def fake_run(cmd, capture_output, text, check):
        assert cmd[1:4] == ["-m", "ruff", "check"] and "--exit-zero" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(diagnostics), stderr="")

    monkeypatch.setattr(cun.subprocess, "run", fake_run)


def test_a_clean_tree_passes(monkeypatch, capsys):
    fake_ruff(monkeypatch, [])
    assert cun.main(["_system/scripts"]) == 0
    assert "OK: no undefined names" in capsys.readouterr().out


def test_an_undefined_name_fails(monkeypatch, capsys):
    fake_ruff(monkeypatch, [diag("F821", "_system/scripts/two_phase_watch.py", 1008, "Undefined name `fetch_ir`")])
    assert cun.main([]) == 1
    out = capsys.readouterr().out
    assert "_system/scripts/two_phase_watch.py:1008:1: F821 Undefined name `fetch_ir`" in out
    assert "::error file=_system/scripts/two_phase_watch.py,line=1008::" in out


def test_an_unparseable_file_fails_even_with_no_f821(monkeypatch, capsys):
    # A syntax error hides the file's undefined names; ruff reports only this.
    fake_ruff(monkeypatch, [diag("invalid-syntax", "_system\\scripts\\broken.py", 1, "Expected `)`, found newline")])
    assert cun.main([]) == 1
    out = capsys.readouterr().out
    assert "_system/scripts/broken.py:1:1: invalid-syntax Expected `)`" in out
    assert "0 undefined name(s), 1 parse error(s)" in out


def test_ruff_not_running_is_an_error(monkeypatch):
    def failing(cmd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No module named ruff")

    monkeypatch.setattr(cun.subprocess, "run", failing)
    assert cun.main([]) == 2


def test_against_real_ruff(tmp_path):
    pytest.importorskip("ruff")
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "undef.py").write_text("def g():\n    return undefined_b\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def f(:\n    return undefined_a\n", encoding="utf-8")
    undefined, unparseable = cun.classify(cun.run_ruff([str(tmp_path)]))
    assert [d["message"] for d in undefined] == ["Undefined name `undefined_b`"]
    # undefined_a is hidden behind the parse error: only the parse error shows.
    assert unparseable and all("broken.py" in d["filename"] for d in unparseable)
