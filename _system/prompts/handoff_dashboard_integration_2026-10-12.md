# Handoff prompt: land the one-hub work on the SSI dashboard

Paste everything below the line into a fresh agent session (written for Sol 6.1; any capable coding agent can run it). It is self-contained.

---

You are working in `magis-capital-partners/single-stock-investments` (SSI), the single hub for Magis Capital Partners research. Clone it fresh or `git pull` main; read `CLAUDE.md`, `CONTRIBUTING.md`, `docs/WRITE_MAP.md`, `SOURCES.md` and `_system/proposals/one_hub_for_humans_and_bots_2026-10-11.md` (its two closing sections, Implementation record and Decisions taken) before touching anything.

## What already landed (do not redo)

Four pull requests merged on 2026-10-11 and 2026-10-12:

- #1146 separations: split-off and spin-off register, terms engine, flow model, `split_offs` lane on the Special Situations desk, Separation card and odd-lot badge.
- #1147 the bots' source index: `SOURCES.md`, `_system/sources.json`, `validate_sources.py`, the in-repo memory hub shell.
- #1148 the one hub: `CONTRIBUTING.md`, `docs/WRITE_MAP.md`, `_system/agents/DESKS.md`, the `grok/` automerge data lane and path guard, `main-push-guard.yml`; desk briefs (`_system/data/desk_briefs/`, `build_desk_briefs.py`, `dashboard/desk-briefs-viz.js`, an Inbox panel); the short-research contract folded into `_system/research/short-alpha/` (new candidate fields, `share_supply` and `reverse_split_impairment` lenses, 114 imported reverse-split leads, Shorts-tab entry fields); the reverse-split study ported to `_system/scripts/reverse_splits/` with a JSONL ledger under `_system/data/reverse_splits/`, `dashboard/reverse-splits-viz.js` mounted under the Shorts tab, a Monday `reverse-splits` job; the memory hub copied into `_system/memory-hub/research-equity/`.
- The follow-up PR: decisions recorded, dead queues retired, the reverse-splits job hardened with step timeouts, the Greenblatt catalogue pointer.

Every builder, validator and test for those is green on main. What is **not** yet proven is the live dashboard: the hosted site serves committed artifacts only, `core.json` is rebuilt by the nightly `intake-full` job, and nobody has looked at the deployed pages since the merge.

## Your job: make the dashboard show all of it, and prove it

Work in this order. Each item is one pull request on a branch named `sol/<slug>` (your branch prefix is not auto-merged; a human merges). Never push to `main` directly.

1. **Rebuilt payloads.** Confirm the nightly `intake-full` run after 2026-10-12 03:00 UTC committed `dashboard/data/core.json` with `shards.desk_briefs` and `shards.reverse_splits`, and committed `desk_briefs.json`, `reverse_splits.json`, `short_alpha.json` (schema 1.2, 199 candidates), `special_situations.json` (six lanes including `split_offs`). If `intake-full` failed, read its log (`gh run list --workflow data-pipeline.yml`), fix the cause by PR, and say what it was. Do not hand-edit any `dashboard/data/*.json`; they are rebuilt (`_system/scripts/ci_rebuild_profile.py` is the order).
2. **Render check without the live login.** The live site is behind Cloudflare Access, so verify renders locally: `node dashboard/preview/spa-harness.mjs` or the preview server on port 8795 (see `dashboard/preview/`). Check, with screenshots or harness output in the PR: Ideas → Inbox shows the Desk briefs panel with the special-situations brief (owner, author, input ages); Ideas → Shorts shows category, source, tags, summary, the six-cell lens strip, and a Reverse splits section with recent announcements and repeat splitters; Ideas → Special Situations has the `split_offs` lane with the Medtronic/MiniMed exchange offer and the forced-seller rows from modelled flows; a ticker detail for MDT shows the Separation card; the feed-status page lists `desk-briefs`, `reverse-splits`, `separations`, `short-alpha`, `special-situations`. Zero console errors other than local `api/*` 404s.
3. **Deploy.** `dashboard-pages.yml` deploys committed data to Cloudflare Pages after the upstream run. Confirm the deploy that followed the rebuild succeeded and that the deployed `data/core.json` carries the new shards (fetch through the Access login if you have it; otherwise confirm the workflow run and the commit SHA it deployed).
4. **The `docs/` mirror.** `docs/index.html` and `docs/*-viz.js` are stale copies that nothing syncs (`Makefile` `pages-sync` points at a script that does not exist). Decide and do one of: delete the mirror and the Makefile target, or make the sync real. Say which and why in the PR.
5. **First Monday reverse-splits run.** The `reverse-splits` job runs Mondays 15:00 UTC (first run 2026-10-12). Check its run: the ledger under `_system/data/reverse_splits/` should gain rows, `check_reverse_splits.py --strict` should pass, and a lane receipt `_system/data/lane_receipts/data-pipeline-reverse-splits.json` should advance. If it failed, read the step logs (seed, clocks, export) and fix by PR. A 2026-10-12 local dry run measured seed at 47 s for 537 EDGAR hits and the clock pass at about six minutes for 423 filings.
6. **Python tests in CI.** `python-tests.yml` now runs the previously orphaned suites and reads `dashboard/index.html` plus the viz files. Confirm the first scheduled run (05:23 UTC) is green; if the Node-based UI suites (`test_separations_ui.py`, `test_desk_briefs.py`, `test_short_alpha_contract.py`) fail on the runner, fix the runner setup, never the tests.
7. **Open items you may take, each as its own PR:**
   - Greenblatt, *You Can Be a Stock Market Genius*: the Drive copy (file id `1LwfqcmaUU7X8uCMsoteeF8nRFt9mDNRe`) is a page scan with no text layer. OCR it (pymupdf with Tesseract, or any OCR), commit the `.txt` to the private `research-vault` under `investment-wisdom/greenblatt/`, and link it from `_system/data/separations/README.md` and the Special Situations block of `_system/prompts/grok_scan_agents.md`. Never commit book text to SSI.
   - Seven older event-lens deep dives (AES, GDRZF, HE, PCH, QDEL, STHO, XTIA) carry the lint warning "event lens without a dated end"; add `classification_inputs.event_window_end` with a sourced date or re-tag the lens, one PR per ticker or one PR with the evidence for each.
   - `check_ib_gateway_registry.py --scan-ssi` fails because `scan_ib_gateway_clients.py` does not exist; either restore the scanner the CLAUDE.md rule 2 describes or change the flag's error to say the scanner is absent.
   - The `reverse_splits` ledger README says the local workbench (prices, book, rerun) runs from the hub package with the SQLite kept under `_system/data/reverse_splits/local/`. Run `python -m _system.scripts.reverse_splits.cli --help` and confirm the `prices` and `book` commands work from a clean clone plus `import-ledger`; document any missing step in that README.

## Rules that bind you

- `CLAUDE.md` Rule 0 and Rule 9: nothing you run touches the IB Gateway, ever. The ThetaData seat rule in the user-level CLAUDE.md also applies; nothing here needs either.
- The write map is the contract: code and schema changes are reviewed by a human; you never weaken a schema to make one note pass; derived JSON is rebuilt, never edited.
- Every number shown on the dashboard carries `research_only: true`, `in_base_irr: false`, `authority: "none"` on its payload. Do not add a stance, a target, or a sizing anywhere.
- Before each PR: `python -m pytest -q _system/scripts/tests <the explicit list in .github/workflows/python-tests.yml>`, `python _system/scripts/validate_sources.py`, `python _system/scripts/check_desk_briefs.py`, `python _system/scripts/check_reverse_splits.py --strict`, `python _system/scripts/check_separation_universe.py --strict`, `python _system/scripts/build_short_alpha_dashboard.py --check`, and `python _system/scripts/graph_invariants.py --db <scratch>/graph.db --out <scratch>` (P3 and P6 must stay OK; never commit the regenerated baseline files).
- Commit messages end with your own attribution line. PR descriptions list what you verified and what you did not.
- If something cannot be done, say so in the PR and stop; do not substitute a weaker version silently.

Report back with the PR links, the screenshots or harness output for item 2, and the run links for items 1, 3, 5 and 6.
