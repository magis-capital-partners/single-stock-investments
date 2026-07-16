#!/usr/bin/env python3
"""Corpus-level canonical identity resolution for superinvestor letters.

Filename-derived identities are useful fallbacks, but a corpus inevitably
contains period stamps, document titles, hashes, spacing variants, and OCR
typos.  This module resolves those aliases only when the whole corpus provides
enough evidence, then emits a complete audit trail for every merge.
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from copy import deepcopy
from urllib.parse import unquote


PERIOD_RE = re.compile(
    r"(?i)(?:"
    r"(?:19|20)?\d{2}q[1-4]|"          # 2018q1, 18q1
    r"0?[1-4]q(?:19|20)?\d{2}|"       # 1q18, 01q2018
    r"q[1-4](?:19|20)?\d{2}|"         # q118, q12018
    r"[12]h(?:19|20)?\d{2}|"          # 1h18
    r"h[12](?:19|20)?\d{2}|"          # h118
    r"q(?:uarter)?ly?\s*(?:19|20)\d{2}|"
    r"qlet(?:ter)?\s*(?:19|20)\d{2}"
    r")"
)
DATE_RE = re.compile(
    r"(?i)(?<![a-z0-9])(?:19|20)\d{2}(?:[._/-]\d{1,2}){0,2}(?![a-z0-9])|"
    r"(?<![a-z0-9])\d{1,2}[._/-]\d{1,2}[._/-]\d{2,4}(?![a-z0-9])"
)
MONTH_YEAR_RE = re.compile(
    r"(?i)\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)[._ -]?(?:19|20)?\d{2}\b"
)
HASH_RE = re.compile(r"(?i)(?<![a-z0-9])[0-9a-f]{8,}(?![a-z0-9])")
RANDOM_SUFFIX_RE = re.compile(r"(?i)(?<![a-z0-9])(?=[a-z0-9]{8,}\b)(?=[a-z0-9]*\d)[a-z0-9]+\b")
VERSION_RE = re.compile(
    r"(?i)\b(?:vol(?:ume)?\.?\s*\d+|ver(?:sion)?\s*\d+|v?final\d*|"
    r"\d+(?:st|nd|rd|th)|\d+\s*(?:year|yr)s?|year\s*end|yearend)\b"
)

NOISE_TOKENS = {
    "annual", "capital", "comment", "commentary", "confidential", "copy",
    "deck", "draft", "fact", "factsheet", "final", "fund", "funds", "fy",
    "inc", "investor", "investors", "letter", "letters", "llc", "lp", "ltd",
    "management", "memo", "mgmt", "monthly", "news", "newsletter", "partner",
    "partners", "plc", "presentation", "qtr", "quarter", "quarterly", "report",
    "review", "semiannual", "shareholder", "shareholders", "sheet", "snapshot",
    "the", "to", "update", "v", "version", "vol", "volume", "year", "years",
    "first", "second", "third", "fourth", "1st", "2nd", "3rd", "4th",
}
MONTH_TOKENS = {
    "jan", "january", "feb", "february", "mar", "march", "apr", "april", "may",
    "jun", "june", "jul", "july", "aug", "august", "sep", "sept", "september",
    "oct", "october", "nov", "november", "dec", "december",
}

# A recurring exact single-word identity may anchor titled documents.  These
# common words cannot safely identify a fund family on their own.
GENERIC_SINGLE_ANCHORS = {
    "active", "alpha", "asset", "blue", "bridge", "company", "david", "east",
    "eagle", "equity", "first", "global", "green", "growth", "half", "health",
    "investment", "investments", "market", "master", "new", "north", "oak",
    "opportunity", "point", "red", "research", "select", "series", "south",
    "summary", "value", "west", "white", "world",
}
ROMAN_TOKENS = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}

# Explicit OCR / slug twins that should share one fund_id (not multi-strategy shops).
CURATED_ALIAS_PAIRS: list[tuple[str, str]] = [
    ("silver-ring-value", "silverringvaluepartners"),
    ("silver-ring-value-partners", "silverringvaluepartners"),
    ("laughing-water", "lwc-end"),
    ("laughing-water-capital", "lwc-end"),
    ("manor-road", "mrc"),
    ("manor-road-capital", "mrc"),
    ("fairlight", "farlight"),
    ("masiff", "massif"),
    ("massif-capital", "masiff-capital"),
]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return value or "unknown-fund"


def identity_core(fund_id: str | None, fund: str | None = None) -> str:
    """Return the deterministic noise-free signature for one raw identity."""
    value = html.unescape(unquote(str(fund or fund_id or ""))).replace("&", " and ")
    value = re.sub(r"(?i)\bL\s*[.]\s*P\s*[.]?\b", " lp ", value)
    value = re.sub(r"(?i)\bL\s*[.]\s*L\s*[.]\s*C\s*[.]?\b", " llc ", value)
    value = MONTH_YEAR_RE.sub(" ", value)
    value = PERIOD_RE.sub(" ", value)
    value = DATE_RE.sub(" ", value)
    value = HASH_RE.sub(" ", value)
    value = RANDOM_SUFFIX_RE.sub(" ", value)
    value = VERSION_RE.sub(" ", value)
    tokens = []
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        if token in NOISE_TOKENS or token in MONTH_TOKENS or token.isdigit():
            continue
        if len(token) == 1:
            continue
        if tokens and tokens[-1] == token:
            continue
        tokens.append(token)
    return "-".join(tokens) or slugify(str(fund_id or fund or "unknown-fund"))


def _edit_distance_one(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if left == right:
        return True
    if len(left) > len(right):
        left, right = right, left
    i = j = differences = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        differences += 1
        if differences > 1:
            return False
        if len(left) == len(right):
            i += 1
        j += 1
    return differences + int(j < len(right)) <= 1


def _safe_spelling_variant(left: str, right: str, letter_counts: dict[str, int]) -> bool:
    """Recognize spacing, plural, and high-confidence one-character variants."""
    compact_left = left.replace("-", "")
    compact_right = right.replace("-", "")
    if compact_left == compact_right:
        return True
    lt = left.split("-")
    rt = right.split("-")
    if len(lt) != len(rt):
        return False
    if any(a in ROMAN_TOKENS or b in ROMAN_TOKENS for a, b in zip(lt, rt)):
        return False
    changed = [(a, b) for a, b in zip(lt, rt) if a != b]
    if len(changed) != 1:
        return False
    a, b = changed[0]
    if min(len(a), len(b)) < 6 or a[:3] != b[:3]:
        return False
    if max(letter_counts.get(left, 0), letter_counts.get(right, 0)) < 3:
        return False
    return (a.rstrip("s") == b.rstrip("s")) or _edit_distance_one(a, b)


class _UnionFind:
    def __init__(self, values: set[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[b] = a


def _display_name(canonical_id: str, raw_names: Counter[str]) -> str:
    """Build a stable label from the clean identity, never the noisy filename."""
    words = canonical_id.split("-")
    acronyms = {"bbcm", "cof", "ecp", "erbof", "jab", "kedm", "mcn", "nb", "ni", "nrc", "splp", "tpep"}
    return " ".join(
        word.upper() if word in acronyms else (word.lower() if word == "and" else word.capitalize())
        for word in words
    )


def consolidate_letter_funds(letters: list[dict], *, _verify: bool = True) -> tuple[list[dict], dict]:
    """Canonicalize every fund identity and return letters plus an audit."""
    if not letters:
        return [], {
            "schema_version": 1,
            "source_profiles": 0,
            "canonical_profiles": 0,
            "profiles_consolidated": 0,
            "alias_groups": [],
            "residual_redundancy_groups": 0,
        }

    rows = []
    core_stats: dict[str, dict] = defaultdict(
        lambda: {"letters": 0, "quarters": set(), "ids": set(), "names": Counter()}
    )
    source_ids: set[str] = set()
    for letter in letters:
        raw_id = str(letter.get("fund_id") or letter.get("fund") or "unknown-fund")
        raw_name = str(letter.get("fund") or raw_id)
        core = identity_core(raw_id, raw_name)
        rows.append((letter, raw_id, raw_name, core))
        source_ids.add(raw_id)
        stats = core_stats[core]
        stats["letters"] += 1
        stats["quarters"].add(letter.get("quarter") or "unknown")
        stats["ids"].add(raw_id)
        stats["names"][raw_name] += 1

    methods: dict[tuple[str, str], str] = {}
    union = _UnionFind(set(core_stats))

    # Curated OCR / slug twins (not multi-strategy shops)
    for left_id, right_id in CURATED_ALIAS_PAIRS:
        left_cores = {
            core
            for _letter, rid, _name, core in rows
            if rid.lower() == left_id or core == left_id or identity_core(rid) == left_id
        }
        right_cores = {
            core
            for _letter, rid, _name, core in rows
            if rid.lower() == right_id or core == right_id or identity_core(rid) == right_id
        }
        for lc in left_cores:
            for rc in right_cores:
                if lc != rc and lc in core_stats and rc in core_stats:
                    union.union(lc, rc)
                    methods[(lc, rc)] = "curated_alias"

    # A recurrent exact identity can safely absorb titled/profile-specific
    # variants beneath it.  Longest anchors win; generic single words cannot.
    anchors = {
        core
        for core, stats in core_stats.items()
        if stats["letters"] >= 2
        and len(stats["quarters"]) >= 2
        and (
            len(core.split("-")) >= 2
            or (
                len(core) >= 4
                and stats["letters"] >= 3
                and core not in GENERIC_SINGLE_ANCHORS
            )
        )
    }
    for core in sorted(core_stats, key=lambda value: (len(value), value), reverse=True):
        candidates = [anchor for anchor in anchors if core != anchor and core.startswith(anchor + "-")]
        if not candidates:
            continue
        anchor = max(candidates, key=lambda value: (len(value), value))
        union.union(anchor, core)
        methods[(anchor, core)] = "recurring_prefix"

    # Resolve spacing and conservative spelling variants after the exact and
    # prefix evidence is known.  Bucket by the first three compact characters
    # so this remains fast across thousands of identities.
    buckets: dict[str, list[str]] = defaultdict(list)
    for core in core_stats:
        compact = core.replace("-", "")
        if len(compact) >= 5:
            buckets[compact[:3]].append(core)
    letter_counts = {core: stats["letters"] for core, stats in core_stats.items()}
    for candidates in buckets.values():
        candidates.sort()
        for idx, left in enumerate(candidates):
            for right in candidates[idx + 1:]:
                if _safe_spelling_variant(left, right, letter_counts):
                    union.union(left, right)
                    methods[(left, right)] = "spacing_or_spelling"

    components: dict[str, set[str]] = defaultdict(set)
    for core in core_stats:
        components[union.find(core)].add(core)

    canonical_for_core: dict[str, str] = {}
    for members in components.values():
        canonical = min(
            members,
            key=lambda core: (
                -core_stats[core]["letters"],
                -len(core_stats[core]["quarters"]),
                len(core),
                core,
            ),
        )
        for member in members:
            canonical_for_core[member] = canonical

    canonical_names: dict[str, Counter[str]] = defaultdict(Counter)
    for _letter, _raw_id, raw_name, core in rows:
        canonical_names[canonical_for_core[core]][raw_name] += 1

    output = []
    aliases_by_canonical: dict[str, dict] = defaultdict(
        lambda: {"ids": set(), "names": set(), "cores": set(), "letters": 0, "quarters": set()}
    )
    for letter, raw_id, raw_name, core in rows:
        canonical_id = canonical_for_core[core]
        canonical_name = _display_name(canonical_id, canonical_names[canonical_id])
        updated = deepcopy(letter)
        if raw_id != canonical_id:
            updated["fund_alias_id"] = raw_id
        if raw_name != canonical_name:
            updated["fund_alias"] = raw_name
        updated["fund_id"] = canonical_id
        updated["fund"] = canonical_name
        if raw_id != canonical_id or raw_name != canonical_name:
            updated["fund_resolution"] = "canonicalized"
        output.append(updated)
        group = aliases_by_canonical[canonical_id]
        group["ids"].add(raw_id)
        group["names"].add(raw_name)
        group["cores"].add(core)
        group["letters"] += 1
        group["quarters"].add(letter.get("quarter") or "unknown")

    audit_groups = []
    for canonical_id, group in aliases_by_canonical.items():
        if len(group["ids"]) <= 1 and len(group["cores"]) <= 1:
            continue
        component_methods = sorted(
            {
                method
                for (left, right), method in methods.items()
                if left in group["cores"] and right in group["cores"]
            }
        )
        if len(group["ids"]) > 1 and len(group["cores"]) == 1:
            component_methods.insert(0, "exact_noise_signature")
        audit_groups.append(
            {
                "fund_id": canonical_id,
                "fund": _display_name(canonical_id, canonical_names[canonical_id]),
                "letter_count": group["letters"],
                "quarter_count": len(group["quarters"]),
                "aliases": sorted(group["ids"]),
                "alias_names": sorted(group["names"]),
                "identity_cores": sorted(group["cores"]),
                "methods": component_methods,
            }
        )
    audit_groups.sort(key=lambda row: (-len(row["aliases"]), -row["letter_count"], row["fund_id"]))

    # Exact-signature uniqueness is one half of the exhaustive regression gate.
    residual_signatures: dict[str, set[str]] = defaultdict(set)
    for letter in output:
        residual_signatures[identity_core(letter.get("fund_id"), letter.get("fund"))].add(
            str(letter.get("fund_id"))
        )
    residual = [sorted(values) for values in residual_signatures.values() if len(values) > 1]
    if _verify:
        verified_output, verified_audit = consolidate_letter_funds(output, _verify=False)
        changed_again = [
            before.get("fund_id")
            for before, after in zip(output, verified_output)
            if before.get("fund_id") != after.get("fund_id") or before.get("fund") != after.get("fund")
        ]
    else:
        verified_audit = {"canonical_profiles": len(aliases_by_canonical)}
        changed_again = []
    audit = {
        "schema_version": 1,
        "source_profiles": len(source_ids),
        "canonical_profiles": len(aliases_by_canonical),
        "profiles_consolidated": len(source_ids) - len(aliases_by_canonical),
        "alias_group_count": len(audit_groups),
        "alias_groups": audit_groups,
        "residual_redundancy_groups": len(residual),
        "residual_redundancies": residual,
        "idempotent": not changed_again
        and verified_audit.get("canonical_profiles") == len(aliases_by_canonical),
        "second_pass_changes": sorted(set(changed_again)),
    }
    return output, audit


def consolidate_letter_funds_stable(
    letters: list[dict], *, max_passes: int = 5
) -> tuple[list[dict], dict]:
    """Iterate corpus identity resolution until aliases reach a fixed point.

    Exact document deduplication can remove the recurrence that previously
    anchored one filename alias.  A bounded fixed-point pass makes identity
    resolution independent of duplicate source counts while retaining the
    existing residual and idempotence gates.
    """
    current = letters
    audits: list[dict] = []
    for pass_number in range(1, max_passes + 1):
        current, audit = consolidate_letter_funds(current)
        audits.append(audit)
        if not audit.get("residual_redundancy_groups") and audit.get("idempotent"):
            return current, {
                **audit,
                "convergence_passes": pass_number,
                "pass_summaries": [
                    {
                        "pass": idx + 1,
                        "canonical_profiles": row.get("canonical_profiles"),
                        "profiles_consolidated": row.get("profiles_consolidated"),
                        "residual_redundancy_groups": row.get("residual_redundancy_groups"),
                        "idempotent": row.get("idempotent"),
                    }
                    for idx, row in enumerate(audits)
                ],
            }
    raise RuntimeError(
        f"Fund identity consolidation did not converge after {max_passes} passes"
    )
