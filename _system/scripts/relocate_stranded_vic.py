#!/usr/bin/env python3
"""Move stranded VIC PDFs onto the canonical Admin/Intake tree.

Does not create repo ticker folders. A writeup whose ticker already exists
is filed under that ticker. A writeup whose ticker does not exist is filed
on Drive at VIC/{TICKER}/ and removed from the wrong repo ticker.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parents[1]
sys.path.insert(0, str(SCRIPTS))

from drive_store_common import (  # noqa: E402
    drive_service,
    ensure_folder_path,
    execute_with_retry,
    folder_id_by_parent_name,
    list_drive_items,
)
from import_drive_intake import (  # noqa: E402
    MANIFEST_PATH,
    download_pdf,
    rel,
    sha256_bytes,
    write_sidecar,
)
from third_party_inventory import write_inventory  # noqa: E402
from vault_paths import vic_root  # noqa: E402

INTAKE_ROOT = "1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C"
WRONG_VIC = "1HtIs_B-agRDDg3vDI99Ki1cS8MTyGm0W"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,24}$")
EXPLICIT = re.compile(
    r"\((?:NYSE|NASDAQ|Nasdaq|TSX|TSXV|LSE|AIM|KRX|KOSDAQ)\s*:\s*([A-Z0-9][A-Z0-9.\-]{0,12})\)",
    re.I,
)

# Body-identified subjects whose Drive path was VIC/{wrong}/ or a bare filename.
OVERRIDES = {
    "163557.pdf": "BIRK",
    "163572.pdf": "SFIX",
    "163586.pdf": "SEER",
    "163592.pdf": "ELME",
    "163596.pdf": "101160.KS",
    "163598.pdf": "SHLS",
    "163599.pdf": "U.UN",
    "BWMX.pdf": "BWMX",
    "CTRI.pdf": "CTRI",
    "FLNC.pdf": "FLNC",
    "JOE - 02-Truen.pdf": "417790.KS",
    "JOE - 03-First-Ottawa-Bancshares.pdf": "FOTB",
    "JOE - 03-Inter-and-Co.pdf": "INTR",
    "JOE - 07-Floor-and-Decor.pdf": "FND",
    "JOE - 08-Natural-Grocers.pdf": "NGVC",
    "JOE - 10-Chewy.pdf": "CHWY",
}


def ticker_exists(ticker: str) -> bool:
    return (ROOT / ticker).is_dir()


def path_ticker(drive_path: str) -> str:
    parts = [p for p in (drive_path or "").split("/") if p]
    if len(parts) >= 2 and parts[0].upper() == "VIC" and TICKER_RE.match(parts[1].upper()):
        if not parts[1].lower().endswith(".pdf"):
            return parts[1].upper()
    return ""


def clean_stem(filename: str, old_ticker: str) -> str:
    stem = Path(filename).stem
    prefix = f"{old_ticker} - "
    if stem.upper().startswith(prefix.upper()):
        stem = stem[len(prefix) :]
    return stem


def drive_name_for(ticker: str, filename: str, old_ticker: str) -> str:
    stem = clean_stem(filename, old_ticker)
    prefix = f"{ticker} - "
    if stem.upper().startswith(prefix.upper()):
        return f"{stem}.pdf"
    return f"{ticker} - {stem}.pdf"


def move_drive_file(service, file_id: str, folder_id: str, new_name: str) -> dict:
    meta = execute_with_retry(
        service.files().get(
            fileId=file_id,
            fields="id,name,parents",
            supportsAllDrives=True,
        )
    )
    parents = meta.get("parents") or []
    if parents == [folder_id] and meta.get("name") == new_name:
        return {"status": "already_placed", "name": new_name}
    kwargs = {
        "fileId": file_id,
        "addParents": folder_id,
        "supportsAllDrives": True,
        "fields": "id,name,parents",
    }
    if parents:
        kwargs["removeParents"] = ",".join(parents)
    if new_name and new_name != meta.get("name"):
        kwargs["body"] = {"name": new_name}
    updated = execute_with_retry(service.files().update(**kwargs))
    return {"status": "moved", "name": updated.get("name") or new_name}


def ensure_vic_ticker(service, existing, ticker: str, dry_run: bool) -> str:
    return ensure_folder_path(service, INTAKE_ROOT, f"VIC/{ticker}", dry_run, existing)


def vault_dir(ticker: str) -> Path:
    return vic_root(create=True) / ticker


def relocate_vault(old: str, new: str, stems: set[str], dry_run: bool) -> list[str]:
    source = vic_root(create=False)
    if source is None:
        return []
    src_dir = source / old
    if not src_dir.is_dir():
        return []
    moved = []
    dest_dir = source / new
    for path in list(src_dir.iterdir()):
        if path.stem not in stems and path.name not in stems:
            continue
        moved.append(str(path.name))
        if dry_run:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / path.name
        if target.exists():
            path.unlink()
        else:
            shutil.move(str(path), str(target))
    return moved


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"schema_version": 1, "files": {}}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def misfiled_rows() -> list[dict]:
    rows = []
    for src in ROOT.glob("*/third-party-analyses/vic/*.source.json"):
        data = json.loads(src.read_text(encoding="utf-8"))
        current = src.parent.parent.parent.name
        pdf = src.with_suffix(".pdf")
        # with_suffix on foo.source.json -> foo.source.pdf. The pdf shares the stem of the sidecar.
        pdf = src.parent / (src.name[: -len(".source.json")] + ".pdf")
        override = OVERRIDES.get(pdf.name) or OVERRIDES.get(data.get("drive_name") or "")
        intended = override or path_ticker(data.get("drive_path") or "")
        if not intended or intended == current:
            continue
        rows.append(
            {
                "current": current,
                "ticker": intended,
                "pdf": pdf,
                "sidecar": src,
                "drive_file_id": data.get("drive_file_id") or "",
                "filename": pdf.name,
                "meta": data,
            }
        )
    return rows


def apply_misfiles(service, existing, dry_run: bool) -> list[dict]:
    manifest = load_manifest()
    files = manifest.setdefault("files", {})
    touched: set[str] = set()
    report = []
    for row in misfiled_rows():
        ticker = row["ticker"]
        current = row["current"]
        pdf: Path = row["pdf"]
        sidecar: Path = row["sidecar"]
        new_name = drive_name_for(ticker, row["filename"], current)
        action = {
            "from": current,
            "to": ticker,
            "file": row["filename"],
            "repo": ticker_exists(ticker),
            "drive_name": new_name,
        }
        stems = {Path(row["filename"]).stem, clean_stem(row["filename"], current), Path(new_name).stem}
        if not dry_run and row["drive_file_id"]:
            folder_id = ensure_vic_ticker(service, existing, ticker, False)
            try:
                action["drive"] = move_drive_file(service, row["drive_file_id"], folder_id, new_name)
            except Exception as exc:  # noqa: BLE001
                action["drive_error"] = str(exc)
        action["vault"] = relocate_vault(current, ticker, stems, dry_run)
        if ticker_exists(ticker):
            dest_dir = ROOT / ticker / "third-party-analyses" / "vic"
            dest_pdf = dest_dir / new_name
            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if pdf.is_file() and pdf.resolve() != dest_pdf.resolve():
                    if dest_pdf.exists():
                        pdf.unlink()
                    else:
                        shutil.move(str(pdf), str(dest_pdf))
                if sidecar.is_file():
                    meta = json.loads(sidecar.read_text(encoding="utf-8"))
                    meta["ticker"] = ticker
                    meta["drive_moved_to"] = f"VIC/{ticker}/{new_name}"
                    meta["ticker_resolve_method"] = "manual_relocate"
                    dest_side = dest_pdf.with_suffix(".source.json")
                    dest_side.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
                    if sidecar.resolve() != dest_side.resolve() and sidecar.exists():
                        sidecar.unlink()
                entry = files.get(row["drive_file_id"]) or {}
                entry.update(
                    {
                        "ticker": ticker,
                        "local_pdf_path": rel(dest_pdf),
                        "drive_moved_to": f"VIC/{ticker}/{new_name}",
                        "ticker_resolve_method": "manual_relocate",
                        "status": entry.get("status") or "relocated",
                    }
                )
                if row["drive_file_id"]:
                    files[row["drive_file_id"]] = entry
            touched.add(ticker)
            touched.add(current)
            action["local"] = rel(dest_pdf)
        else:
            if not dry_run:
                if pdf.is_file():
                    pdf.unlink()
                if sidecar.is_file():
                    sidecar.unlink()
                if row["drive_file_id"]:
                    files.pop(row["drive_file_id"], None)
            touched.add(current)
            action["local"] = "removed_from_wrong_ticker"
        report.append(action)
    if not dry_run:
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for ticker in sorted(touched):
            if ticker_exists(ticker):
                write_inventory(ticker)
    return report


def list_children(service, folder_id: str) -> list[dict]:
    token = None
    out = []
    while True:
        resp = execute_with_retry(
            service.files().list(
                q="'%s' in parents and trashed=false" % folder_id,
                fields="nextPageToken, files(id,name,mimeType,parents)",
                pageSize=200,
                pageToken=token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
        )
        out.extend(resp.get("files") or [])
        token = resp.get("nextPageToken")
        if not token:
            break
    return out


def import_existing(service, file_id: str, ticker: str, filename: str, dry_run: bool) -> str:
    if not ticker_exists(ticker):
        return "drive_only"
    if dry_run:
        return "would_import"
    data = download_pdf(service, file_id)
    dest_dir = ROOT / ticker / "third-party-analyses" / "vic"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    if not (dest.exists() and sha256_bytes(dest.read_bytes()) == sha256_bytes(data)):
        dest.write_bytes(data)
    item = execute_with_retry(
        service.files().get(
            fileId=file_id,
            fields="id,name,webViewLink,createdTime,modifiedTime",
            supportsAllDrives=True,
        )
    )
    parsed = {
        "intake_kind": "vic",
        "ticker": ticker,
        "path": f"VIC/{ticker}/{filename}",
        "ticker_resolve_method": "folder_name",
        "drive_moved_to": f"VIC/{ticker}/{filename}",
    }
    write_sidecar(dest, item, parsed, sha256_bytes(data))
    from vic_vault import stage_vic_to_vault

    stage_vic_to_vault(ticker, pdf_path=dest, filename=dest.name)
    manifest = load_manifest()
    manifest.setdefault("files", {})[file_id] = {
        "status": "imported",
        "intake_kind": "vic",
        "ticker": ticker,
        "drive_file_id": file_id,
        "drive_name": item.get("name"),
        "local_pdf_path": rel(dest),
        "sha256": sha256_bytes(data),
        "ticker_resolve_method": "folder_name",
        "drive_moved_to": f"VIC/{ticker}/{filename}",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_inventory(ticker)
    return rel(dest)


def move_wrong_tree(service, existing, dry_run: bool) -> list[dict]:
    report = []
    try:
        meta = execute_with_retry(
            service.files().get(fileId=WRONG_VIC, fields="id,name,driveId", supportsAllDrives=True)
        )
        folders = [f for f in list_children(service, WRONG_VIC) if str(f.get("mimeType", "")).endswith("folder")]
    except Exception as exc:  # noqa: BLE001
        return [{"error": "wrong_tree_not_visible", "detail": str(exc)}]
    if not folders:
        return [{"error": "wrong_tree_empty_or_hidden", "seen": meta.get("name"), "driveId": meta.get("driveId")}]
    for folder in folders:
        ticker = str(folder.get("name") or "").strip().upper()
        if not TICKER_RE.match(ticker):
            report.append({"skip": folder.get("name"), "reason": "bad_ticker"})
            continue
        pdfs = [f for f in list_children(service, folder["id"]) if f.get("mimeType") == "application/pdf"]
        folder_id = None if dry_run else ensure_vic_ticker(service, existing, ticker, False)
        for pdf in pdfs:
            name = pdf.get("name") or "writeup.pdf"
            action = {"from": "wrong_tree", "to": ticker, "file": name, "repo": ticker_exists(ticker)}
            if not dry_run and folder_id:
                try:
                    action["drive"] = move_drive_file(service, pdf["id"], folder_id, name)
                    action["local"] = import_existing(service, pdf["id"], ticker, name, False)
                except Exception as exc:  # noqa: BLE001
                    action["error"] = str(exc)
            report.append(action)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    dry_run = not args.apply
    service = drive_service(readonly=dry_run)
    items = list_drive_items(service, [INTAKE_ROOT]) if not dry_run else []
    existing = folder_id_by_parent_name(items) if items else {}
    report = {
        "dry_run": dry_run,
        "misfiles": apply_misfiles(service, existing, dry_run),
        "wrong_tree": move_wrong_tree(service, existing, dry_run),
    }
    out = ROOT / "_system" / "reference" / "document-store" / "vic_relocate_2026-09-22.json"
    if not dry_run:
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in report.items()}, indent=2))
    for row in report["misfiles"]:
        print(f"{row['from']} -> {row['to']} repo={row['repo']} {row['file']}")
    for row in report["wrong_tree"][:20]:
        print("tree", row)
    print("wrong_tree_count", len(report["wrong_tree"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
