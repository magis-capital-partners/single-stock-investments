"""Write the committed Drew sleeve, and Michael's January 3905.T lot, into D1 SQL.

The live Drew tab reads sleeve_positions. The static JSON is not served.
This statement replaces Drew's rows and only the 3905.T row on Michael.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DREW = ROOT / "dashboard" / "data" / "sleeves_drew.json"
MICHAEL = ROOT / "dashboard" / "data" / "sleeves_michael.json"


def q(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(float(value)) if isinstance(value, float) else str(value)
    return "'" + str(value).replace("'", "''") + "'"


def position_sql(owner: str, pos: dict, as_of: str) -> str:
    key = pos.get("local_symbol") or pos.get("ticker")
    sec = str(pos.get("secType") or pos.get("sec_type") or "STK").upper()
    return (
        "INSERT INTO sleeve_positions ("
        "owner, position_key, ticker, qty, mark, market_value, sec_type, classifier_reason, "
        "conid, local_symbol, expiry, strike, right_code, multiplier, synced_at"
        ") VALUES ("
        f"{q(owner)}, {q(key)}, {q(pos.get('ticker'))}, {q(pos.get('qty'))}, {q(pos.get('mark'))}, "
        f"{q(pos.get('market_value'))}, {q(sec)}, {q(pos.get('classifier_reason') or 'residual')}, "
        f"{q(pos.get('conid'))}, {q(pos.get('local_symbol') or key)}, {q(pos.get('expiry'))}, "
        f"{q(pos.get('strike'))}, {q(pos.get('right') or pos.get('right_code'))}, {q(pos.get('multiplier'))}, {q(as_of)}"
        ");"
    )


def idea_sql(owner: str, pos: dict, as_of: str) -> str:
    side = "BUY" if float(pos.get("qty") or 0) >= 0 else "SELL"
    return (
        "INSERT INTO sleeve_ideas (owner, ticker, side, status, entry_price, shares, cost_usd, updated_at) "
        f"VALUES ({q(owner)}, {q(pos.get('ticker'))}, {q(side)}, 'filled', {q(pos.get('entry_price'))}, "
        f"{q(pos.get('qty'))}, {q(pos.get('cost_usd'))}, {q(as_of)}) "
        "ON CONFLICT(owner, ticker) DO UPDATE SET "
        "side=excluded.side, status='filled', entry_price=excluded.entry_price, "
        "shares=excluded.shares, cost_usd=excluded.cost_usd, updated_at=excluded.updated_at;"
    )


def build_sql() -> str:
    drew = json.loads(DREW.read_text(encoding="utf-8"))
    michael = json.loads(MICHAEL.read_text(encoding="utf-8"))
    as_of = str(drew.get("as_of") or "")
    header = drew.get("header") or {}
    lines = [
        "DELETE FROM sleeve_positions WHERE owner='drew';",
        (
            "INSERT INTO sleeve_config (owner, equity_usd, extra_margin_usd, as_of, payload_json, updated_at) "
            f"VALUES ('drew', {q(header.get('equity_usd'))}, {q(header.get('extra_margin_usd') or 0)}, {q(as_of)}, "
            f"{q(json.dumps({'equity_usd': header.get('equity_usd'), 'extra_margin_usd': header.get('extra_margin_usd')}))}, {q(as_of)}) "
            "ON CONFLICT(owner) DO UPDATE SET equity_usd=excluded.equity_usd, "
            "extra_margin_usd=excluded.extra_margin_usd, as_of=excluded.as_of, "
            "payload_json=excluded.payload_json, updated_at=excluded.updated_at;"
        ),
    ]
    for pos in drew.get("positions") or []:
        lines.append(position_sql("drew", pos, as_of))
        if pos.get("cost_usd") is not None:
            lines.append(idea_sql("drew", pos, as_of))
    january = next((pos for pos in michael.get("positions") or [] if pos.get("ticker") == "3905.T"), None)
    if january is None:
        raise SystemExit("Michael book is missing the January 3905.T lot")
    lines.append("DELETE FROM sleeve_positions WHERE owner='michael' AND ticker='3905.T';")
    lines.append(position_sql("michael", january, as_of))
    lines.append(idea_sql("michael", january, as_of))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sql = build_sql()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sql, encoding="utf-8")


if __name__ == "__main__":
    main()
