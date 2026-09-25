from _system.trading.portfolio_hub.publisher import signed_headers


def test_signed_headers_are_body_bound() -> None:
    headers = signed_headers("x" * 32, b"payload", now=1_777_777_777)
    assert headers["x-portfolio-timestamp"] == "1777777777"
    assert headers["user-agent"] == "MagisPortfolioHub/1.0"
    assert len(headers["x-portfolio-nonce"]) == 32
    assert len(headers["x-portfolio-signature"]) == 64


def test_a_signing_domain_binds_the_signature_and_is_validated() -> None:
    """The peek's domain makes its signature useless on every undomained route."""
    import hashlib
    import hmac

    import pytest

    peek = signed_headers("x" * 32, b"{}", now=1_777_777_777, domain="peek")
    nonce = peek["x-portfolio-nonce"]
    domained = hmac.new(("x" * 32).encode(), f"peek\n1777777777\n{nonce}\n".encode() + b"{}", hashlib.sha256).hexdigest()
    undomained = hmac.new(("x" * 32).encode(), f"1777777777\n{nonce}\n".encode() + b"{}", hashlib.sha256).hexdigest()
    assert peek["x-portfolio-signature"] == domained
    assert peek["x-portfolio-signature"] != undomained
    # A domain that could begin like a timestamp, or carry a newline, would let
    # the two message shapes collide.
    for bad in ("", "1peek", "peek\n", "PEEK", "peek-ish"):
        with pytest.raises(ValueError):
            signed_headers("x" * 32, b"{}", domain=bad)
