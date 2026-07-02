#!/usr/bin/env python3
"""Batch onboard tickers from portfolio intake list."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
ONBOARD = ROOT / "_system" / "scripts" / "onboard_ticker.py"

# (ticker, company, market, ir_url, skip_download)
TICKERS = [
    ("ABMD.CVR", "Abiomed CVR (Johnson & Johnson acquisition)", "US", "", True),
    ("ASPN", "Aspen Aerogels, Inc.", "US", "https://ir.aerogel.com", False),
    ("AXON", "Axon Enterprise, Inc.", "US", "https://investor.axon.com", False),
    ("B", "Barrick Mining Corporation", "US", "https://www.barrick.com/investors", False),
    ("BRBR", "BellRing Brands, Inc.", "US", "https://investors.bellring.com", False),
    ("COLD", "Americold Realty Trust, Inc.", "US", "https://ir.americold.com", False),
    ("CORBF", "Corbus Pharmaceuticals Holdings, Inc.", "US", "https://www.corbuspharma.com", True),
    ("CSU.DB", "Constellation Software Inc. (Series 1 Debentures)", "CA", "https://www.csisoftware.com/category/stat-filings", True),
    ("ECHO", "EchoStar Corporation", "US", "https://ir.echostar.com", False),
    ("EFOR", "Everforth, Inc.", "US", "https://investor.everforth.com", False),
    ("ENPH", "Enphase Energy, Inc.", "US", "https://investor.enphase.com", False),
    ("EQPT", "EquipmentShare.com Inc", "US", "https://investors.equipmentshare.com", False),
    ("ETOR", "eToro Group Ltd.", "US", "https://investors.etoro.com", False),
    ("FIHO12.MX", "FibraHotel (Concentradora Fibra Hotelera Mexicana)", "EU", "https://fibrahotel.mx", True),
    ("FLUX", "Flux Power Holdings, Inc.", "US", "https://ir.fluxpower.com", False),
    ("FMCCK", "Ford Motor Credit Company LLC (Preferred)", "US", "", True),
    ("FMCCL", "Ford Motor Credit Company LLC (Preferred)", "US", "", True),
    ("FNMAO", "Federal National Mortgage Association (Preferred)", "US", "", True),
    ("FNMAP", "Federal National Mortgage Association (Preferred)", "US", "", True),
    ("FTRE", "Fortrea Holdings Inc.", "US", "https://investor.fortrea.com", False),
    ("GDRZF", "Gold Reserve Inc.", "US", "https://www.goldreserveinc.com", True),
    ("GKTX.PS1", "Galapagos NV (Janssen structured security PS1)", "US", "", True),
    ("GKTX.PS2", "Galapagos NV (Janssen structured security PS2)", "US", "", True),
    ("GKTX.PS3", "Galapagos NV (Janssen structured security PS3)", "US", "", True),
    ("GPGI", "GPGI, Inc.", "US", "https://gpgi.com/investors", False),
    ("GS", "Goldman Sachs Group, Inc.", "US", "https://www.goldmansachs.com/investor-relations", False),
    ("GTX", "Garrett Motion Inc.", "US", "https://investors.garrettmotion.com", False),
    ("HEI.A", "HEICO Corporation (Class A)", "US", "https://heico.com/investors", False),
    ("HL", "Hecla Mining Company", "US", "https://www.hecla.com/investors", False),
    ("INV", "Innovex International, Inc.", "US", "https://www.innovex-inc.com/investors", False),
    ("IPCXR", "Inflection Point Acquisition Corp. II (Rights)", "US", "", True),
    ("JL80.DE", "Norconsult ASA", "EU", "https://norconsult.com/investors", True),
    ("JPM", "JPMorgan Chase & Co.", "US", "https://www.jpmorganchase.com/ir", False),
    ("LBRDK", "Liberty Broadband Corporation (Class C)", "US", "https://www.libertybroadband.com/investors", False),
    ("LMN", "Lumine Group Inc.", "CA", "https://www.luminegroup.com/investor-relations", True),
    ("MCHB", "Mechanics Bancorp", "US", "https://investor.mechanicsbank.com", False),
    ("MDB", "MongoDB, Inc.", "US", "https://investors.mongodb.com", False),
    ("MRTX.CVR", "Mirati Therapeutics CVR (Bristol-Myers Squibb acquisition)", "US", "", True),
    ("NAN", "Nuveen New York AMT-Free Quality Municipal Income Fund", "US", "https://www.nuveen.com/en-us/investment-products/closed-end-funds/nan", True),
    ("POST", "Post Holdings, Inc.", "US", "https://investor.postholdings.com", False),
    ("PRVL.CVR", "Prevail Therapeutics CVR (Eli Lilly acquisition)", "US", "", True),
    ("SHC", "Sotera Health Company", "US", "https://investors.soterahealth.com", False),
    ("SRPT", "Sarepta Therapeutics, Inc.", "US", "https://investorrelations.sarepta.com", False),
    ("TBBK", "The Bancorp, Inc.", "US", "https://investors.thebancorp.com", False),
    ("TOI", "The Oncology Institute, Inc.", "US", "https://investors.theoncologyinstitute.com", False),
    ("WEST", "Westrock Coffee Company", "US", "https://investors.westrockcoffee.com", False),
    ("XTIA", "XTI Aerospace, Inc.", "US", "https://www.xtiaerospace.com", False),
]


def main() -> int:
    import json

    reg = json.loads((ROOT / "_system" / "portfolio" / "registry.json").read_text(encoding="utf-8"))
    existing = set(reg.get("holdings", {})) | set(reg.get("watchlist", {}))

    failed: list[tuple[str, int]] = []
    skipped: list[str] = []
    ok: list[str] = []

    for ticker, company, market, ir_url, skip_dl in TICKERS:
        if ticker in existing or (ROOT / ticker).is_dir():
            skipped.append(ticker)
            print(f"SKIP (exists): {ticker}", flush=True)
            continue

        cmd = [
            PY,
            str(ONBOARD),
            "--ticker",
            ticker,
            "--company",
            company,
            "--market",
            market,
            "--no-deep-dive",
        ]
        if ir_url:
            cmd.extend(["--ir-url", ir_url])
        if skip_dl:
            cmd.append("--skip-download")

        print(f"\n{'=' * 60}\nONBOARD {ticker}\n{'=' * 60}", flush=True)
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode == 0:
            ok.append(ticker)
        else:
            failed.append((ticker, result.returncode))

    print("\n=== BATCH SUMMARY ===", flush=True)
    print(f"OK ({len(ok)}): {', '.join(ok)}", flush=True)
    print(f"Skipped ({len(skipped)}): {', '.join(skipped)}", flush=True)
    if failed:
        print(f"Failed ({len(failed)}): {failed}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
