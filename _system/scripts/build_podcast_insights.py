#!/usr/bin/env python3
"""Build structured podcast episode insights (parallel to letter insights)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import letter_matching as lm  # noqa: E402
from resolve_podcast_entities import PodcastEntityResolver  # noqa: E402
from vault_paths import podcasts_ref, podcasts_root, path_to_podcasts_ref  # noqa: E402

SECURITY_MASTER = ROOT / "_system" / "reference" / "securities" / "security_master.json"
REGISTRY = ROOT / "_system" / "portfolio" / "registry.json"
EMIT_MIN_TIER = "B"
THEME_KEYWORDS = {
    "AI": ["artificial intelligence", " ai ", "llm", "gpu", "hyperscaler"],
    "Capital Allocation": ["buyback", "dividend", "capital allocation", "m&a", "acquisition"],
    "Special Situations": ["spin-off", "spinoff", "restructuring", "activist", "catalyst"],
    "Compounders": ["compounder", "moat", "pricing power", "reinvestment"],
    "Credit": ["credit", "leverage", "refinanc", "liquidity", "debt"],
}


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_security_master() -> lm.SecurityMaster:
    data = load_json(SECURITY_MASTER) or {}
    registry = load_json(REGISTRY) or {}
    return lm.SecurityMaster.from_dict(
        data if isinstance(data, dict) else {},
        registry if isinstance(registry, dict) else None,
    )


def theme_hits(text: str) -> list[dict]:
    low = f" {text.lower()} "
    out = []
    for theme, kws in THEME_KEYWORDS.items():
        if any(k in low for k in kws):
            out.append({"theme": theme, "stance": "neutral"})
    return out


def iter_episode_files(root: Path):
    ep_root = root / "episodes"
    if not ep_root.is_dir():
        return
    for meta_path in sorted(ep_root.rglob("*.meta.json")):
        stem = meta_path.name[: -len(".meta.json")]
        txt_path = meta_path.parent / f"{stem}.txt"
        yield txt_path, meta_path


def source_ref_for(txt_path: Path, meta_path: Path) -> str | None:
    path = txt_path if txt_path.exists() else meta_path
    ref = path_to_podcasts_ref(path)
    if ref:
        return ref
    try:
        rel = path.relative_to(podcasts_root())
        return podcasts_ref(rel.as_posix())
    except ValueError:
        return None


def build_episode_record(
    txt_path: Path,
    meta: dict,
    master: lm.SecurityMaster,
    resolver: PodcastEntityResolver,
    host_by_show: dict[str, list[str]] | None = None,
) -> dict:
    text = txt_path.read_text(encoding="utf-8", errors="ignore") if txt_path.exists() else ""
    # Cap expensive letter_matching — full Whisper dumps are huge vs letters.
    match_window = text[:24000]
    head = text[:8000]
    host_ids = (host_by_show or {}).get(str(meta.get("show_id") or "")) or None
    resolved = resolver.resolve_episode(
        title=meta.get("title") or "",
        description=meta.get("description") or "",
        transcript_head=head,
        show_title=meta.get("show_title") or "",
        host_guest_ids=host_ids,
    )

    positions: list[dict] = []
    seen: set[str] = set()

    if match_window.strip():
        all_mentions = lm.match_letter(match_window, master, as_of=meta.get("published"))
        for m in lm.emitted_mentions(all_mentions, EMIT_MIN_TIER):
            t = m.get("ticker")
            if not t or t in seen:
                continue
            seen.add(t)
            positions.append(
                {
                    "ticker": t,
                    "action": m.get("action") or "discussed",
                    "commentary": (m.get("evidence") or "")[:240] or None,
                    "tier": m.get("tier"),
                }
            )

    for t in resolved.get("tickers") or []:
        t = str(t)
        if t in seen:
            continue
        seen.add(t)
        positions.append({"ticker": t, "action": "discussed", "commentary": None, "tier": "resolver"})

    guests = resolved.get("guests") or []
    return {
        "episode_id": meta.get("episode_id"),
        "show_id": meta.get("show_id"),
        "show_title": meta.get("show_title"),
        "title": meta.get("title"),
        "published": meta.get("published"),
        "link": meta.get("link"),
        "audio_url": meta.get("audio_url"),
        "discovery": meta.get("discovery"),
        "guests": guests,
        "persona_ids": sorted({pid for g in guests for pid in (g.get("persona_ids") or [])}),
        "officers": resolved.get("officers") or [],
        "companies": resolved.get("companies") or [],
        "tickers": [p["ticker"] for p in positions],
        "positions": positions,
        "themes": theme_hits(text or (meta.get("description") or "")),
        "highlights": meta.get("highlights") or [],
        "in_book": any(bool(c.get("in_book")) for c in (resolved.get("companies") or []))
        or any(bool(o.get("in_book")) for o in (resolved.get("officers") or [])),
        "near_universe": bool(resolved.get("near_universe_any")),
        "resolve_score": resolved.get("score"),
        "resolve_trace": resolved.get("resolve_trace"),
        "ambiguous": resolved.get("ambiguous") or [],
        "source_document": source_ref_for(txt_path, txt_path.with_name(txt_path.name)),
        "transcript_source": meta.get("transcript_source"),
        "has_pz_guest": bool(resolved.get("has_pz_guest")),
        "has_officer_hit": bool(resolved.get("has_officer_hit")),
    }


def build() -> dict:
    root = podcasts_root(create=True)
    master = load_security_master()
    resolver = PodcastEntityResolver()
    shows = (load_json(ROOT / "_system" / "reference" / "podcasts" / "show_registry.json") or {}).get(
        "shows"
    ) or []
    host_by_show = {
        str(s.get("show_id")): list(s.get("host_guest_ids") or [])
        for s in shows
        if s.get("show_id") and s.get("host_guest_ids")
    }
    episodes: list[dict] = []
    for txt_path, meta_path in iter_episode_files(root) or []:
        meta = load_json(meta_path) or {}
        if not meta.get("episode_id"):
            continue
        # Fix source ref using meta path
        rec = build_episode_record(txt_path, meta, master, resolver, host_by_show=host_by_show)
        rec["source_document"] = source_ref_for(txt_path, meta_path)
        if meta.get("highlights"):
            rec["highlights"] = meta["highlights"]
        episodes.append(rec)

    episodes.sort(key=lambda e: e.get("published") or "", reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": 1,
        "episode_count": len(episodes),
        "episodes": episodes,
    }
    (root / "insights.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    mirror = ROOT / "_system" / "reference" / "podcasts" / "insights_mirror.json"
    mirror.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    payload = build()
    print(f"podcast episodes={payload['episode_count']} -> {podcasts_root() / 'insights.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
