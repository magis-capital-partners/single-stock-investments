#!/usr/bin/env python3
"""Unit tests for insider conviction scoring (offline fixtures)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from insider_signal_common import (  # noqa: E402
    build_insider_signal,
    names_match,
    parse_form4_xml,
    score_transactions,
)


LMNR_FIXTURE = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>NOLAN PETER J</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>0</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-02</value></transactionDate>
      <transactionAmounts>
        <transactionShares><value>16420</value></transactionShares>
        <transactionPricePerShare><value>12.73</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>1100000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-05</value></transactionDate>
      <transactionAmounts>
        <transactionShares><value>3580</value></transactionShares>
        <transactionPricePerShare><value>12.78</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>1103580</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

SLATER_FIXTURE = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Scott S. Slater</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>0</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>0</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-08</value></transactionDate>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionPricePerShare><value>12.85</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>64447</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

HAMM_SALE = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Greg Hamm</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle><value>CFO</value></officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>1</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-01</value></transactionDate>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>13.10</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def lmnr_fixture_txs() -> list[dict]:
    meta = {"filing_date": "2026-01-09", "accession": "test", "source_path": "fixture"}
    txs = []
    txs.extend(parse_form4_xml(LMNR_FIXTURE, meta))
    txs.extend(parse_form4_xml(SLATER_FIXTURE, meta))
    txs.extend(parse_form4_xml(HAMM_SALE, meta))
    return txs


class InsiderSignalTests(unittest.TestCase):
    def test_names_match(self) -> None:
        self.assertTrue(names_match("Peter J. Nolan", "NOLAN PETER J"))
        self.assertTrue(names_match("Scott S. Slater", "Scott S. Slater"))

    def test_lmnr_ics_strong(self) -> None:
        txs = lmnr_fixture_txs()
        scored = score_transactions("LMNR", txs, spot=11.83)
        self.assertGreaterEqual(scored["ics"], 6.0)
        self.assertIn(scored["bull_case_support"], ("strong", "exceptional"))
        self.assertGreater(scored["scenario_confidence"]["bull_delta"], 0)

    def test_build_insider_signal(self) -> None:
        sig = build_insider_signal("LMNR", lmnr_fixture_txs())
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertFalse(sig["in_base_irr"])
        self.assertGreaterEqual(sig["ics"], 6.0)
        hooks = " ".join(sig.get("narrative_hooks") or [])
        self.assertIn("domain-relevant", hooks.lower())


if __name__ == "__main__":
    unittest.main()
