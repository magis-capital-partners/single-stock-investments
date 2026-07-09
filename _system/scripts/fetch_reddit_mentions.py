#!/usr/bin/env python3
"""Fetch Reddit portfolio-ticker mentions (context tier — never base IRR).

Writes:
  - _system/reference/market-data/social/reddit_mentions_latest.json
  - _system/reference/market-data/social/records/{YYYY-MM-DD}.json

Auth: REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (optional REDDIT_USER_AGENT).
Use --offline to rebuild from cache without calling Reddit.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOCIAL_DIR = ROOT / "_system" / "reference" / "market-data" / "social"
SOURCES_PATH = SOCIAL_DIR / "reddit_sources.json"
LATEST_PATH = SOCIAL_DIR / "reddit_mentions_latest.json"
RECORDS_DIR = SOCIAL_DIR / "records"
CACHE_DIR = SOCIAL_DIR / "cache"
REGISTRY_PATH = ROOT / "_system" / "portfolio" / "registry.json"

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE = "https://oauth.reddit.com"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def portfolio_tickers() -> dict[str, str]:
    registry = load_json(REGISTRY_PATH, {"holdings": {}, "watchlist": {}})
    out: dict[str, str] = {}
    for bucket in ("holdings", "watchlist"):
        for ticker, meta in (registry.get(bucket) or {}).items():
            t = str(ticker).upper().strip()
            if t:
                out[t] = (meta or {}).get("company") or t
    return out


def ticker_patterns(tickers: dict[str, str]) -> dict[str, re.Pattern]:
    """Word-boundary patterns; skip 1-letter tickers to reduce false positives."""
    patterns: dict[str, re.Pattern] = {}
    for ticker in tickers:
        if len(ticker) < 2:
            continue
        # Escape dots (e.g. BRK.B) for regex
        escaped = re.escape(ticker)
        patterns[ticker] = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return patterns


def get_token(client_id: str, client_secret: str, user_agent: str) -> str:
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {creds}",
            "User-Agent": user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.load(resp)
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("Reddit token response missing access_token")
    return str(token)


def oauth_get(path: str, token: str, user_agent: str, params: dict | None = None) -> dict:
    qs = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{OAUTH_BASE}{path}{qs}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.load(resp)


def fetch_subreddit_new(subreddit: str, token: str, user_agent: str, limit: int) -> list[dict]:
    cache_path = CACHE_DIR / f"{subreddit}_new.json"
    try:
        doc = oauth_get(
            f"/r/{subreddit}/new",
            token,
            user_agent,
            {"limit": min(100, max(1, limit)), "raw_json": 1},
        )
        save_json(cache_path, doc)
        children = ((doc.get("data") or {}).get("children")) or []
        return [c.get("data") or {} for c in children if isinstance(c, dict)]
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if cache_path.exists():
            doc = load_json(cache_path, {})
            children = ((doc.get("data") or {}).get("children")) or []
            return [c.get("data") or {} for c in children if isinstance(c, dict)]
        raise RuntimeError(f"r/{subreddit}: {exc}") from exc


def load_cached_posts(subreddits: list[str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for name in subreddits:
        cache_path = CACHE_DIR / f"{name}_new.json"
        if not cache_path.exists():
            continue
        doc = load_json(cache_path, {})
        children = ((doc.get("data") or {}).get("children")) or []
        for child in children:
            if isinstance(child, dict):
                out.append((name, child.get("data") or {}))
    return out


def scan_posts(
    posts: list[tuple[str, dict]],
    patterns: dict[str, re.Pattern],
    lookback_hours: int,
) -> tuple[dict[str, dict], list[dict]]:
    cutoff = time.time() - lookback_hours * 3600
    by_ticker: dict[str, dict] = {}
    top_posts: list[dict] = []

    for subreddit, post in posts:
        created = float(post.get("created_utc") or 0)
        if created and created < cutoff:
            continue
        title = str(post.get("title") or "")
        selftext = str(post.get("selftext") or "")
        blob = f"{title}\n{selftext}"
        score = int(post.get("score") or 0)
        permalink = post.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else str(post.get("url") or "")
        matched: list[str] = []
        for ticker, pat in patterns.items():
            if pat.search(blob):
                matched.append(ticker)
        if not matched:
            continue
        for ticker in matched:
            bucket = by_ticker.setdefault(
                ticker,
                {"ticker": ticker, "mention_count": 0, "max_score": 0, "subreddits": set(), "posts": []},
            )
            bucket["mention_count"] += 1
            bucket["max_score"] = max(bucket["max_score"], score)
            bucket["subreddits"].add(subreddit)
            if len(bucket["posts"]) < 5:
                bucket["posts"].append(
                    {
                        "title": title[:200],
                        "url": url,
                        "score": score,
                        "subreddit": subreddit,
                        "created_utc": created,
                    }
                )
        top_posts.append(
            {
                "title": title[:200],
                "url": url,
                "score": score,
                "subreddit": subreddit,
                "tickers": matched,
                "created_utc": created,
            }
        )

    # Serialize sets
    for ticker, bucket in by_ticker.items():
        bucket["subreddits"] = sorted(bucket["subreddits"])
    top_posts.sort(key=lambda p: p.get("score") or 0, reverse=True)
    return by_ticker, top_posts[:40]


def build_payload(
    by_ticker: dict[str, dict],
    top_posts: list[dict],
    subreddits: list[str],
    status: str,
    error: str | None = None,
    mode: str = "live",
) -> dict:
    tickers_out = sorted(by_ticker.values(), key=lambda r: (-(r.get("mention_count") or 0), r.get("ticker") or ""))
    return {
        "generated_at": now_iso(),
        "as_of": today_iso(),
        "status": status,
        "mode": mode,
        "error": error,
        "subreddits": subreddits,
        "ticker_count": len(tickers_out),
        "mention_total": sum(r.get("mention_count") or 0 for r in tickers_out),
        "by_ticker": tickers_out,
        "top_posts": top_posts,
        "notes": "Context-tier social mention scan for portfolio/watchlist tickers. Not for base IRR.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Use cached Reddit JSON only")
    args = parser.parse_args()

    sources = load_json(SOURCES_PATH, {})
    settings = sources.get("settings") or {}
    subreddit_rows = sources.get("subreddits") or []
    subreddits = [str(s.get("name")) for s in subreddit_rows if s.get("name")]
    if not subreddits:
        print("No subreddits configured in reddit_sources.json")
        return 1

    user_agent = os.environ.get("REDDIT_USER_AGENT") or settings.get("user_agent") or "MarvinResearch/1.0"
    limit = int(settings.get("posts_per_subreddit") or 50)
    lookback = int(settings.get("lookback_hours") or 72)
    tickers = portfolio_tickers()
    patterns = ticker_patterns(tickers)

    posts: list[tuple[str, dict]] = []
    status = "ok"
    error = None
    mode = "offline" if args.offline else "live"

    if args.offline:
        posts = load_cached_posts(subreddits)
        if not posts:
            payload = build_payload({}, [], subreddits, status="empty", error="no cache", mode="offline")
            save_json(LATEST_PATH, payload)
            print(f"Wrote empty offline payload to {LATEST_PATH}")
            return 0
        status = "cached"
    else:
        client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            posts = load_cached_posts(subreddits)
            if posts:
                status = "cached"
                error = "missing REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET; used cache"
                mode = "offline"
            else:
                payload = build_payload(
                    {},
                    [],
                    subreddits,
                    status="missing",
                    error="missing REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET and no cache",
                    mode="offline",
                )
                save_json(LATEST_PATH, payload)
                RECORDS_DIR.mkdir(parents=True, exist_ok=True)
                save_json(RECORDS_DIR / f"{today_iso()}.json", payload)
                print(f"No credentials/cache; wrote status=missing to {LATEST_PATH}")
                return 0
        else:
            try:
                token = get_token(client_id, client_secret, user_agent)
                for name in subreddits:
                    try:
                        for post in fetch_subreddit_new(name, token, user_agent, limit):
                            posts.append((name, post))
                    except Exception as exc:  # noqa: BLE001
                        status = "degraded"
                        error = str(exc)
                    time.sleep(0.6)
            except Exception as exc:  # noqa: BLE001
                posts = load_cached_posts(subreddits)
                if posts:
                    status = "cached"
                    error = f"auth/fetch failed ({exc}); used cache"
                    mode = "offline"
                else:
                    payload = build_payload({}, [], subreddits, status="forbidden", error=str(exc), mode="live")
                    save_json(LATEST_PATH, payload)
                    print(f"Reddit auth failed: {exc}")
                    return 0

    by_ticker, top_posts = scan_posts(posts, patterns, lookback)
    payload = build_payload(by_ticker, top_posts, subreddits, status=status, error=error, mode=mode)
    save_json(LATEST_PATH, payload)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(RECORDS_DIR / f"{today_iso()}.json", payload)
    print(
        f"Wrote {LATEST_PATH} status={status} tickers={payload['ticker_count']} "
        f"mentions={payload['mention_total']} posts_scanned={len(posts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
