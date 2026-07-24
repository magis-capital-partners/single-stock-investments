#!/usr/bin/env python3
"""Discover podcast episodes from watchlist RSS and Podcast Index guest/officer search."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

from vault_paths import podcasts_root  # noqa: E402
from resolve_podcast_entities import PodcastEntityResolver  # noqa: E402

PODCASTS_CFG = ROOT / "_system" / "reference" / "podcasts"
SHOW_REG = PODCASTS_CFG / "show_registry.json"
GUEST_REG = PODCASTS_CFG / "podcast_guest_registry.json"
ALIAS_OVERRIDES = PODCASTS_CFG / "company_alias_overrides.json"
OFFICER_DIR = PODCASTS_CFG / "officer_directory.json"

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "content": "http://purl.org/rss/1.0/modules/content/",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def user_agent() -> str:
    return (load_json(SHOW_REG).get("user_agent")
            or "SSI-PodcastAgent/1.0 (+research)")


def http_get(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def episode_id_from(guid: str | None, audio_url: str | None, title: str) -> str:
    raw = (guid or audio_url or title or "unknown").strip()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "episode")[:48]).strip("-").lower() or "episode"
    return f"{slug}-{digest}"


def parse_rss(xml_bytes: bytes, show: dict) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []
    show_title = (channel.findtext("title") or show.get("title") or "").strip()
    out: list[dict] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        description = (item.findtext("description") or "").strip()
        # strip simple html
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()
        guid = (item.findtext("guid") or "").strip() or None
        link = (item.findtext("link") or "").strip() or None
        pub = item.findtext("pubDate")
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).date().isoformat()
            except (TypeError, ValueError, IndexError):
                published = None
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None
        itunes_author = None
        author_el = item.find("itunes:author", NS)
        if author_el is not None and author_el.text:
            itunes_author = author_el.text.strip()
        eid = episode_id_from(guid, audio_url, title)
        out.append(
            {
                "episode_id": eid,
                "show_id": show.get("show_id"),
                "show_title": show_title,
                "title": title,
                "description": description,
                "published": published,
                "guid": guid,
                "link": link,
                "audio_url": audio_url,
                "itunes_author": itunes_author,
                "discovery": "watchlist_rss",
                "enclosure_hash": hashlib.sha1((audio_url or guid or title).encode()).hexdigest(),
            }
        )
    return out


def podcast_index_search(term: str, max_results: int = 10) -> list[dict]:
    """Best-effort public Podcast Index search (no auth). Returns empty on failure."""
    if not term.strip():
        return []
    # Public Apple iTunes search as durable fallback (no API key).
    q = urllib.parse.urlencode({"term": term, "media": "podcast", "entity": "podcastEpisode", "limit": max_results})
    url = f"https://itunes.apple.com/search?{q}"
    try:
        raw = http_get(url, timeout=30)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return []
    out: list[dict] = []
    for row in data.get("results") or []:
        if row.get("wrapperType") and row.get("wrapperType") != "podcastEpisode":
            # collection results — skip unless episode
            if "episodeUrl" not in row and "trackTimeMillis" not in row:
                continue
        title = (row.get("trackName") or row.get("collectionName") or "").strip()
        if not title:
            continue
        desc = (row.get("description") or "").strip()
        audio = row.get("episodeUrl") or row.get("previewUrl")
        guid = str(row.get("trackId") or audio or title)
        published = None
        if row.get("releaseDate"):
            published = str(row.get("releaseDate"))[:10]
        show_title = (row.get("collectionName") or term).strip()
        eid = episode_id_from(guid, audio, title)
        out.append(
            {
                "episode_id": eid,
                "show_id": "discovered",
                "show_title": show_title,
                "title": title,
                "description": desc,
                "published": published,
                "guid": guid,
                "link": row.get("trackViewUrl") or row.get("collectionViewUrl"),
                "audio_url": audio,
                "itunes_author": row.get("artistName"),
                "discovery": "podcast_index_search",
                "search_term": term,
                "enclosure_hash": hashlib.sha1((audio or guid or title).encode()).hexdigest(),
            }
        )
    return out


def build_search_terms() -> list[str]:
    terms: list[str] = []
    for g in load_json(GUEST_REG).get("guests") or []:
        for q in g.get("search_queries") or []:
            if q and q not in terms:
                terms.append(q)
    for row in load_json(ALIAS_OVERRIDES).get("aliases") or []:
        for p in row.get("phrases") or []:
            if p and f"{p} podcast" not in terms:
                terms.append(f"{p} CEO")
                terms.append(f"{p} CFO")
    for off in load_json(OFFICER_DIR).get("officers") or []:
        name = off.get("person_name")
        if name and name not in terms:
            terms.append(name)
        for c in off.get("company_aliases") or []:
            t = f"{c} podcast"
            if t not in terms:
                terms.append(t)
    return terms


def select_relevant(
    episodes: list[dict],
    resolver: PodcastEntityResolver,
    *,
    watchlist: bool,
    host_guest_ids: list[str] | None = None,
    keep_all_watchlist: bool = False,
    host_recent_limit: int = 40,
) -> list[dict]:
    selected: list[dict] = []
    host_only_recent: list[dict] = []
    for ep in episodes:
        blob_title = ep.get("title") or ""
        # Prefer description over itunes_author for guest resolve (author is often the host)
        blob_desc = ep.get("description") or ""
        if not blob_desc and ep.get("itunes_author"):
            blob_desc = ep.get("itunes_author") or ""
        resolved = resolver.resolve_episode(
            title=blob_title,
            description=blob_desc,
            show_title=ep.get("show_title") or "",
            host_guest_ids=host_guest_ids,
        )
        # Title-only guest resolve avoids Buffett/Berkshire body-spam in long show notes
        title_resolved = resolver.resolve_episode(
            title=blob_title,
            description="",
            show_title="",
            host_guest_ids=None,
        )
        title_guests = [
            g
            for g in (title_resolved.get("guests") or [])
            if g.get("guest_id") not in set(host_guest_ids or [])
        ]
        resolved["title_guests"] = title_guests
        ep = {**ep, "resolve_preview": resolved}
        if watchlist and keep_all_watchlist:
            selected.append(ep)
            continue
        high = bool(
            title_guests
            or resolved.get("has_officer_hit")
            or resolved.get("tickers")
            or resolved.get("near_universe_any")
        )
        if high:
            selected.append(ep)
        elif host_guest_ids and resolved.get("has_pz_guest"):
            host_only_recent.append(ep)
    if host_only_recent:
        host_only_recent.sort(key=lambda e: e.get("published") or "", reverse=True)
        selected.extend(host_only_recent[:host_recent_limit])
    return selected


def discover(*, include_search: bool = True, max_search_terms: int = 40) -> dict:
    shows = load_json(SHOW_REG).get("shows") or []
    resolver = PodcastEntityResolver()
    all_eps: list[dict] = []
    errors: list[dict] = []

    for show in shows:
        if not show.get("watchlist"):
            continue
        rss = (show.get("rss_url") or "").strip()
        if not rss:
            # Resolve feed via iTunes podcast search on show name
            term = show.get("podcast_index_term") or show.get("title")
            try:
                q = urllib.parse.urlencode({"term": term, "media": "podcast", "entity": "podcast", "limit": 3})
                data = json.loads(http_get(f"https://itunes.apple.com/search?{q}").decode())
                for row in data.get("results") or []:
                    feed = row.get("feedUrl")
                    if feed:
                        rss = feed
                        break
            except Exception as exc:
                errors.append({"show_id": show.get("show_id"), "error": f"feed_lookup:{exc}"})
        if not rss:
            errors.append({"show_id": show.get("show_id"), "error": "no_rss"})
            continue
        try:
            xml_bytes = http_get(rss)
            eps = parse_rss(xml_bytes, show)
            all_eps.extend(
                select_relevant(
                    eps,
                    resolver,
                    watchlist=True,
                    host_guest_ids=list(show.get("host_guest_ids") or []),
                    keep_all_watchlist=False,
                )
            )
            time.sleep(float(show.get("rate_limit_seconds") or 1.0))
        except Exception as exc:
            errors.append({"show_id": show.get("show_id"), "error": str(exc)})

    if include_search:
        terms = build_search_terms()[:max_search_terms]
        for term in terms:
            try:
                eps = podcast_index_search(term, max_results=8)
                all_eps.extend(select_relevant(eps, resolver, watchlist=False))
                time.sleep(0.8)
            except Exception as exc:
                errors.append({"search_term": term, "error": str(exc)})

    # Dedupe by enclosure_hash
    seen: set[str] = set()
    deduped: list[dict] = []
    for ep in all_eps:
        h = ep.get("enclosure_hash") or ep.get("episode_id")
        if h in seen:
            continue
        seen.add(h)
        deduped.append(ep)

    out_dir = podcasts_root(create=True)
    out_path = out_dir / "discovery_latest.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "episode_count": len(deduped),
        "errors": errors,
        "episodes": deduped,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-search", action="store_true", help="Skip Podcast Index / iTunes discovery (2B)")
    p.add_argument("--max-search-terms", type=int, default=40)
    args = p.parse_args()
    payload = discover(include_search=not args.no_search, max_search_terms=args.max_search_terms)
    print(f"discovered {payload['episode_count']} episodes; errors={len(payload.get('errors') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
