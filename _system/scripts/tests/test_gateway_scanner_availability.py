"""A missing optional code scanner must never look like a successful scan."""
from __future__ import annotations

import builtins
import sys

import pytest

from _system.scripts import check_ib_gateway_registry as checker

SCANNER = "_system.scripts.scan_ib_gateway_clients"


def block_scanner(monkeypatch, missing_name):
    original_import = builtins.__import__

    def import_with_missing_scanner(name, *args, **kwargs):
        if name == SCANNER:
            raise ModuleNotFoundError(f"No module named '{missing_name}'", name=missing_name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_with_missing_scanner)


def test_missing_scanner_returns_failure_without_claiming_scan_success(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["checker", "--skip-mirrors", "--scan-ssi"])
    block_scanner(monkeypatch, SCANNER)
    assert checker.main() == 1
    captured = capsys.readouterr()
    assert "no SSI code scan was performed" in captured.err
    assert "scan_ib_gateway_clients.py is absent" in captured.err
    assert "OK SSI Gateway scanner" not in captured.out


def test_missing_scanner_dependency_is_not_misreported_as_absent_scanner(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["checker", "--skip-mirrors", "--scan-ssi"])
    block_scanner(monkeypatch, "scanner_dependency")
    with pytest.raises(ModuleNotFoundError) as caught:
        checker.main()
    assert caught.value.name == "scanner_dependency"


def test_registry_only_validation_does_not_need_the_scanner(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["checker", "--skip-mirrors"])
    block_scanner(monkeypatch, SCANNER)
    assert checker.main() == 0
    assert "OK 2026-09-09.1 sha256:" in capsys.readouterr().out
