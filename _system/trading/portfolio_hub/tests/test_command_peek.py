"""The bridge peeks before it claims, so an idle desk writes nothing to D1.

Each claim route reserves a nonce row before it looks for work. The loop used to
call both claim routes every 15s tick, so an idle desk wrote two rows every tick
(~34k billed row writes a day, plus ~10k more when retention deleted them). These
tests pin the new contract: claims happen only for a queue the peek says has
claimable work, and every way the peek can be missing or broken falls back to
the old claim-both behaviour rather than stranding a ticket.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import urllib.error

import pytest

from _system.trading.portfolio_hub import command_poller
from _system.trading.portfolio_hub.command_poller import (
    IDLE_POLL_SECONDS,
    PEEK_PATH,
    PEEK_RETRY_SECONDS,
    ChannelConfig,
    OrderCommandChannel,
    OrderCommandLoop,
    PeekUnavailable,
)
from _system.trading.portfolio_hub.paper import PaperOrderBroker


def _quotes(conid):
    return {"bid": "5.10", "ask": "5.20", "min_tick": "0.01", "multiplier": "100"}


class _Service:
    def __init__(self, broker):
        self.broker = broker


class _PeekingChannel:
    """Counts signed calls. Each claim is one nonce row at the edge; a peek is none."""

    def __init__(self, *, peek=None, requests=None, lookups=None):
        self._peek = peek if peek is not None else {"order_requests": 0, "contract_lookups": 0}
        self._requests, self._lookups = requests or [], lookups or []
        self.calls: list[str] = []
        self.published, self.lookup_published = [], []

    def peek(self):
        self.calls.append("peek")
        if isinstance(self._peek, BaseException):
            raise self._peek
        return dict(self._peek)

    def claim(self):
        self.calls.append("claim")
        return self._requests

    def claim_lookups(self):
        self.calls.append("claim_lookups")
        return self._lookups

    def publish(self, request_id, update):
        self.published.append((request_id, update))

    def publish_lookup(self, lookup_id, update):
        self.lookup_published.append((lookup_id, update))


class _Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


def _loop(channel, clock=None):
    return OrderCommandLoop(_Service(PaperOrderBroker(_quotes)), channel, account_alias="U123",
                            clock=clock or _Clock())


def _nonce_writes(channel):
    # Each claim route reserves exactly one nonce; the peek reserves none.
    return sum(1 for call in channel.calls if call in {"claim", "claim_lookups"})


def test_an_idle_desk_makes_no_claim_and_so_writes_no_nonce():
    channel = _PeekingChannel()
    loop = _loop(channel)
    for _ in range(100):
        assert loop.tick() is False
    assert _nonce_writes(channel) == 0, "100 idle ticks must reserve zero nonces"
    assert channel.calls == ["peek"] * 100


def test_only_the_queue_with_claimable_work_is_claimed():
    orders_only = _PeekingChannel(peek={"order_requests": 1, "contract_lookups": 0})
    _loop(orders_only).tick()
    assert orders_only.calls == ["peek", "claim"]

    lookups_only = _PeekingChannel(peek={"order_requests": 0, "contract_lookups": 2})
    _loop(lookups_only).tick()
    assert lookups_only.calls == ["peek", "claim_lookups"]


def test_work_found_through_the_peek_is_handled_exactly_as_before():
    """Same ticket, same refusal: the peek changes when we claim, never what we do."""
    row = {
        "request_id": "r1", "conid": 907480285, "sec_type": "OPT", "action": "BUY",
        "quantity_decimal": "2", "limit_price_decimal": "5.15", "owner": "drew",
        "strategy": "single_stock", "mode": "paper", "tif": "DAY", "state": "requested",
    }
    channel = _PeekingChannel(peek={"order_requests": 1, "contract_lookups": 0}, requests=[row])
    _loop(channel).tick()
    assert channel.published and channel.published[0][1]["state"] == "rejected"
    assert "options interlock" in channel.published[0][1]["reject_reason"]


def test_a_missing_peek_route_falls_back_to_claiming_and_reprobes_later():
    """The edge may deploy after the bridge; nothing may be stranded meanwhile."""
    clock = _Clock()
    channel = _PeekingChannel(peek=PeekUnavailable("peek route answered HTTP 405"))
    loop = _loop(channel, clock)

    loop.tick()
    assert channel.calls == ["peek", "claim", "claim_lookups"], "fall back to the old claim-both tick"

    channel.calls.clear()
    clock.now += PEEK_RETRY_SECONDS - 1
    loop.tick()
    assert channel.calls == ["claim", "claim_lookups"], "no re-probe inside the retry window"

    channel.calls.clear()
    channel._peek = {"order_requests": 0, "contract_lookups": 0}
    clock.now += 2
    loop.tick()
    assert channel.calls == ["peek"], "once the route exists the saving starts on its own"


def test_a_failing_peek_claims_directly_for_that_tick_only():
    channel = _PeekingChannel(peek=RuntimeError("HTTP 500 from the edge"))
    loop = _loop(channel)
    loop.tick()
    assert channel.calls == ["peek", "claim", "claim_lookups"]
    channel.calls.clear()
    channel._peek = {"order_requests": 0, "contract_lookups": 0}
    loop.tick()
    assert channel.calls == ["peek"], "a transient failure does not suspend the peek"


def test_a_channel_without_a_peek_behaves_as_it_always_did():
    class _Legacy:
        def __init__(self):
            self.calls = []

        def claim(self):
            self.calls.append("claim")
            return []

        def claim_lookups(self):
            self.calls.append("claim_lookups")
            return []

    channel = _Legacy()
    _loop(channel).tick()
    assert channel.calls == ["claim", "claim_lookups"]


def test_run_forever_on_an_idle_desk_sleeps_idle_and_never_claims():
    channel = _PeekingChannel()
    slept: list[float] = []

    def sleep(seconds):
        slept.append(seconds)
        if len(slept) == 5:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _loop(channel).run_forever(sleep=sleep)
    assert slept == [IDLE_POLL_SECONDS] * 5
    assert _nonce_writes(channel) == 0


# ---------------------------------------------------------------- the channel

class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _channel():
    return OrderCommandChannel(ChannelConfig(base_url="https://dash.example", token="t" * 40,
                                             account_alias="U123"))


def test_peek_is_a_signed_post_to_the_peek_route(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["url"], seen["method"], seen["body"] = request.full_url, request.get_method(), request.data
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        return _Response(json.dumps({"claimable": {"order_requests": 3, "contract_lookups": 0}}).encode())

    monkeypatch.setattr(command_poller.urllib.request, "urlopen", urlopen)
    assert _channel().peek() == {"order_requests": 3, "contract_lookups": 0}
    assert seen["url"] == f"https://dash.example{PEEK_PATH}"
    assert seen["method"] == "POST", "a GET would be answered by the SPA fallback page before deploy"
    assert json.loads(seen["body"]) == {"account_alias": "U123"}
    headers = seen["headers"]
    expected = hmac.new(("t" * 40).encode(),
                        f"{headers['x-portfolio-timestamp']}\n{headers['x-portfolio-nonce']}\n".encode() + seen["body"],
                        hashlib.sha256).hexdigest()
    assert headers["x-portfolio-signature"] == expected


@pytest.mark.parametrize("code", [404, 405])
def test_an_undeployed_peek_route_is_reported_as_unavailable(monkeypatch, code):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "no route", {}, io.BytesIO(b""))

    monkeypatch.setattr(command_poller.urllib.request, "urlopen", urlopen)
    with pytest.raises(PeekUnavailable):
        _channel().peek()


def test_a_pages_fallback_page_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr(command_poller.urllib.request, "urlopen",
                        lambda request, timeout: _Response(b"<!doctype html><title>dashboard</title>"))
    with pytest.raises(PeekUnavailable):
        _channel().peek()


def test_a_server_error_is_not_mistaken_for_a_missing_route(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, io.BytesIO(b""))

    monkeypatch.setattr(command_poller.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        _channel().peek()
