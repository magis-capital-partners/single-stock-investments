"""Issuer operating KPIs (volume, share, revenue per contract, industry totals).

Add an issuer by writing a parser module and appending it in ``registry.py``.
Each parser turns one primary document into normalized points. The fetcher
owns the network; tests call the parsers on fixtures.
"""
