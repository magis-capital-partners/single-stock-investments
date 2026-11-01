#!/usr/bin/env python3
"""Reconcile public manager identities and the private eligible-document corpus.

Source membership and document references remain private. The public registry
contains public names/SEC identifiers only. Name similarity never joins CIKs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system/scripts"))
from build_managers_json import (
    _record,
    names_are_the_same_firm,
)
from fund_identity import identity_core
from investor_history import (
    ARCHIVE,
    OWNERSHIP,
    cik_map,
    now,
    table,
    write_json,
)
from ownership_common import slug
from vault_paths import letters_root

ROSTER = ROOT / "_system/reference/investors/public_roster.json"
ALIASES = ROOT / "_system/reference/investors/manager_aliases.json"
FILER_HISTORY = ROOT / "_system/reference/investors/historical_filers.json"


def historical_filers(path=None):
    path = Path(path) if path is not None else FILER_HISTORY
    return (
        json.loads(path.read_text(encoding="utf-8"))["filers"] if path.exists() else []
    )


def with_declared_filer_history(universe, sources=None):
    """Apply reviewed historical identifiers without guessing or merging owners."""
    sources = historical_filers() if sources is None else sources
    managers = {m["manager_id"]: m for m in universe["managers"]}
    owners = cik_map(list(managers.values()))
    for source in sources:
        owner = owners.get(str(int(source["primary_cik"])))
        if owner is None:
            continue
        former = str(int(source["cik"]))
        if former in owners and owners[former] != owner:
            raise ValueError("Historical filer already belongs to another manager")
        manager = managers[owner]
        entry = {
            k: v
            for k, v in source.items()
            if k not in {"primary_cik", "checkpoint_identity"}
        }
        previous = manager.get("cik_history", [])
        history = [
            r
            for r in previous
            if str(int(r.get("cik") if isinstance(r, dict) else r)) != former
        ]
        managers[owner] = {**manager, "cik_history": [*history, entry]}
        owners[former] = owner
    return {**universe, "managers": list(managers.values())}


LEGAL_WORDS = {
    "llc",
    "lp",
    "llp",
    "ltd",
    "limited",
    "inc",
    "plc",
    "ag",
    "gmbh",
    "corp",
    "corporation",
    "company",
    "co",
    "capital",
    "management",
    "investment",
    "investments",
    "partners",
    "advisors",
    "advisers",
    "asset",
    "fund",
    "funds",
    "holdings",
    "holding",
    "the",
    "and",
}


def identity_tokens(name):
    name = re.sub(r"\s*/\s*(?:ADV|[A-Za-z]{2,3})\s*$", "", name)
    name = re.sub(r"\bL[.\s]*L[.\s]*P\.?$", "LLP", name, flags=re.IGNORECASE)
    name = re.sub(r"\bL[.\s]*P\.?$", "LP", name, flags=re.IGNORECASE)
    return tuple(
        sorted(
            word
            for word in re.findall(r"[a-z0-9]+", name.lower())
            if word not in LEGAL_WORDS
        )
    )


def strict_name_match(left, right):
    a, b = identity_tokens(left), identity_tokens(right)
    return bool(a) and (a == b or "".join(a) == "".join(b))


def public_name_variants(name, variants, aliases):
    """Expand declared aliases in either direction, without fuzzy matching."""
    result = list(dict.fromkeys([name, *variants]))
    keys = {re.sub(r"[^a-z0-9]", "", value.lower()) for value in result if value}
    while True:
        before = len(result)
        for brand, names in aliases.items():
            group = [brand, *names]
            if not any(
                re.sub(r"[^a-z0-9]", "", value.lower()) in keys
                for value in group
                if value
            ):
                continue
            for value in group:
                if value and value not in result:
                    result.append(value)
                    keys.add(re.sub(r"[^a-z0-9]", "", value.lower()))
        if len(result) == before:
            return result


def reconcile_public_identities(universe, *, roster=None, aliases=None):
    """Retain verified public brands and link confirmed archived publishers.

    Only a unique existing SEC owner can receive an alias. Known filers are
    never combined by name, and fund vehicles retain their own identities.
    This also upgrades pinned snapshots created before aliases were retained.
    """
    if roster is None:
        roster = json.loads(ROSTER.read_text(encoding="utf-8"))["managers"]
    if aliases is None:
        aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    managers = {m["manager_id"]: dict(m) for m in universe["managers"]}
    public_names = defaultdict(set)
    preferred = {}
    for candidate in roster:
        variants = public_name_variants(candidate["firm"], [candidate["name"]], aliases)
        owners = [
            m
            for m in managers.values()
            if m.get("cik")
            and any(
                strict_name_match(variant, name)
                for variant in variants
                for name in [
                    m.get("display_name") or "",
                    m.get("sec_name") or "",
                    *m.get("public_aliases", []),
                ]
            )
        ]
        if len(owners) != 1:
            continue
        owner = owners[0]
        owner_id = owner["manager_id"]
        public_names[owner_id].update(
            name
            for name in [
                *variants,
                owner.get("display_name"),
                owner.get("sec_name"),
                *owner.get("public_aliases", []),
            ]
            if name
        )
        preferred.setdefault(owner_id, candidate["firm"])
    membership = universe.get("membership", {})
    redirects = {
        source: target
        for source, target in universe.get("manager_redirects", {}).items()
        if not managers.get(source, {}).get("cik")
        and managers.get(target, {}).get("cik")
    }
    for manager_id, manager in managers.items():
        if manager.get("cik"):
            continue
        if manager.get(
            "identity_status"
        ) != "document_header_confirmed" and "public_roster" not in membership.get(
            manager_id, []
        ):
            continue
        # A private publisher needs a declared public spelling, not a fuzzy
        # family-name match after removing words such as Capital or Advisors.
        key = re.sub(r"[^a-z0-9]", "", (manager.get("display_name") or "").lower())
        owners = [
            owner
            for owner, names in public_names.items()
            if key
            and any(key == re.sub(r"[^a-z0-9]", "", name.lower()) for name in names)
        ]
        if len(owners) == 1:
            redirects[manager_id] = owners[0]
    for owner, names in public_names.items():
        managers[owner]["public_aliases"] = sorted(names)
        managers[owner]["display_name"] = preferred[owner]
    members = defaultdict(set)
    for owner, tags in membership.items():
        target = redirects.get(owner, owner)
        if target in managers:
            members[target].update(tags)
    result = {
        **universe,
        "managers": [m for key, m in sorted(managers.items()) if key not in redirects],
        "source_ids": {
            source: redirects.get(owner, owner)
            for source, owner in universe.get("source_ids", {}).items()
        },
        "manager_redirects": redirects,
        "membership": {owner: sorted(tags) for owner, tags in members.items()},
        "identity_review": [
            r
            for r in universe.get("identity_review", [])
            if r.get("manager_id") not in redirects
        ],
    }
    return result


def current_disclosure_identity(document, universe):
    """Change the verified manager link while preserving fund/date/scope."""
    owner = None
    if document.get("source_kind") == "fund_disclosure":
        owner = universe.get("source_ids", {}).get(document.get("vehicle_id"))
    owner = owner or universe.get("manager_redirects", {}).get(
        document.get("manager_id")
    )
    return {**document, "manager_id": owner} if owner else document


class RosterParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.link = None
        self.parts = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href", "")
        if tag == "a" and re.search(r"holdings\.php\?m=", href, re.IGNORECASE):
            self.link, self.parts = href, []

    def handle_data(self, value):
        if self.link:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag == "a" and self.link:
            name = " ".join("".join(self.parts).split())
            self.rows.append({"name": name, "firm": name.split(" - ")[-1]})
            self.link = None


def fetch_roster():
    from urllib.request import Request, urlopen

    from sec_client import sec_user_agent

    url = "https://www.dataroma.com/m/managers.php"
    with urlopen(
        Request(url, headers={"User-Agent": sec_user_agent(), "Accept": "text/html"}),
        timeout=45,
    ) as response:
        raw = response.read().decode("utf-8")
    parser = RosterParser()
    parser.feed(raw)
    if len(parser.rows) < 20:
        raise ValueError("Roster response is incomplete; previous snapshot retained")
    return {
        "schema_version": 1,
        "as_of": now(),
        "source_url": url,
        "managers": parser.rows,
    }


def filer_catalog(raw_dir=ARCHIVE / "raw"):
    catalog = defaultdict(set)
    cache = ARCHIVE / "filer_catalog.json"
    if cache.exists():
        catalog.update(
            {
                key: set(values)
                for key, values in json.loads(cache.read_text(encoding="utf-8")).items()
            }
        )
    for path in sorted(raw_dir.glob("*.zip")):
        try:
            with zipfile.ZipFile(path) as zipped:
                submissions = {
                    r["ACCESSION_NUMBER"]: r["CIK"]
                    for r in table(zipped, "SUBMISSION.tsv")
                }
                for row in table(zipped, "COVERPAGE.tsv"):
                    cik = submissions.get(row["ACCESSION_NUMBER"])
                    if cik and row.get("FILINGMANAGER_NAME"):
                        catalog[row["FILINGMANAGER_NAME"]].add(f"{int(cik):010d}")
        except (ValueError, zipfile.BadZipFile, KeyError):
            continue
    write_json(cache, {key: sorted(values) for key, values in sorted(catalog.items())})
    return catalog


def match_cik(aliases, catalog, token_index=None):
    found = {}
    candidates = (
        set(catalog)
        if token_index is None
        else set().union(
            *(
                token_index.get(token, set())
                for alias in aliases
                for token in identity_tokens(alias)
            )
        )
    )
    for name in candidates:
        ciks = catalog[name]
        if any(strict_name_match(alias, name) for alias in aliases):
            for cik in ciks:
                found[cik] = name
    return next(iter(found.items())) if len(found) == 1 else None


def eligible_profiles(path):
    from investor_corpus import load_records

    rows = load_records(path)
    profiles = {}
    for row in rows:
        if row.get("letter_eligible") is not True:
            continue
        if row.get("document_type") not in {"investor_letter", "fund_report"}:
            continue
        original = row.get("fund_id") or ""
        name = (row.get("fund") or "").strip()
        core = identity_core(original, name)
        if not core or not name:
            continue
        profile = profiles.setdefault(
            core,
            {
                "name": name,
                "aliases": set(),
                "ids": set(),
                "documents": [],
                "identity_status": "unverified_document_identity",
            },
        )
        if profile["identity_status"] == "unverified_document_identity":
            ref = row.get("source_file") or ""
            suffix = ref.removeprefix("_system/reference/superinvestor-letters/")
            source = (path.parent / suffix).resolve()
            if source.is_relative_to(path.parent.resolve()) and source.is_file():
                with source.open("r", encoding="utf-8", errors="replace") as stream:
                    head = stream.read(5000)
                salutation = re.search(
                    r"\bdear\s+(?:(?:fellow|limited|valued)\s+)?(?:partners|investors|shareholders|co-investors)",
                    head,
                    re.IGNORECASE,
                )
                header = head[: salutation.start()] if salutation else head[:1200]
                publisher = re.findall(
                    r"(?m)^\s*([A-Z][A-Za-z0-9&'’., -]{1,80}?\b(?:Capital(?: Management)?|Asset Management|Investment Management|Investments|Partners|Advisors|Advisers|Funds|Fund))\s*(?:[|:–—-]|\d{4}|\(?Q[1-4]|$)",
                    header,
                )
                publisher = [
                    value.strip(" .,-")
                    for value in publisher
                    if not re.search(
                        r"\b(?:Dear|To Our|Quarter|Performance|Top|Returns|Holdings|Schedule)\b",
                        value,
                        re.IGNORECASE,
                    )
                ]
                if len(set(publisher)) == 1 and (
                    salutation or row.get("document_type") == "fund_report"
                ):
                    profile["aliases"].add(publisher[0])
                    profile["name"] = publisher[0]
                    profile["identity_status"] = "document_header_confirmed"
                compact = re.sub(r"[^a-z0-9]", "", head.lower())
                brand = re.sub(r"[^a-z0-9]", "", name.lower())
                greeting = re.search(
                    r"\bdear\s+(?:partners|investors|shareholders|co-investors)|letter\s+to\s+(?:partners|investors|shareholders)",
                    head,
                    re.IGNORECASE,
                )
                if (
                    brand
                    and len(brand) >= 4
                    and brand in compact
                    and (greeting or row.get("document_type") == "fund_report")
                ):
                    profile["identity_status"] = "document_header_confirmed"
            if row.get("fund_resolution") == "curated":
                profile["identity_status"] = "document_header_confirmed"
        profile["aliases"].add(name)
        profile["ids"].add(original)
        profile["documents"].append(
            {
                "ref": row.get("source_file"),
                "period": row.get("quarter"),
                "date": row.get("letter_date"),
            }
        )
    return profiles


def compile_universe(
    *,
    registry_path=OWNERSHIP / "managers.json",
    roster_path=ROSTER,
    corpus_path=None,
    catalog=None,
    aliases_path=ALIASES,
    resolve_public=False,
):
    document = json.loads(registry_path.read_text(encoding="utf-8"))
    public = with_declared_filer_history(document)["managers"]
    catalog = catalog if catalog is not None else filer_catalog()
    aliases = (
        json.loads(aliases_path.read_text(encoding="utf-8"))
        if aliases_path.exists()
        else {}
    )
    by_id = {r["manager_id"]: r for r in public}
    # A declared former filer is owned by the same canonical manager. Searching
    # older legal names must not create a second owner for that historical CIK.
    by_cik = {cik: by_id[owner] for cik, owner in cik_map(public).items()}
    public_candidates = json.loads(roster_path.read_text(encoding="utf-8"))["managers"]
    preferred = {}
    if resolve_public:
        from urllib.parse import urlencode

        from build_managers_json import pick_efts_cik
        from ownership_common import fetch_submissions
        from sec_client import get_json

        for candidate in public_candidates:
            variants = public_name_variants(candidate["firm"], [], aliases)
            if match_cik(variants, catalog):
                continue
            for variant in variants:
                try:
                    params = {
                        "q": f'"{variant}"',
                        "forms": "13F-HR",
                        "dateRange": "custom",
                        "startdt": f"{int(now()[:4]) - 2}-01-01",
                        "enddt": now()[:10],
                    }
                    hits = (
                        get_json(
                            "https://efts.sec.gov/LATEST/search-index?"
                            + urlencode(params)
                        )
                        .get("hits", {})
                        .get("hits", [])
                    )
                    strict_hits = [
                        h
                        for h in hits
                        if any(
                            strict_name_match(variant, re.sub(r"\s*\(CIK.*", "", n))
                            for n in h.get("_source", {}).get("display_names", [])
                        )
                    ]
                    picked = pick_efts_cik(variant, strict_hits)
                    if picked:
                        cik, _name = picked
                        live = fetch_submissions(cik).get("name", "")
                        if names_are_the_same_firm(variant, live):
                            catalog.setdefault(live, set()).add(cik)
                            preferred[candidate["firm"]] = (cik, live)
                            print(
                                f"Verified public filer {candidate['firm']}", flush=True
                            )
                            break
                except (OSError, ValueError, KeyError) as exc:
                    print(
                        f"Public identity lookup pending for {candidate['firm']}: {exc}",
                        flush=True,
                    )
    token_index = defaultdict(set)
    for legal_name in catalog:
        for token in identity_tokens(legal_name):
            token_index[token].add(legal_name)
    unresolved = []
    members = defaultdict(set)

    def resolve(name, variants, membership, *, private=False):
        variants = public_name_variants(name, variants, aliases)
        exact = [
            r
            for r in public
            if any(
                strict_name_match(v, r["display_name"])
                or strict_name_match(v, r.get("sec_name") or "")
                for v in variants
            )
        ]
        picked = preferred.get(name) or match_cik(variants, catalog, token_index)
        existing = by_cik.get(str(int(picked[0]))) if picked else None
        linked_exact = [r for r in exact if r.get("cik")]
        fallback = (
            linked_exact[0]
            if len(linked_exact) == 1
            else exact[0]
            if len(exact) == 1
            else None
        )
        if (
            existing is None
            and fallback is not None
            and (not picked or not fallback.get("cik"))
        ):
            existing = fallback
            if picked:
                existing.update(
                    {
                        "cik": picked[0],
                        "sec_name": picked[1],
                        "book": "full",
                        "files_13f": True,
                        "verified_at": now()[:10],
                    }
                )
                by_cik[str(int(picked[0]))] = existing
        if existing:
            # A formerly unlinked roster brand must resolve to its existing
            # legal manager, rather than survive as a second empty profile.
            for duplicate in exact:
                if duplicate is not existing and not duplicate.get("cik"):
                    public.remove(duplicate)
                    by_id.pop(duplicate["manager_id"], None)
            members[existing["manager_id"]].add(membership)
            if not existing.get("cik"):
                unresolved.append(
                    {
                        "manager_id": existing["manager_id"],
                        "name": name,
                        "reason": "SEC identity not uniquely linked",
                    }
                )
            return existing
        manager_id = slug(name)
        if manager_id in by_id:
            manager_id += "-" + (picked[0][-5:] if picked else "unlinked")
        display = picked[1] if private and picked else name
        record = _record(
            manager_id,
            display,
            sec_name=picked[1] if picked else "",
            cik=picked[0] if picked else None,
            roles=["active"],
            book="full" if picked else "none",
            verified_at=now()[:10] if picked else None,
        )
        if private and not picked:
            record["identity_status"] = "unverified_document_identity"
        else:
            public.append(record)
            by_id[manager_id] = record
        if picked:
            by_cik[str(int(picked[0]))] = record
        members[manager_id].add(membership)
        if not picked:
            unresolved.append(
                {
                    "manager_id": manager_id,
                    "name": name,
                    "reason": "SEC identity not uniquely linked",
                }
            )
        return record

    for candidate in public_candidates:
        resolve(candidate["firm"], [candidate["name"]], "public_roster")
    profiles = (
        eligible_profiles(corpus_path) if corpus_path and corpus_path.exists() else {}
    )
    private_records = {}
    source_ids = {}
    for core, profile in sorted(profiles.items()):
        record = resolve(
            profile["name"], list(profile["aliases"]), "document_corpus", private=True
        )
        if not record.get("cik") and "public_roster" not in members.get(
            record["manager_id"], set()
        ):
            record["identity_status"] = profile["identity_status"]
        private_records[record["manager_id"]] = record
        for original in profile["ids"]:
            source_ids[original] = record["manager_id"]
    public.sort(key=lambda r: r["manager_id"])
    document["updated_at"] = now()
    registry_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    universe = {**by_id, **private_records}
    unresolved = list(
        {
            (r["manager_id"], r["reason"]): r
            for r in unresolved
            if r["manager_id"] in universe and not universe[r["manager_id"]].get("cik")
        }.values()
    )
    result = {
        "schema_version": 1,
        "generated_at": now(),
        "managers": sorted(universe.values(), key=lambda r: r["manager_id"]),
        "source_ids": source_ids,
        "membership": {k: sorted(v) for k, v in members.items()},
        "identity_review": unresolved,
        "eligible_profile_count": len(profiles),
        "public_roster_count": len(public_candidates),
    }
    result = reconcile_public_identities(
        result, roster=public_candidates, aliases=aliases
    )
    write_json(ARCHIVE / "universe.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-roster", action="store_true")
    parser.add_argument("--resolve-public", action="store_true")
    parser.add_argument("--corpus", type=Path, default=letters_root() / "insights.json")
    args = parser.parse_args()
    if args.refresh_roster:
        try:
            write_json(ROSTER, fetch_roster())
        except (OSError, ValueError, KeyError) as exc:
            if not ROSTER.exists():
                raise
            print(f"Public roster refresh failed; using dated snapshot: {exc}")
    result = compile_universe(
        corpus_path=args.corpus, resolve_public=args.resolve_public
    )
    print(
        json.dumps(
            {
                "managers": len(result["managers"]),
                "identity_review": len(result["identity_review"]),
                "eligible_profiles": result["eligible_profile_count"],
            }
        )
    )


if __name__ == "__main__":
    main()
