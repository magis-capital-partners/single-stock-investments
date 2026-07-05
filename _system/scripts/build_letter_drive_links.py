#!/usr/bin/env python3
"""Map superinvestor letter source paths to Google Drive PDF links."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))
from vault_paths import letters_root  # noqa: E402

LETTERS_INDEX_PATH = letters_root() / "letters_index.json"
FILENAME_INDEX_PATH = ROOT / "_system/reference/document-store/drive_filename_index.json"
FOLDER_INDEX_PATH = ROOT / "_system/reference/document-store/drive_folder_index.json"
OUTPUT_PATH = ROOT / "_system/reference/document-store/letter_drive_links.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(value).stem.lower())


def quarter_folder_paths(quarter: str | None) -> list[str]:
    text = str(quarter or "").strip().upper()
    match = re.match(r"^(20\d{2})Q([1-4])$", text)
    if not match:
        return []
    label = f"{match.group(1)} Q{match.group(2)}"
    return [
        f"Letters/{label}",
        f"Letters/Letters/{label}",
        f"superinvestor-letters/{text}",
    ]


def folder_links() -> dict[str, str]:
    payload = load_json(FOLDER_INDEX_PATH, {})
    out: dict[str, str] = {}
    for path, meta in (payload.get("folders") or {}).items():
        link = (meta or {}).get("webViewLink")
        if link:
            out[str(path)] = str(link)
    return out


def filename_index() -> dict[str, dict]:
    payload = load_json(FILENAME_INDEX_PATH, {})
    return payload.get("by_filename") or {}


def pdfs_in_folder(folder_id: str, index: dict[str, dict]) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for key, row in index.items():
        parents = row.get("parents") or []
        if folder_id in parents:
            rows.append((key, row))
    return rows


def fund_match_score(fund: str | None, filename: str, quarter: str | None) -> int:
    if not fund or not quarter:
        return 0
    year = quarter[:4]
    qnum = quarter[-1]
    name = filename.lower()
    if year not in name:
        return 0
    if f"q{qnum}" not in name and f"{qnum}q" not in name and f" {qnum} " not in f" {name} ":
        if qnum == "1" and not any(token in name for token in ("q1", "1q", "first quarter")):
            return 0
    tokens = [t for t in re.split(r"[^a-z0-9]+", fund.lower()) if len(t) >= 4]
    return sum(1 for token in tokens if token in name)


def resolve_letter_link(letter: dict, index: dict[str, dict], folders: dict[str, str]) -> str | None:
    source_document = str(letter.get("source_document") or "").replace("\\", "/")
    if not source_document:
        return None

    filename = Path(source_document).name.lower()
    exact = index.get(filename)
    if exact and exact.get("webViewLink"):
        return str(exact["webViewLink"])

    stem = Path(source_document).stem.lower()
    norm = normalize_name(source_document)
    for key, row in index.items():
        if key == stem or normalize_name(key) == norm:
            link = row.get("webViewLink")
            if link:
                return str(link)

    quarter = str(letter.get("quarter") or "").upper()
    fund = letter.get("fund")
    for folder_path in quarter_folder_paths(quarter):
        folder_link = folders.get(folder_path)
        if not folder_link:
            continue
        folder_id = folder_link.rstrip("/").split("/")[-1]
        candidates = pdfs_in_folder(folder_id, index)
        if not candidates:
            continue
        best_score = 0
        best_link = None
        for key, row in candidates:
            score = fund_match_score(fund, key, quarter)
            if filename == key:
                score += 10
            if score > best_score:
                best_score = score
                best_link = row.get("webViewLink")
        if best_link and best_score >= 2:
            return str(best_link)
    return None


def build() -> dict:
    letters = load_json(LETTERS_INDEX_PATH, [])
    index = filename_index()
    folders = folder_links()
    links: dict[str, str] = {}
    matched = 0
    for letter in letters if isinstance(letters, list) else []:
        source_document = str(letter.get("source_document") or "").replace("\\", "/")
        if not source_document:
            continue
        link = resolve_letter_link(letter, index, folders)
        if not link:
            continue
        links[source_document] = link
        links[Path(source_document).name.lower()] = link
        matched += 1
    return {
        "generated_at": now_iso(),
        "letter_count": len(letters) if isinstance(letters, list) else 0,
        "matched_count": matched,
        "links": dict(sorted(links.items())),
    }


def main() -> int:
    payload = build()
    write_json(OUTPUT_PATH, payload)
    print(
        f"Wrote {OUTPUT_PATH.relative_to(ROOT)} "
        f"({payload['matched_count']}/{payload['letter_count']} letters matched)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
