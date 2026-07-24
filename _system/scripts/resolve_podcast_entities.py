#!/usr/bin/env python3
"""Multi-signal podcast guest / company / officer → ticker + persona resolver."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

PODCASTS_CFG = ROOT / "_system" / "reference" / "podcasts"
GUEST_REG = PODCASTS_CFG / "podcast_guest_registry.json"
ALIAS_OVERRIDES = PODCASTS_CFG / "company_alias_overrides.json"
OFFICER_DIR = PODCASTS_CFG / "officer_directory.json"
SECURITY_MASTER = ROOT / "_system" / "reference" / "securities" / "security_master.json"

TITLE_RE = re.compile(
    r"\b(CEO|CFO|COO|CTO|Chief\s+(?:Executive|Financial|Operating|Product|Technology)\s+Officer|"
    r"Founder|Co-Founder|Chairman|President|Managing\s+Director|Partner)\b",
    re.I,
)
# Company capture stops before common English continuations / role phrases.
_COMPANY_STOP = (
    r"(?=\s+(?:on|and|with|who|that|which|about|discuss|joins?|from|in|for|to|of|"
    r"the|a|an|podcast|episode|interview|live|casino)\b|[.,;:!?|]|$)"
)
OF_AT_RE = re.compile(
    r"(?P<title>" + TITLE_RE.pattern + r")\s+(?:of|at|for)\s+"
    r"(?P<company>[A-Z][\w.&'\-]{1,40}(?:\s+[A-Z][\w.&'\-]{1,40}){0,5})"
    + _COMPANY_STOP,
    re.I,
)
PERSON_COMMA_TITLE_RE = re.compile(
    r"(?P<person>[A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){0,3})\s*,\s*"
    r"(?P<title>" + TITLE_RE.pattern + r")\s+(?:of|at|for)\s+"
    r"(?P<company>[A-Z][\w.&'\-]{1,40}(?:\s+[A-Z][\w.&'\-]{1,40}){0,5})"
    + _COMPANY_STOP,
    re.I,
)

# Short / noisy tokens that must not substring-match inside unrelated words.
_SHORT_ALIAS_MIN = 4
_BANNED_SOLO_ALIASES = {
    "tci",
    "orbis",
    "nomad",
    "marks",
    "stahl",
    "the memo",
    "soft dollar",
    "greenlight",
    "himalaya",
    "fairfax",
    "coatue",
    "giverny",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _contains_any(text: str, needles: list[str]) -> bool:
    n = _norm(text)
    return any(_norm(x) in n for x in needles if x)


def _alias_matches(haystack_norm: str, alias_norm: str) -> bool:
    """Word-boundary match; reject tiny / banned solo aliases unless exact phrase."""
    if not alias_norm or not haystack_norm:
        return False
    if alias_norm in _BANNED_SOLO_ALIASES and len(alias_norm) < 8:
        # Require full phrase already covered by longer aliases; skip solo short tokens.
        return False
    if len(alias_norm) < _SHORT_ALIAS_MIN:
        return False
    # Word-boundary via spaces in normalized text
    padded = f" {haystack_norm} "
    needle = f" {alias_norm} "
    return needle in padded


class PodcastEntityResolver:
    def __init__(self) -> None:
        self.guests = (load_json(GUEST_REG).get("guests") or [])
        alias_doc = load_json(ALIAS_OVERRIDES)
        self.aliases = alias_doc.get("aliases") or []
        self.collision_guards = alias_doc.get("collision_guards") or []
        self.officers = (load_json(OFFICER_DIR).get("officers") or [])
        master = load_json(SECURITY_MASTER)
        self.master: dict[str, dict] = master if isinstance(master, dict) else {}
        self._guest_alias_index: list[tuple[str, dict]] = []
        for g in self.guests:
            for a in (g.get("aliases") or []) + (g.get("fund_aliases") or []):
                an = _norm(a)
                if not an or len(an) < _SHORT_ALIAS_MIN:
                    continue
                # Skip show-name aliases that cause every episode of a host show to match
                if an in {"chai with pabrai", "the memo", "marks memo"}:
                    continue
                self._guest_alias_index.append((an, g))
        self._guest_alias_index.sort(key=lambda x: -len(x[0]))

    def match_guests(self, text: str) -> list[dict]:
        n = _norm(text)
        hits: list[dict] = []
        seen: set[str] = set()
        for alias_n, g in self._guest_alias_index:
            if not _alias_matches(n, alias_n):
                continue
            gid = g["guest_id"]
            if gid in seen:
                continue
            seen.add(gid)
            hits.append(
                {
                    "guest_id": gid,
                    "display": g.get("display"),
                    "tier": g.get("tier"),
                    "persona_ids": g.get("persona_ids") or [],
                    "matched_alias": alias_n,
                }
            )
        return hits

    def _collision_blocks(self, ticker: str, context: str) -> bool:
        for guard in self.collision_guards:
            if str(guard.get("ticker") or "").upper() != str(ticker).upper():
                continue
            if _contains_any(context, guard.get("reject_if_context_any") or []):
                return True
        return False

    def resolve_company_phrase(self, phrase: str, context: str = "") -> dict | None:
        phrase_n = _norm(phrase)
        ctx = f"{phrase} {context}"
        # Manual overrides first (Evolution Gaming etc.)
        for row in self.aliases:
            phrases = [_norm(p) for p in (row.get("phrases") or [])]
            if not any(p and (p in phrase_n or phrase_n in p) for p in phrases):
                continue
            req = row.get("context_require_any") or []
            if req and not _contains_any(ctx, req) and not _contains_any(phrase, req):
                # Allow if phrase itself is an exact override phrase
                if not any(p == phrase_n for p in phrases):
                    continue
            ticker = row.get("ticker")
            if ticker and self._collision_blocks(str(ticker), ctx):
                continue
            return {
                "company_key": row.get("company_key"),
                "ticker": ticker,
                "in_book": bool(row.get("in_book")),
                "near_universe": bool(row.get("near_universe")),
                "source": "alias_override",
                "matched_phrase": phrase,
            }
        # security_master: only in-book names (avoid CEO-of-FROM junk tickers)
        best = None
        best_len = 0
        for ticker, meta in self.master.items():
            if not isinstance(meta, dict):
                continue
            if not meta.get("in_book"):
                continue
            names = [meta.get("name"), *(meta.get("aliases") or [])]
            for name in names:
                nn = _norm(str(name or ""))
                if not nn or len(nn) < 5:
                    continue
                if _alias_matches(phrase_n, nn) or _alias_matches(nn, phrase_n) or nn == phrase_n:
                    if self._collision_blocks(ticker, ctx):
                        continue
                    if len(nn) > best_len:
                        best_len = len(nn)
                        best = {
                            "company_key": _norm(str(name)),
                            "ticker": ticker,
                            "in_book": True,
                            "near_universe": False,
                            "source": "security_master",
                            "matched_phrase": phrase,
                        }
        return best

    def match_officers(self, text: str) -> list[dict]:
        n = _norm(text)
        hits: list[dict] = []
        seen: set[str] = set()
        for off in self.officers:
            names = [off.get("person_name"), *(off.get("name_aliases") or [])]
            for name in names:
                nn = _norm(str(name or ""))
                if not nn or nn not in n:
                    continue
                key = f"{off.get('person_name')}|{off.get('ticker')}"
                if key in seen:
                    continue
                seen.add(key)
                # Prefer corroboration with company alias in same text
                company_hit = any(_norm(c) in n for c in (off.get("company_aliases") or []) if c)
                score = 0.9 if company_hit else 0.7
                hits.append(
                    {
                        "person_name": off.get("person_name"),
                        "titles": off.get("titles") or [],
                        "ticker": off.get("ticker"),
                        "company_key": off.get("company_key"),
                        "company_aliases": off.get("company_aliases") or [],
                        "in_book": bool(off.get("in_book")),
                        "near_universe": not bool(off.get("in_book")),
                        "score": score,
                        "source": "officer_directory",
                    }
                )
        return hits

    def extract_title_company_pairs(self, text: str) -> list[dict]:
        out: list[dict] = []
        for m in PERSON_COMMA_TITLE_RE.finditer(text or ""):
            out.append(
                {
                    "person": m.group("person").strip(),
                    "title": m.group("title").strip(),
                    "company": m.group("company").strip(" .,;"),
                }
            )
        for m in OF_AT_RE.finditer(text or ""):
            out.append(
                {
                    "person": None,
                    "title": m.group("title").strip(),
                    "company": m.group("company").strip(" .,;"),
                }
            )
        return out

    def resolve_episode(
        self,
        *,
        title: str = "",
        description: str = "",
        transcript_head: str = "",
        show_title: str = "",
        host_guest_ids: list[str] | None = None,
    ) -> dict:
        # Guests: title + description + transcript only (not show_title — avoids host-show spam)
        guest_blob = "\n".join(x for x in [title, description, transcript_head] if x)
        # Officers / companies: include show_title for context phrases
        blob = "\n".join(x for x in [show_title, title, description, transcript_head] if x)
        guests = self.match_guests(guest_blob)
        host_ids = set(host_guest_ids or [])
        # Host shows: tag host matches as show_host (so discovery can cap host-only eps)
        if host_ids:
            for g in guests:
                if g.get("guest_id") in host_ids:
                    g["matched_alias"] = "show_host"
                    g["is_show_host"] = True
            by_id = {g.get("guest_id"): g for g in self.guests}
            seen = {g["guest_id"] for g in guests}
            for gid in host_ids:
                if gid in seen:
                    continue
                g = by_id.get(gid)
                if not g:
                    continue
                guests.append(
                    {
                        "guest_id": gid,
                        "display": g.get("display"),
                        "tier": g.get("tier"),
                        "persona_ids": g.get("persona_ids") or [],
                        "matched_alias": "show_host",
                        "is_show_host": True,
                    }
                )
                seen.add(gid)
        officers = self.match_officers(blob)
        pairs = self.extract_title_company_pairs(blob)
        companies: list[dict] = []
        ambiguous: list[dict] = []
        seen_keys: set[str] = set()

        for pair in pairs:
            company = pair.get("company") or ""
            resolved = self.resolve_company_phrase(company, blob)
            if resolved:
                key = str(resolved.get("ticker") or resolved.get("company_key"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    companies.append({**resolved, "title": pair.get("title"), "person": pair.get("person")})
            else:
                ambiguous.append(
                    {
                        "reason": "title_company_unresolved",
                        "person": pair.get("person"),
                        "title": pair.get("title"),
                        "company": company,
                    }
                )

        # Also try company phrases from alias list present in text
        for row in self.aliases:
            for phrase in row.get("phrases") or []:
                pn = _norm(phrase)
                if pn and _alias_matches(_norm(blob), pn):
                    resolved = self.resolve_company_phrase(phrase, blob)
                    if resolved:
                        key = str(resolved.get("ticker") or resolved.get("company_key"))
                        if key not in seen_keys:
                            seen_keys.add(key)
                            companies.append(resolved)

        tickers: list[str] = []
        for c in companies:
            t = c.get("ticker")
            if t and t not in tickers:
                tickers.append(str(t))
        for o in officers:
            t = o.get("ticker")
            if t and t not in tickers:
                tickers.append(str(t))

        score = 0.0
        if guests:
            score = max(score, 0.85)
        if officers:
            score = max(score, max(float(o.get("score") or 0) for o in officers))
        if companies:
            score = max(score, 0.8 if any(c.get("source") == "alias_override" for c in companies) else 0.65)

        officer_dir_hit = bool(officers)
        title_company_universe = any(
            c.get("title") and (c.get("in_book") or c.get("source") == "alias_override")
            for c in companies
        )

        return {
            "guests": guests,
            "officers": officers,
            "companies": companies,
            "tickers": tickers,
            "ambiguous": ambiguous,
            "score": score,
            "has_pz_guest": any(g.get("tier") == "zone" or g.get("persona_ids") for g in guests)
            or any(g.get("tier") == "guest_only" for g in guests),
            "has_officer_hit": officer_dir_hit or title_company_universe,
            "in_book_any": any(bool(c.get("in_book")) for c in companies)
            or any(bool(o.get("in_book")) for o in officers),
            "near_universe_any": any(bool(c.get("near_universe")) for c in companies)
            or any(bool(o.get("near_universe")) for o in officers),
            "resolve_trace": {
                "pair_count": len(pairs),
                "guest_count": len(guests),
                "officer_count": len(officers),
                "company_count": len(companies),
            },
        }


def resolve_text(title: str, description: str = "", transcript_head: str = "", show_title: str = "") -> dict:
    return PodcastEntityResolver().resolve_episode(
        title=title,
        description=description,
        transcript_head=transcript_head,
        show_title=show_title,
    )


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--show", default="")
    args = p.parse_args()
    result = resolve_text(args.title, args.description, show_title=args.show)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
