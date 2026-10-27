"""Bounded Flex HTTPS retrieval. Never imports a TWS/Gateway client."""
from __future__ import annotations

import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .realized import read_report

BASE = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
PENDING = {"1001", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1018", "1019", "1021"}


@contextmanager
def report_lock(root: Path):
    """A process lock, not a socket. Kernel releases it even after a crash."""
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / "report.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            if handle.tell() == 0:
                handle.write(b"0"); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def fetch_report(*, query_id: str, account: str, start: str, through: str, destination: Path,
                 token: str | None = None, timeout: int = 240) -> Path:
    """Explicit date windows, shared pacing, atomic file promotion, redacted errors.

    Call only after the existing primary report fetch has finished. Credentials
    come from the established environment; no token rotation or new session.
    """
    first, last = date.fromisoformat(start), date.fromisoformat(through)
    if last < first or (last - first).days >= 365:
        raise ValueError("Flex requests require an inclusive interval of at most 365 days")
    if not str(query_id).isdigit():
        raise ValueError("a numeric supplemental Flex query ID is required")
    token = token or os.environ.get("IBKR_FLEX_TOKEN", "")
    if not token:
        raise ValueError("IBKR_FLEX_TOKEN is not configured")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".pending")
    deadline, last_request = time.monotonic() + timeout, 0.0

    def request(operation: str, query: str, extra: dict | None = None) -> Path:
        nonlocal last_request
        delay = max(0.0, 7.0 - (time.monotonic() - last_request))
        if time.monotonic() + delay > deadline:
            raise TimeoutError("Flex report generation timed out; existing files preserved")
        time.sleep(delay)
        params = {"t": token, "q": query, "v": "3", **(extra or {})}
        req = urllib.request.Request(BASE + "/" + operation + "?" + urllib.parse.urlencode(params),
                                     headers={"User-Agent": "MagisSleeveReports/1.0"})
        last_request = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=min(30, max(1, deadline - time.monotonic()))) as response, temporary.open("wb") as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > 200_000_000:
                        raise ValueError("Flex report exceeds the private import size limit")
                    output.write(block)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Flex HTTPS request failed with status {exc.code}; credentials redacted") from None
        except urllib.error.URLError:
            raise RuntimeError("Flex HTTPS request failed; credentials redacted") from None
        return temporary

    def envelope(path: Path):
        with path.open("rb") as source:
            head = source.read(65536)
        if b"<FlexStatementResponse" not in head:
            return None
        root = ET.fromstring(head)
        return root.findtext("Status"), root.findtext("ErrorCode"), root.findtext("ReferenceCode")

    try:
        reference = None
        while time.monotonic() < deadline:
            request("GetStatement" if reference else "SendRequest", reference or query_id,
                    None if reference else {"fd": first.strftime("%Y%m%d"), "td": last.strftime("%Y%m%d")})
            status = envelope(temporary)
            if status is None:
                parsed = read_report(temporary, account=account)
                if parsed["from"] != start or parsed["through"] != through:
                    raise ValueError("Flex returned a different period; refusing to mark requested coverage complete")
                temporary.replace(destination)
                return destination
            state, code, new_reference = status
            if state == "Success" and new_reference:
                reference = new_reference
            elif code not in PENDING:
                raise RuntimeError(f"Flex report error {code or 'unknown'}; check report configuration/token without changing broker sessions")
        raise TimeoutError("Flex report generation timed out; existing files preserved")
    finally:
        temporary.unlink(missing_ok=True)
