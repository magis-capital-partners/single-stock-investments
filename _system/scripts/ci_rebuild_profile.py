#!/usr/bin/env python3
"""Run dashboard rebuild script lists by CI profile.

Profiles (aliases in parentheses):
  minimal              — build_dashboard_data only
  insights (pages-fast)— letters/index/insights/research_memory + dashboard
  activist             — activist feed + document registry slice
  full (intake-full)    — nightly full rebuild (documents, KPI, insights, memory);
                          valuation lives in Power Zone Universe, activist in the
                          dedicated Data Pipeline job

Removed: darwin, darwin-full, darwin-fast (the Darwin allocator was retired in 2026-10).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RETIRED_PROFILES = frozenset({"darwin", "darwin-full", "darwin-fast"})

ALIASES = {
    "pages-fast": "insights",
    "intake-full": "full",
    "world-model-monthly": "world-model-weekly",
}

# Steps that require GOOGLE_APPLICATION_CREDENTIALS (Shared Drive API).
DRIVE_API_STEPS = frozenset(
    {
        "_system/scripts/audit_drive_pdf_store.py",
        "_system/scripts/sync_pdf_store_google_drive.py",
    }
)

# Each entry is argv after `python` (script path relative to repo root + args).
PROFILES: dict[str, list[list[str]]] = {
    "biotech-strategy": [["_system/scripts/build_biotech_strategy.py", "--record-paper"]],
    "minimal": [
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "insights": [
        ["_system/scripts/enrich_cusip_ticker_map.py", "--skip-fetch"],
        ["_system/scripts/build_specialist_13f_signals.py"],
        ["_system/scripts/build_biotech_spend_value.py"],
        ["_system/scripts/build_biotech_insider_scores.py"],
        ["_system/scripts/build_biotech_peer_short_stub.py"],
        ["_system/scripts/build_biotech_composite.py"],
        ["_system/scripts/build_biotech_strategy.py", "--record-paper"],
        ["_system/scripts/repair_letter_dates.py", "--apply"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_insights.py"],
        # AFTER build_insights: research memory is built from insights.json,
        # which is gitignored and so absent in a fresh CI checkout until
        # build_insights writes it. Built first, it saw no insights and the
        # drive lane committed ~1,100 claims over the ~12,000 intake-full had
        # written that morning, every evening (15.4MB -> 1.4MB evidence).
        ["_system/scripts/build_research_memory.py"],
        ["_system/scripts/build_dashboard_data.py"],
        ["_system/scripts/validate_research_memory.py"],
    ],
    "activist": [
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/clean_activist_indexes.py"],
        ["_system/scripts/cleanup_activist_false_positives.py"],
        ["_system/scripts/activist_triage.py", "--apply", "--fetch-sec"],
        ["_system/scripts/build_activist_feed.py"],
        ["_system/scripts/auto_resolve_filing_events.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "full": [
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/audit_drive_pdf_store.py"],
        ["_system/scripts/build_drive_filename_index.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/sync_pdf_store_google_drive.py", "--root-key", "general_pdfs", "--workers", "4"],
        ["_system/scripts/build_document_registry.py"],
        ["_system/scripts/build_drive_filename_index.py"],
        ["_system/scripts/build_letter_drive_links.py"],
        ["_system/scripts/build_fundamental_series.py"],
        ["_system/scripts/fetch_insider_transactions.py", "--offline"],
        ["_system/scripts/build_equity_model_dashboard.py"],
        ["_system/scripts/extract_equity_kpi_observations.py"],
        # Before the KPI build: FluView drops Friday, and this nightly lane is
        # what was leaving the respiratory panel and QDEL model on the August
        # cache. Both scripts keep the last good file if a source is down.
        ["_system/scripts/fetch_respiratory_panel.py"],
        ["_system/scripts/build_qdel_respiratory_model.py"],
        ["_system/scripts/build_fico_watch.py"],
        # Before KPI trends so the nightly monolith and the shards pick up
        # issuer operating series. A blocked source keeps the last file.
        ["_system/scripts/fetch_operating_kpis.py"],
        ["_system/scripts/build_kpi_trends.py"],
        ["_system/scripts/repair_letter_dates.py", "--apply"],
        ["_system/scripts/build_superinvestor_insights.py"],
        ["_system/scripts/build_index_membership.py"],
        ["_system/scripts/build_insights.py"],
        ["_system/scripts/enrich_cusip_ticker_map.py", "--skip-fetch"],
        ["_system/scripts/build_specialist_13f_signals.py"],
        ["_system/scripts/build_biotech_spend_value.py"],
        ["_system/scripts/build_biotech_insider_scores.py"],
        ["_system/scripts/build_biotech_peer_short_stub.py"],
        ["_system/scripts/build_biotech_composite.py"],
        ["_system/scripts/build_biotech_strategy.py", "--record-paper"],
        ["_system/scripts/build_research_memory.py"],
        # Backfill compact agent-context cards for the whole universe.
        ["_system/scripts/refresh_core_compounders.py", "--write", "--propose"],
        ["_system/scripts/build_thesis_card.py", "--all"],
        # Valuation authority is owned by the Power Zone Universe workflow
        # (run_security_decision_pipeline) and the activist slice by the
        # dedicated 06:00 Data Pipeline job; neither is duplicated here.
        ["_system/scripts/build_dashboard_data.py"],
    ],
    "world-model-weekly": [
        # Second writer, Sunday, in case the nightly intake-full lane misses
        # Friday's FluView. Same two scripts as the full profile.
        ["_system/scripts/fetch_respiratory_panel.py"],
        ["_system/scripts/build_qdel_respiratory_model.py"],
        ["_system/scripts/fetch_theme_panel.py"],
        ["_system/scripts/fetch_crypto_panel.py", "--skip-snowball"],
        ["_system/scripts/build_hk_snowball_model.py"],
        ["_system/scripts/refresh_energy_model.py", "--optional"],
        ["_system/scripts/refresh_commodity_models.py", "--optional"],
        ["_system/scripts/build_compounder_roster.py"],
        ["_system/scripts/scaffold_industry_kpi_ledgers.py", "--write"],
        ["_system/scripts/resolve_linkages.py", "--update-ledgers"],
        [
            "_system/scripts/check_kpi_ledger.py",
            "--write",
            "--mark-auto",
            "--queue-reviews",
        ],
        # After mark-auto, so a null actual is not left as the Sunday status,
        # and before lint, so the ledger lint sees this file.
        ["_system/scripts/build_fico_watch.py"],
        ["_system/scripts/lint_kpi_ledger.py"],
        ["_system/scripts/refresh_core_compounders.py", "--write"],
        ["_system/scripts/build_world_model_snapshot.py", "--skip-resolve", "--skip-snowball"],
        [
            "_system/scripts/apply_world_model_context.py",
            "--all",
            "--write",
            "--queue-reviews",
        ],
        # Warn-only Magis claim lint (not --strict until prose corpus is clean).
        ["_system/scripts/lint_predictability_claims.py"],
        ["_system/scripts/build_dashboard_data.py"],
    ],
}


def resolve_profile(name: str) -> str:
    key = name.strip()
    if key == "none":
        raise SystemExit("profile 'none' means skip rebuild; do not invoke this script")
    if key in RETIRED_PROFILES:
        raise SystemExit(
            f"profile '{key}' was removed with the Darwin allocator (2026-10); "
            "the Darwin Covered Call page is built by darwin-covered-call.yml"
        )
    return ALIASES.get(key, key)


def drive_api_configured() -> bool:
    return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


def should_skip_step(step: list[str]) -> bool:
    script = step[0] if step else ""
    return script in DRIVE_API_STEPS and not drive_api_configured()


# External sources. (attempts, per-attempt timeout seconds). A hung Drive read
# or a vendor blip retries with backoff; a local builder does not, so a real
# logic failure still fails on the first exit. The 2026-10-08 nightly died in
# sync_pdf_store_google_drive.py on TimeoutError with the registry unsaved
# past the last checkpoint and the rest of the profile unrun.
EXTERNAL_STEP_POLICY: dict[str, tuple[int, int]] = {
    "_system/scripts/sync_pdf_store_google_drive.py": (2, 20 * 60),
    "_system/scripts/audit_drive_pdf_store.py": (3, 10 * 60),
    "_system/scripts/fetch_respiratory_panel.py": (3, 5 * 60),
    "_system/scripts/fetch_operating_kpis.py": (2, 15 * 60),
    "_system/scripts/fetch_theme_panel.py": (3, 5 * 60),
    "_system/scripts/fetch_crypto_panel.py": (3, 5 * 60),
    "_system/scripts/refresh_cvr_universe.py": (2, 15 * 60),
    "_system/scripts/refresh_warrant_universe.py": (2, 15 * 60),
}
DEFAULT_STEP_TIMEOUT_SEC = 50 * 60
DASHBOARD_STEP = "_system/scripts/build_dashboard_data.py"


def step_policy(script: str) -> tuple[int, int]:
    """Return (attempts, timeout_seconds) for one rebuild step."""
    return EXTERNAL_STEP_POLICY.get(script, (1, DEFAULT_STEP_TIMEOUT_SEC))


class SourceFailure(RuntimeError):
    def __init__(self, source: str, detail: str) -> None:
        self.source = source
        super().__init__(detail)


def github_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def run_step(step: list[str], env: dict[str, str], *, sleep_fn=time.sleep) -> None:
    script = step[0]
    source = Path(script).name
    attempts, timeout = step_policy(script)
    cmd = [sys.executable, *step]
    detail = "failed"
    for attempt in range(1, attempts + 1):
        print(
            f"+ {' '.join(cmd)} (attempt {attempt}/{attempts}, timeout {timeout}s)",
            flush=True,
        )
        try:
            subprocess.run(cmd, cwd=ROOT, env=env, check=True, timeout=timeout)
            return
        except subprocess.TimeoutExpired:
            detail = f"timed out after {timeout}s"
        except subprocess.CalledProcessError as exc:
            detail = f"exit {exc.returncode}"
        if attempt >= attempts:
            break
        delay = min(60, 2 ** attempt)
        print(
            f"::warning::source {source} {detail}; retrying in {delay}s "
            f"({attempt}/{attempts})",
            flush=True,
        )
        sleep_fn(delay)
    message = (
        f"intake rebuild failed on source {source} ({script}) "
        f"after {attempts} attempt(s): {detail}"
    )
    print(f"::error::{message}", flush=True)
    raise SourceFailure(source, message)


def expand_steps(steps: list[list[str]]) -> list[list[str]]:
    """Insert rare-security refreshes immediately before each dashboard build."""
    out: list[list[str]] = []
    for step in steps:
        if step and step[0].endswith("build_dashboard_data.py"):
            # Nightly/CI sync: prices + stage transitions + scoped sleeve (no SEC).
            out.append(
                [
                    "_system/scripts/refresh_cvr_universe.py",
                    "--refresh-prices",
                    "--apply-transitions",
                    "--queue-stubs",
                ]
            )
            out.append(["_system/scripts/check_cvr_universe.py"])
            # Contract terms are immutable; this refresh only updates delayed
            # marks, point-in-time cohorts, matured outcomes, and the serving
            # artifact. Vendor failures preserve the last-known-good state.
            out.append(
                [
                    "_system/scripts/refresh_warrant_universe.py",
                    "--refresh-market",
                    "--capture-cohort",
                ]
            )
            out.append(["_system/scripts/resolve_warrant_outcomes.py"])
            out.append(["_system/scripts/build_warrant_dashboard.py"])
            # Warn-only here: this lane rebuilds the warrant artifact, it does
            # not own the registry. The warrant-discover job sweeps expiries
            # and runs the strict check. A blocking check here let one expired
            # series (BKSY.W) fail intake-full, drive and world-model for 13
            # days (2026-09-10..22).
            out.append(["_system/scripts/check_warrant_universe.py", "--warn-only"])
            # Separations: the register is append-only and owned by the
            # separation-discover job (Monday, strict check). This lane only
            # re-models flows and rebuilds dashboard/data/separations.json,
            # which the Special Situations desk reads, so the check is
            # warn-only here for the same reason as the warrant check above.
            out.append(["_system/scripts/build_separation_flows.py"])
            out.append(["_system/scripts/build_separations_dashboard.py"])
            out.append(["_system/scripts/check_separation_universe.py", "--warn-only"])
            out.append(["_system/scripts/build_reverse_splits_dashboard.py"])
            out.append(["_system/scripts/check_reverse_splits.py", "--warn-only"])
            out.append(["_system/scripts/build_special_situations.py"])
            # Desk briefs arrive by PR; the nightly rebuild only re-validates and
            # re-joins them so the Inbox shows the latest file per desk.
            out.append(["_system/scripts/check_desk_briefs.py", "--warn-only"])
            out.append(["_system/scripts/build_desk_briefs.py"])
            # Warn-only: a quiet discovery list or a catalog pointer with an old
            # stamp would otherwise fail intake-full. The strict command is what
            # a desk run uses. Activism calls the same script for activist_feed.
            out.append(["_system/scripts/check_desk_feed_age.py", "--desk", "special_situations", "--warn-only"])
        out.append(step)
    return out


def run_profile(profile: str, *, dry_run: bool = False) -> int:
    resolved = resolve_profile(profile)
    steps = PROFILES.get(resolved)
    if steps is None:
        known = ", ".join(sorted(set(PROFILES) | set(ALIASES)))
        raise SystemExit(f"Unknown rebuild profile: {profile!r} (known: {known})")

    steps = expand_steps(steps)
    print(f"ci_rebuild_profile: profile={profile} resolved={resolved} steps={len(steps)}", flush=True)
    env = os.environ.copy()
    dashboard_started = False
    try:
        for step in steps:
            if should_skip_step(step):
                print(f"~ skip (no GOOGLE_APPLICATION_CREDENTIALS): {' '.join(step)}", flush=True)
                continue
            if dry_run:
                attempts, timeout = step_policy(step[0])
                print(
                    f"+ {sys.executable} {' '.join(step)} "
                    f"(attempt 1/{attempts}, timeout {timeout}s)",
                    flush=True,
                )
                continue
            if step[0] == DASHBOARD_STEP:
                # Set before the script runs. A crash inside dashboard assembly
                # must not be committed as a partial dashboard.
                dashboard_started = True
                github_output("dashboard_written", "true")
            run_step(step, env)
    except SourceFailure as exc:
        github_output("failed_source", exc.source)
        github_output("dashboard_written", "true" if dashboard_started else "false")
        return 1
    github_output("failed_source", "")
    github_output("dashboard_written", "true" if dashboard_started else "false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", help="Rebuild profile name")
    parser.add_argument("--dry-run", action="store_true", help="Print steps only")
    parser.add_argument("--list", action="store_true", help="List profiles and exit")
    args = parser.parse_args()
    if args.list:
        for name in sorted(PROFILES):
            print(f"{name}: {len(PROFILES[name])} steps")
        for alias, target in sorted(ALIASES.items()):
            print(f"{alias} -> {target}")
        return 0
    if not args.profile:
        parser.error("profile is required unless --list")
    return run_profile(args.profile, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
