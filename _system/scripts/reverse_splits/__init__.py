"""Reverse-split short research: EDGAR discovery, nominal-price book, RSI-1.0 process.

Migrated from the ``rsdb`` repository under the proposal
``_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md`` (Phase 3).
The committed truth is the JSONL ledger under ``_system/data/reverse_splits/``;
SQLite, raw EDGAR/price caches and reports are local build artifacts under
``_system/data/reverse_splits/local/`` (ignored). ``export_ledger`` and
``import_ledger`` round-trip the two.

No module in this package opens a broker connection. Borrow evidence enters
only through the Client Portal availability CSV importer in ``borrow.py``.
"""

__version__ = "0.2.0"
