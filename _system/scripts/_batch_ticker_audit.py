#!/usr/bin/env python3
"""One-off audit + SEC lookup for batch onboard."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEC_UA = "Marvin Research single-stock-investments (contact: portfolio@local)"

USER_TICKERS = [
    "3905.T", "ABMD.CVR", "APLD", "ASPN", "AXON", "B", "BRBR", "BRKB", "BUR", "COLD",
    "CORBF", "CSU", "CSU.DB", "ECHO", "EFOR", "ENPH", "EQPT", "ETOR", "FIHO12", "FLUX",
    "FMCCK", "FMCCL", "FNMAO", "FNMAP", "FTRE", "GDRZF", "GKTX.PS1", "GKTX.PS2", "GKTX.PS3",
    "GPGI", "GS", "GTX", "HEI A", "HL", "INV", "IPCXR", "JL80", "JPM", "LBRDK", "LMN",
    "MCHB", "MCO", "MDB", "MRTX.CVR", "NAN", "POST", "PRVL.CVR", "QDEL", "SHC", "SRPT",
    "TBBK", "TOI", "WEST", "XTIA",
]

FORMAT_CORRECTIONS = {
    "BRKB": ("BKRB", "Already in universe as BKRB (Berkshire Class B)"),
    "HEI A": ("HEI.A", "Heico Corp Class A — use dot, not space"),
}

# Canonical onboard list: (ticker, company, market, notes)
ONBOARD_MANUAL = {
    "ABMD.CVR": ("ABMD.CVR", "Abiomed CVR (J&J acquisition)", "US", "CVR; not in SEC ticker map"),
    "ASPN": ("ASPN", "Aspen Aerogels, Inc.", "US", ""),
    "AXON": ("AXON", "Axon Enterprise, Inc.", "US", ""),
    "B": ("B", "Barrick Mining Corporation", "US", "NYSE; formerly Barrick Gold"),
    "BRBR": ("BRBR", "BellRing Brands, Inc.", "US", ""),
    "COLD": ("COLD", "Americold Realty Trust, Inc.", "US", ""),
    "CORBF": ("CORBF", "Corbus Pharmaceuticals Holdings, Inc.", "US", "OTC Pink"),
    "CSU.DB": ("CSU.DB", "Constellation Software Inc. (DB)", "CA", "Depository receipt; parent CSU already onboarded"),
    "ECHO": ("ECHO", "EchoStar Corporation", "US", "May reflect post-DISH reorg; verify symbol"),
    "EFOR": ("EFOR", "eForCity Holdings (verify)", "US", "Illiquid/OTC — verify active symbol"),
    "ENPH": ("ENPH", "Enphase Energy, Inc.", "US", ""),
    "EQPT": ("EQPT", "EquipmentShare.com Inc", "US", "Recent IPO"),
    "ETOR": ("ETOR", "eToro Group Ltd.", "US", "Recent IPO"),
    "FIHO12": ("FIHO12", "Fidelity International High Dividend ETF (verify)", "US", "Fund ticker — verify listing"),
    "FLUX": ("FLUX", "Flux Power Holdings, Inc.", "US", ""),
    "FMCCK": ("FMCCK", "Ford Motor Credit Company LLC (Preferred)", "US", "Preferred; manual IR"),
    "FMCCL": ("FMCCL", "Ford Motor Credit Company LLC (Preferred)", "US", "Preferred; manual IR"),
    "FNMAO": ("FNMAO", "Federal National Mortgage Association (Preferred)", "US", "Fannie Mae pref"),
    "FNMAP": ("FNMAP", "Federal National Mortgage Association (Preferred)", "US", "Fannie Mae pref"),
    "FTRE": ("FTRE", "Fortrea Holdings Inc.", "US", "Spin from LabCorp"),
    "GDRZF": ("GDRZF", "Gold Reserve Inc.", "US", "OTC"),
    "GKTX.PS1": ("GKTX.PS1", "Galapagos NV (Janssen CVR/Rights PS1)", "US", "Structured security"),
    "GKTX.PS2": ("GKTX.PS2", "Galapagos NV (Janssen CVR/Rights PS2)", "US", "Structured security"),
    "GKTX.PS3": ("GKTX.PS3", "Galapagos NV (Janssen CVR/Rights PS3)", "US", "Structured security"),
    "GPGI": ("GPGI", "GPGI, Inc.", "US", "Verify — small cap"),
    "GS": ("GS", "Goldman Sachs Group, Inc.", "US", ""),
    "GTX": ("GTX", "Garrett Motion Inc.", "US", ""),
    "HEI.A": ("HEI.A", "HEICO Corporation (Class A)", "US", "Class A shares"),
    "HL": ("HL", "Hecla Mining Company", "US", ""),
    "INV": ("INV", "Innovex International, Inc.", "US", ""),
    "IPCXR": ("IPCXR", "Inflection Point Acquisition Corp. II (Rights)", "US", "SPAC rights"),
    "JL80": ("JL80", "Janus Henderson AAA CLO ETF (verify)", "US", "Fund — verify listing"),
    "JPM": ("JPM", "JPMorgan Chase & Co.", "US", ""),
    "LBRDK": ("LBRDK", "Liberty Broadband Corporation (Class C)", "US", "Tracking stock"),
    "LMN": ("LMN", "Lumen Technologies (verify) / or Luminar?", "US", "Ambiguous — verify portfolio intent"),
    "MCHB": ("MCHB", "Mechanics Bancorp (verify)", "US", "Verify symbol"),
    "MDB": ("MDB", "MongoDB, Inc.", "US", ""),
    "MRTX.CVR": ("MRTX.CVR", "Mirati Therapeutics CVR (BMS acquisition)", "US", "CVR"),
    "NAN": ("NAN", "Nuveen New York AMT-Free Quality Municipal Income Fund", "US", "Closed-end fund"),
    "POST": ("POST", "Post Holdings, Inc.", "US", ""),
    "PRVL.CVR": ("PRVL.CVR", "Prevail Therapeutics CVR (Lilly acquisition)", "US", "CVR"),
    "SHC": ("SHC", "Sotera Health Company", "US", ""),
    "SRPT": ("SRPT", "Sarepta Therapeutics, Inc.", "US", ""),
    "TBBK": ("TBBK", "The Bancorp, Inc.", "US", ""),
    "TOI": ("TOI", "The Oncology Institute, Inc.", "US", ""),
    "WEST": ("WEST", "Westrock Coffee Company", "US", ""),
    "XTIA": ("XTIA", "XTI Aerospace, Inc.", "US", ""),
}


def load_sec_map() -> dict[str, tuple[str, str]]:
    req = urllib.request.Request(
        "https://www.sec.gov/files/company_tickers.json",
        headers={"User-Agent": SEC_UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return {str(v["ticker"]).upper(): (v["title"], str(v["cik_str"]).zfill(10)) for v in data.values()}


def main() -> None:
    registry = json.loads((ROOT / "_system/portfolio/registry.json").read_text(encoding="utf-8"))
    holdings = set(registry.get("holdings", {}))
    watchlist = set(registry.get("watchlist", {}))
    all_reg = holdings | watchlist

    sec = load_sec_map()

    print("=== FORMAT CORRECTIONS ===")
    for raw, (canonical, note) in FORMAT_CORRECTIONS.items():
        exists = canonical in all_reg or (ROOT / canonical).is_dir()
        print(f"  {raw} -> {canonical} | {note} | in_universe={exists}")

    print("\n=== ALREADY IN UNIVERSE ===")
    for t in USER_TICKERS:
        canon = FORMAT_CORRECTIONS.get(t, (t,))[0]
        if t in all_reg or canon in all_reg or (ROOT / t).is_dir() or (ROOT / canon).is_dir():
            print(f"  SKIP: {t}")

    print("\n=== SEC VALIDATION (new tickers) ===")
    for ticker, (canon, company, market, notes) in ONBOARD_MANUAL.items():
        if canon in all_reg or (ROOT / canon).is_dir():
            continue
        hit = sec.get(canon.upper())
        sec_note = f"SEC OK: {hit[0][:55]}" if hit else "NOT IN SEC (expected for CVR/pref/fund)"
        print(f"  {canon:12} {sec_note} | {notes}")

    print(f"\nTotal to onboard: {sum(1 for t in ONBOARD_MANUAL if t not in all_reg and not (ROOT / t).is_dir())}")


if __name__ == "__main__":
    main()
