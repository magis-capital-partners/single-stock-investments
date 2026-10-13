"""Local research API. Re-simulates the book from SQLite; it does not re-download.

The original repository served its own ``docs/`` single-page dashboard from
here. Those pages were not migrated (the hosted SSI dashboard renders the
ledger through ``dashboard/reverse-splits-viz.js``), so by default this serves
the JSON endpoints only. Point ``--docs`` at a folder of static files to keep
using the old browser UI against the new package. Binds to 127.0.0.1.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import Config, load_config
from .run_book import run_snapshot
from .strategy import decisions, evaluate, handoff, portfolio_stress, record_decision

_ALLOWED = {
    "signal",
    "horizon",
    "min_price",
    "spread_floor",
    "spread_range_fraction",
    "force_cover",
    "max_book",
    "max_names",
    "target_notional",
    "max_participation",
    "fee_annual",
    "borrow_policy",
    "listed_only",
    "require_filing_text",
    "cohorts",
    "outcomes",
    "jump_window",
}


class Handler(BaseHTTPRequestHandler):
    cfg: Config | None = None
    docs: Path | None = None

    def log_message(self, fmt: str, *args) -> None:
        print(f"[dashboard] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str, download: str | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)

    def _config(self) -> Config:
        return self.cfg or load_config()

    def _snapshot(self) -> dict:
        return json.loads((self._config().public_dir / "backtest.json").read_text(encoding="utf-8"))

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/api/strategy/decisions", "/api/strategy/export"}:
            cfg = self._config()
            if path.endswith("decisions"):
                result = {"decisions": decisions(cfg)}
            else:
                result = handoff(cfg, self._snapshot()["strategy"])
            self._send(200, json.dumps(result, allow_nan=False).encode(), "application/json",
                       "reverse_split_strategy_handoff.json" if path.endswith("export") else None)
            return
        if path.startswith("/api/"):
            self._send(404, b'{"error":"use POST /api/resimulate"}', "application/json")
            return
        if self.docs is None:
            self._send(404, b"no static files configured; use --docs", "text/plain")
            return
        if path in {"", "/"}:
            path = "/index.html"
        file_path = (self.docs / path.lstrip("/")).resolve()
        if not file_path.is_relative_to(self.docs.resolve()) or not file_path.is_file():
            self._send(404, b"not found", "text/plain")
            return
        kind = "text/html; charset=utf-8"
        if file_path.suffix == ".json":
            kind = "application/json"
        elif file_path.suffix == ".js":
            kind = "text/javascript"
        elif file_path.suffix == ".md":
            kind = "text/plain; charset=utf-8"
        self._send(200, file_path.read_bytes(), kind)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/resimulate", "/api/strategy/evaluate", "/api/strategy/decision", "/api/strategy/portfolio"}:
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            self._send(403, b'{"error":"local dashboard origin required"}', "application/json")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 100000:
            self._send(400, b'{"error":"request too large or invalid length"}', "application/json")
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("object required")
        except (ValueError, UnicodeDecodeError):
            self._send(400, b'{"error":"invalid json"}', "application/json")
            return
        if path.startswith("/api/strategy/"):
            try:
                cfg = self._config()
                if path.endswith("portfolio"):
                    result = portfolio_stress(payload)
                else:
                    snapshot = self._snapshot()
                    lead = next((r for r in snapshot["strategy"]["candidates"] if r["ticker"] == payload.get("ticker")), None)
                    if lead is None:
                        raise ValueError("Select a candidate from the frozen research queue")
                    requested_day = str(payload.get("as_of") or lead["score_as_of"])
                    if requested_day != lead["fundamental"]["as_of"]:
                        from .fundamentals import FundamentalBridge
                        lead = {**lead, "fundamental": FundamentalBridge(cfg).score(lead["ticker"], lead.get("cik"), requested_day)}
                    result = record_decision(cfg, lead, payload) if path.endswith("decision") else evaluate(lead, payload)
                self._send(200, json.dumps(result, allow_nan=False).encode(), "application/json")
            except (ValueError, TypeError, KeyError) as exc:
                self._send(400, json.dumps({"error": str(exc)}).encode(), "application/json")
            return
        overrides = {key: payload[key] for key in payload if key in _ALLOWED}
        try:
            snapshot = run_snapshot(self._config(), grid=False, **overrides)
        except Exception as exc:  # noqa: BLE001 - surfaced to the local caller
            message = json.dumps({"error": str(exc)}).encode("utf-8")
            self._send(500, message, "application/json")
            return
        self._send(200, json.dumps(snapshot).encode("utf-8"), "application/json")


def serve(port: int = 8765, docs: Path | str | None = None, cfg: Config | None = None) -> None:
    Handler.cfg = cfg or load_config()
    Handler.docs = Path(docs).resolve() if docs else None
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Research API at http://127.0.0.1:{port}" + (f" serving {Handler.docs}" if Handler.docs else " (API only)"))
    server.serve_forever()
