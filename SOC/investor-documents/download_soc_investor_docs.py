"""
Download Sable Offshore Corp. (SOC, CIK 0001831481) SEC filings and IR PDFs.
SEC requires a descriptive User-Agent; replace CONTACT below if you use this script regularly.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

SEC_UA = "SOCInvestorDocs (marvin-research@example.com)"
IR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SOCInvestorDocs/1.0"
COMPANY_EDGAR_CIK_PATH = "1831481"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0001831481.json"
SLEEP_SEC = 0.12
MIN_FILING_DATE = "2022-01-01"

ROOT = os.path.dirname(os.path.abspath(__file__))
SEC_DIR = os.path.join(ROOT, "sec-edgar")
IR_DIR = os.path.join(ROOT, "ir-sableoffshore")

FORM_LIMITS = [
    ("10-K", 5),
    ("10-K/A", 3),
    ("10-Q", 14),
    ("DEF 14A", 4),
    ("PRE 14A", 3),
    ("S-3", 5),
    ("S-3ASR", 3),
    ("424B5", 10),
    ("424B3", 5),
    ("S-1", 3),
    ("S-1/A", 3),
    ("8-K", 25),
]


def sec_url(accession: str, primary: str) -> str:
    nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{COMPANY_EDGAR_CIK_PATH}/{nodash}/{primary}"


def download(url: str, dest: str, ua: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except Exception as e:
        print(f"FAIL {url}\n  -> {e}")
        return False
    with open(dest, "wb") as f:
        f.write(data)
    print(f"OK {len(data):,} bytes -> {dest}")
    return True


def main() -> None:
    os.makedirs(SEC_DIR, exist_ok=True)
    os.makedirs(IR_DIR, exist_ok=True)

    req = urllib.request.Request(SUBMISSIONS_URL, headers={"User-Agent": SEC_UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)

    recent = j["filings"]["recent"]
    n = len(recent["form"])
    rows = []
    for i in range(n):
        rows.append(
            {
                "form": recent["form"][i],
                "filingDate": recent["filingDate"][i],
                "accession": recent["accessionNumber"][i],
                "primary": recent["primaryDocument"][i],
                "report": recent["reportDate"][i] or "",
            }
        )

    picked: list[dict] = []
    for form, limit in FORM_LIMITS:
        cnt = 0
        for row in rows:
            if row["form"] != form:
                continue
            if row["filingDate"] < MIN_FILING_DATE:
                continue
            picked.append(row)
            cnt += 1
            if cnt >= limit:
                break

    manifest = []
    for row in picked:
        fd = row["filingDate"].replace("-", "")
        rep = (row.get("report") or "").replace("-", "")
        acc = row["accession"].replace("-", "_")
        ext = os.path.splitext(row["primary"])[1] or ".htm"
        safe = f"{row['form'].replace('/', '-')}_{fd}_rpt{rep}_acc{acc}{ext}"
        dest = os.path.join(SEC_DIR, safe)
        url = sec_url(row["accession"], row["primary"])
        time.sleep(SLEEP_SEC)
        ok = download(url, dest, SEC_UA)
        manifest.append({**row, "url": url, "local": dest, "ok": ok})

    # IR: try investor relations page for PDFs
    ir_urls = [
        "https://www.sableoffshore.com/investors",
        "https://ir.sableoffshore.com/",
    ]
    pdfs: set[str] = set()
    for pres_url in ir_urls:
        try:
            req = urllib.request.Request(pres_url, headers={"User-Agent": IR_UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", errors="ignore")
            pdfs.update(re.findall(r"https?://[^\"'\\s]+\\.pdf", html, flags=re.I))
        except Exception as e:
            print(f"IR skip {pres_url}: {e}")

    for u in sorted(pdfs):
        name = re.sub(r"[^a-zA-Z0-9._-]", "_", u.rsplit("/", 1)[-1])
        dest = os.path.join(IR_DIR, name)
        time.sleep(SLEEP_SEC)
        download(u, dest, IR_UA)

    man_path = os.path.join(ROOT, "DOWNLOAD_MANIFEST.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote manifest: {man_path} ({len(manifest)} SEC filings)")


if __name__ == "__main__":
    main()
