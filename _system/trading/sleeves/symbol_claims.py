"""Read another system's symbol claims on this shared account. Read-only: it opens files.

reverse-split ("RS", `_system/trading/rs_paper_executor` and its live successor)
shorts small-cap stock in the same IBKR account as the hub, ls-algo, spx-0dte and
etf-0dte. Its orders and executions carry orderRef prefix ``RSLIVE|``
(`classify_positions.RS_REF_PREFIXES`), but a position carries no orderRef, so the
ref cannot say which positions are RS's. Without this file an RS short falls
through every rule to Michael's residual book, and a hub BUY could net against it.

RS therefore publishes the names it holds, one file per system:

    <dir>/<system>.json                    (RS's is reverse-split.json)
    {"schema": "ib_account_symbol_claims.v1", "system": "reverse-split",
     "account": "U...", "generated_at": "<UTC ISO>",
     "claims": {"ABC": {"conid": 123, "sec_type": "STK",
                        "claimed_at": "<UTC ISO>", "release_after": null}}}

``<dir>`` is ``IB_ACCOUNT_SYMBOL_CLAIMS_DIR``, default ``/var/lib/ib-account-claims``
(on NY4, written by the RS process). The rules, all fail closed:

* A claim is active until ``release_after`` is set and in the past. Age never
  releases one: an old ``generated_at`` is still a claim.
* Positions match a claim by conid first, symbol second, and only a row of the
  claim's sec type (an option on a claimed name is not RS's position). A ticket
  matches by conid or by symbol / underlying whatever its sec type, because an
  exercised or assigned option delivers shares that net against the RS short.
* Activity is judged at a moment: now for a ticket, the session date for a Flex
  statement (`claims_moment`), so republishing yesterday's statement after RS
  released a name still attributes yesterday's short to RS.
* An unreadable file is not "no claims". When the directory is configured (the
  env var is set, or the default directory exists) and the file is missing,
  unparseable, of another schema, system or account, or has one malformed entry,
  the result is ``status="error"``: it carries the last good copy (in-process,
  and on disk under ``IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR`` or the caller's
  ``last_good_dir``) and the error. Callers refuse every ticket and quarantine
  every unproven short while it is in error (see `classify_positions`).
* Not configured at all (no env var, no default directory: CI, Windows, the
  dashboard) means RS is not deployed here, and there are no claims.

Nothing here opens a socket. The hosts that cannot read the directory -- GitHub
Actions and the Cloudflare edge -- receive the effective claims inside the
published account snapshot (``completeness.symbol_claims``), never the file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Mapping

from .classify_positions import RS_SYSTEM, norm_sym

SCHEMA = "ib_account_symbol_claims.v1"
CLAIMS_DIR_ENV = "IB_ACCOUNT_SYMBOL_CLAIMS_DIR"
LAST_GOOD_DIR_ENV = "IB_ACCOUNT_SYMBOL_CLAIMS_LAST_GOOD_DIR"
ACCOUNT_ENV = "IB_ACCOUNT_SYMBOL_CLAIMS_ACCOUNT"
DEFAULT_CLAIMS_DIR = "/var/lib/ib-account-claims"

STATUS_OK = "ok"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_ERROR = "error"

_OCC_ROOT = re.compile(r"^([A-Z0-9.]{1,6})[\s-]+\d{6}[CP]\d")
# The last good payload per claims path, for the long-running bridge. A oneshot
# job (the Flex publisher) needs the on-disk copy instead.
_LAST_GOOD: dict[str, bytes] = {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _instant(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is not a timestamp: {value!r}")
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} is not a timestamp: {value!r}") from exc
    # The contract says UTC. A naive stamp is read as UTC rather than refusing
    # the whole file over its spelling.
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def claims_moment(*, as_of: Any = None, session_date: Any = None) -> datetime:
    """The instant claim activity is judged at.

    A Flex statement is judged at the START of its New York session date, the
    most conservative reading: any claim released on or after that day still
    covers the statement. Otherwise ``as_of``; otherwise now.
    """
    if session_date:
        try:
            day = date.fromisoformat(str(session_date)[:10])
            try:
                from zoneinfo import ZoneInfo

                return datetime.combine(day, time(0, 0), ZoneInfo("America/New_York")).astimezone(timezone.utc)
            except Exception:  # pragma: no cover - no tz database on this host
                return datetime.combine(day, time(4, 0), timezone.utc)
        except ValueError:
            pass
    if as_of:
        try:
            return _instant(str(as_of), "as_of")
        except ValueError:
            pass
    return utcnow()


@dataclass(frozen=True)
class SymbolClaim:
    symbol: str
    conid: int | None
    sec_type: str
    claimed_at: datetime
    release_after: datetime | None

    def active_at(self, moment: datetime) -> bool:
        return self.release_after is None or moment < self.release_after

    def as_dict(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "conid": self.conid, "sec_type": self.sec_type}


@dataclass(frozen=True)
class SymbolClaims:
    """One system's claims as read, plus how they were read."""

    system: str
    status: str
    path: str | None = None
    account: str | None = None
    generated_at: str | None = None
    sha256: str | None = None
    claims: tuple[SymbolClaim, ...] = ()
    # "file" (read just now), "last_good" (the file failed; this is the last
    # copy that read cleanly) or "none".
    source: str = "none"
    error: str | None = None
    # When claim activity is judged. None = now, at each call.
    moment: datetime | None = field(default=None, compare=False)

    @property
    def unreadable(self) -> bool:
        """Configured but not readable now: nothing may assume "no claims"."""
        return self.status == STATUS_ERROR

    @property
    def configured(self) -> bool:
        return self.status != STATUS_NOT_CONFIGURED

    def at(self, moment: datetime | None) -> "SymbolClaims":
        return replace(self, moment=moment)

    def active(self) -> tuple[SymbolClaim, ...]:
        moment = self.moment or utcnow()
        return tuple(claim for claim in self.claims if claim.active_at(moment))

    def _reason(self, kind: str) -> str:
        return f"symbol_claim_{kind}" if self.source == "file" else f"symbol_claim_last_good_{kind}"

    def position_match(self, pos: Mapping[str, Any]) -> str | None:
        """The classifier reason when this position row is claimed, else None.

        Conid first, symbol second, and only rows of the claim's sec type.
        """
        sec = str(pos.get("secType") or pos.get("sec_type") or "STK").strip().upper()
        conid = _conid(pos.get("conid", pos.get("conId", pos.get("con_id"))))
        active = [claim for claim in self.active() if claim.sec_type == sec]
        if conid is not None and any(claim.conid == conid for claim in active):
            return self._reason("conid")
        symbol = norm_sym(pos.get("symbol") or pos.get("ticker") or pos.get("localSymbol") or pos.get("local_symbol") or "")
        if symbol and any(claim.symbol == symbol for claim in active):
            return self._reason("symbol")
        return None

    def ticket_match(self, identity: Mapping[str, Any]) -> SymbolClaim | None:
        """The active claim a ticket on this contract would trade against, else None.

        Any sec type: IBKR's ``symbol`` of an option is its underlying, and an
        exercise or assignment delivers shares that net against the claim.
        """
        conid = _conid(identity.get("conid", identity.get("conId")))
        names = {
            norm_sym(identity.get("symbol") or ""),
            norm_sym(identity.get("underlying") or identity.get("underlyingSymbol") or ""),
            _occ_root(identity.get("local_symbol") or identity.get("localSymbol")),
            norm_sym(identity.get("trading_class") or identity.get("tradingClass") or "")
            if str(identity.get("sec_type") or identity.get("secType") or "").upper() in {"OPT", "FOP"} else "",
        } - {""}
        active = self.active()
        for claim in active:
            if conid is not None and claim.conid == conid:
                return claim
        for claim in active:
            if claim.symbol in names:
                return claim
        return None

    def summary(self) -> dict[str, Any]:
        """Deterministic for one effective claim set, so a republish is idempotent.

        Carries no generated_at or file hash: RS rewrites the file without
        changing what it claims, and the snapshot must not change with it.
        """
        out: dict[str, Any] = {
            "schema": SCHEMA, "system": self.system, "status": self.status, "source": self.source,
            "claims": sorted((claim.as_dict() for claim in self.active()), key=lambda c: (c["symbol"], c["conid"] or 0)),
        }
        if self.error:
            out["error"] = self.error
        return out


def _conid(value: Any) -> int | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _occ_root(text: Any) -> str:
    match = _OCC_ROOT.match(str(text or "").strip().upper())
    return match.group(1) if match else ""


def parse_claims(raw: bytes, *, system: str, account: str | None = None) -> tuple[dict[str, Any], tuple[SymbolClaim, ...]]:
    """Validate one claims file. Any malformed entry fails the whole file."""
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("claims file is not a JSON object")
    if payload.get("schema") != SCHEMA:
        raise ValueError(f"schema is {payload.get('schema')!r}, not {SCHEMA!r}")
    if payload.get("system") != system:
        raise ValueError(f"system is {payload.get('system')!r}, not {system!r}")
    _instant(payload.get("generated_at"), "generated_at")
    file_account = payload.get("account")
    if file_account is not None and not isinstance(file_account, str):
        raise ValueError("account is not a string")
    if account and file_account and file_account.strip() != str(account).strip():
        raise ValueError(f"claims are for account {file_account!r}, not {account!r}")
    entries = payload.get("claims")
    if not isinstance(entries, dict):
        raise ValueError("claims is not an object")
    claims = []
    for name, entry in entries.items():
        symbol = norm_sym(name)
        if not symbol or not isinstance(entry, dict):
            raise ValueError(f"claim {name!r} is malformed")
        conid = _conid(entry.get("conid"))
        if conid is None:
            raise ValueError(f"claim {name!r} has no valid conid")
        sec_type = entry.get("sec_type")
        if not isinstance(sec_type, str) or not sec_type.strip():
            raise ValueError(f"claim {name!r} has no sec_type")
        release = entry.get("release_after")
        claims.append(SymbolClaim(
            symbol=symbol, conid=conid, sec_type=sec_type.strip().upper(),
            claimed_at=_instant(entry.get("claimed_at"), f"{name}.claimed_at"),
            release_after=None if release is None else _instant(release, f"{name}.release_after"),
        ))
    return payload, tuple(claims)


def claims_path(system: str = RS_SYSTEM, directory: str | Path | None = None) -> tuple[Path, bool]:
    """The file and whether this host is configured to have one."""
    explicit = directory or os.environ.get(CLAIMS_DIR_ENV)
    root = Path(explicit or DEFAULT_CLAIMS_DIR)
    return root / f"{system}.json", bool(explicit) or root.is_dir()


def _from_bytes(raw: bytes, *, system: str, account: str | None, path: Path, status: str,
                source: str, error: str | None = None) -> SymbolClaims:
    payload, claims = parse_claims(raw, system=system, account=account)
    return SymbolClaims(
        system=system, status=status, path=str(path), account=payload.get("account"),
        generated_at=payload.get("generated_at"), sha256=hashlib.sha256(raw).hexdigest(),
        claims=claims, source=source, error=error,
    )


def _last_good_file(last_good_dir: str | Path | None, system: str) -> Path | None:
    return Path(last_good_dir) / f"{system}.last-good.json" if last_good_dir else None


def _remember(path: Path, raw: bytes, last_good: Path | None) -> None:
    _LAST_GOOD[str(path)] = raw
    if last_good is None:
        return
    try:
        if last_good.is_file() and last_good.read_bytes() == raw:
            return
        last_good.parent.mkdir(parents=True, exist_ok=True)
        temporary = last_good.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(last_good)
    except OSError:
        # The in-process copy still stands; a read-only cache is not a reason
        # to reject a claims file that read cleanly.
        pass


def load_symbol_claims(
    system: str = RS_SYSTEM,
    *,
    directory: str | Path | None = None,
    last_good_dir: str | Path | None = None,
    account: str | None = None,
) -> SymbolClaims:
    """Read ``<dir>/<system>.json``; on failure, the last good copy and the error.

    ``account`` (default ``IB_ACCOUNT_SYMBOL_CLAIMS_ACCOUNT``, else
    ``IBKR_ACCOUNT_ID``) must match the file's account when both are known.
    """
    path, configured = claims_path(system, directory)
    if not configured:
        return SymbolClaims(system=system, status=STATUS_NOT_CONFIGURED, path=str(path))
    account = account or os.environ.get(ACCOUNT_ENV) or os.environ.get("IBKR_ACCOUNT_ID") or None
    last_good = _last_good_file(last_good_dir or os.environ.get(LAST_GOOD_DIR_ENV), system)
    try:
        raw = path.read_bytes()
        result = _from_bytes(raw, system=system, account=account, path=path, status=STATUS_OK, source="file")
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        error = f"{path}: {type(exc).__name__}: {exc}"
        for candidate in (_LAST_GOOD.get(str(path)), _read_quietly(last_good)):
            if candidate is None:
                continue
            try:
                return _from_bytes(candidate, system=system, account=account, path=path,
                                   status=STATUS_ERROR, source="last_good", error=error)
            except (ValueError, UnicodeDecodeError):
                continue
        return SymbolClaims(system=system, status=STATUS_ERROR, path=str(path), error=error)
    _remember(path, raw, last_good)
    return result


def _read_quietly(path: Path | None) -> bytes | None:
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def claims_from_summary(summary: Mapping[str, Any] | None, *, system: str = RS_SYSTEM) -> SymbolClaims:
    """Rebuild claims from a snapshot's ``completeness.symbol_claims[system]``.

    For a reader that has the published snapshot but not the file. The summary
    lists only the claims active at the statement's moment, so they stay active.
    """
    if not summary:
        return SymbolClaims(system=system, status=STATUS_NOT_CONFIGURED)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    claims = tuple(
        SymbolClaim(symbol=norm_sym(row.get("symbol") or ""), conid=_conid(row.get("conid")),
                    sec_type=str(row.get("sec_type") or "STK").upper(), claimed_at=epoch, release_after=None)
        for row in summary.get("claims") or [] if norm_sym(row.get("symbol") or "")
    )
    return SymbolClaims(system=system, status=str(summary.get("status") or STATUS_ERROR),
                        claims=claims, source=str(summary.get("source") or "none"), error=summary.get("error"))


def claim_refusal(identity: Mapping[str, Any], claims: SymbolClaims | None, *, who: str = "The hub") -> str | None:
    """Why ``who`` must refuse an order on this contract, or None.

    Any side and any route, including a reduce-only cover: the reduce-only check
    reads the account-wide position, so a BUY passes against RS's short and nets
    it. While the claims cannot be read, nothing is proven unclaimed.
    """
    if claims is None or not claims.configured:
        return None
    if claims.unreadable:
        return (
            f"reverse-split symbol claims are unreadable ({claims.error}); {who} cannot prove this contract is "
            "not reverse-split's stock short and orders nothing until they are readable."
        )
    claim = claims.ticket_match(identity)
    if claim is None:
        return None
    return (
        f"{claim.symbol} is claimed by reverse-split (RSLIVE| small-cap stock shorts, conId {claim.conid}). "
        f"{who} never orders it: any order would net against reverse-split's position."
    )
