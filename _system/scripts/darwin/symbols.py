"""Yahoo Finance symbol overrides for non-US listings."""

YAHOO_SYMBOL: dict[str, str] = {
    "CSU": "CSU.TO",
    "BN": "BN.TO",
    "TEQ.ST": "TEQ.ST",
    "8697.T": "8697.T",
    "3905.T": "3905.T",
    "LSEG": "LSEG.L",
    "HEE": "EXAE.AT",
    "CMSG": "CMSG",
    "KEWL": "KEWL",
    "FRMO": "FRMO",
    "OTCM": "OTCM",
}


def yahoo_for_ticker(ticker: str, market: str = "US") -> str:
    if ticker in YAHOO_SYMBOL:
        return YAHOO_SYMBOL[ticker]
    if market == "US" and "." not in ticker:
        return ticker.split(".")[0]
    return ticker
