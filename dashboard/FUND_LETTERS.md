# Fund Letters

The shared reader lives at `/fund-letters/` and in the dashboard’s Fund Letters tab. It reads published revisions through `/api/fund-letters`. It never reads the legacy extract-based dashboard shards.

## Access boundary

The verified owner identities are `drew@magiscapitalpartners.com` and `mike@magiscapitalpartners.com`. A login is also an owner when its address is listed in `PORTFOLIO_DREW_ACCESS_EMAILS` or `PORTFOLIO_MICHAEL_ACCESS_EMAILS`. An address listed for both is not an owner. Those two people, and no others, can load the main dashboard. Every other admitted human identity is a reader. Service tokens cannot become human readers or owners. A human Access token may include the person's name beside the email; that name does not remove ownership. An owner who opens `/fund-letters/` is sent back to the portfolio dashboard at `/`.

Root Pages middleware runs on **every path**, including static assets, guessed filenames, manifests, preview hosts and APIs. `_routes.json` has no exclusions. Only the Fund Letters reader shell, its two assets and its API are reader-accessible. A reader opening `/` or `/index.html` is redirected to `/fund-letters/`, the Fund Letters tab, and every other dashboard path is denied before the asset or API is read. Owner APIs also check ownership themselves. Exact POST ingestion routes retain their existing cryptographic machine authentication; there is no ingestion-prefix exemption.

Configure `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` in both production and preview environments. Missing identity configuration denies access. Use a Cloudflare Access application covering the entire hostname, with the intended approved-user policy. Application authorization restricts those admitted users further. If more-specific Access applications exist, reconcile their audiences/policies before release. An ordinary Cloudflare account is not admission to the application. Keep R2 public access disabled.

`CF_ACCESS_REVOKED_EMAILS` supports immediate application-level denial of an email. Revoke the user’s Access sessions as well when removing admission. No-store responses prevent shared/browser cache reuse by role. Previously cached or publicly distributed copies require separate cleanup.

Local development bypass requires `PORTFOLIO_AUTH_MODE=development` **and** a localhost request. It cannot enable access on a deployed hostname.

## Canonical archive and editorial processing

Schema: `dashboard/cloudflare/migrations/0023_fund_letters.sql`. Funds, canonical letters, source sections, idea discussions, evidence, immutable revisions, review issues, processing checkpoints and releases are separate records. Published pointers identify the reader-visible revision; a failed later attempt does not remove an existing publication.

All local generated data goes under ignored `_private/fund_letters/`. The inventory starts from the complete private vault, reuses established fund normalization, and hashes full normalized text. It collapses exact copies within a fund, preserves distinct same-quarter letters, and recovers nonidentical editions from prior duplicate-source lists. The automated lane resolves an identity, extraction or duplicate-source question only on deterministic evidence: the canonical fund record exists, the full text reconciles exactly to its sections, or the content hash is unique within the fund. Anything else stays unpublished with the reason recorded. It does not auto-merge distinct strategies.

Dates are separate: reporting period, verified printed date, independently supplied publication date, first ingestion, revision creation and summary publication. Quarter/month endpoints, filename dates and file modification dates are not promoted to verified printed dates. Unknown exact dates remain visibly unknown. Owners can correct dates with a recorded evidence note.

Synthesis maps **every** source passage, including tables and footnotes, independent of the ticker universe. It covers public and private companies, credit, shorts, special situations, unnamed investments, sector/macro arguments and portfolio reasoning. Table-only references stay factual notes. Passage inventories are cached by canonical content and pipeline version; repeated ideas are consolidated for the letter. `--retry-failed` retries failed work. The summarizer itself never publishes; the automated lane below publishes only after the deterministic verifier passes.

Validation checks full passage reconciliation, unique idea IDs, exact private evidence quotes, numerical support, dated comparisons, source-link leakage and copied twelve-word sequences. Publication records all six checks as machine-verified on the exact revision: complete document, idea coverage, claim accuracy, numerical accuracy, original writing and historical dates. The verifier repairs before it rejects: a figure backed elsewhere in the letter gains that exact source sentence as evidence, a figure found nowhere in the letter loses its sentence, a dropped passage note becomes its own idea, and a copied sentence is removed. Letters that still fail are quarantined with the reason and retried by the summarizer; no human review is required. Unresolved identity, extraction or alternate-source issues block publication. Unknown printed dates can remain unknown.

Owner review controls still expose the in-page original reader, original-letter links, private references/evidence, draft editing, revision selection, explicit editorial checks and issue resolution for the two owners. Saving creates a new revision. Publishing an older revision restores it while retaining the later revisions. Optimistic concurrency rejects publication against a stale published pointer.

## Commands

Run from the repository root. No command uses ThetaData or IB Gateway.

```powershell
python _system/scripts/fund_letters.py inventory
python _system/scripts/fund_letters.py status
python _system/scripts/fund_letters.py synthesize --fund FUND_ID --limit 10
python _system/scripts/fund_letters.py synthesize --letter LETTER_ID --retry-failed
python _system/scripts/fund_letters.py import-draft LETTER_ID PRIVATE_DRAFT.json --author EDITOR
```

Synthesis defaults to LM Studio’s native `/api/v1/chat` endpoint through the existing local transport, with reasoning disabled, no stored chats and no integrations. Start/load a suitable local model before running it. `--transport compatible` supports a compatible chat endpoint. Hidden reasoning and output exhausted at the token budget are rejected. The endpoint must be loopback. Large or scanned documents that cannot be processed must remain unresolved; do not sample away text, invent a thesis, or substitute the old extracts.

A local reader-summary stage also runs over the private vault extracts. It reads every passage, asks the local model for detailed company-level notes (business, thesis, activity, size, valuation, catalyst, named risk) and, for macro or mixed letters, the fund's main stances with what it is leaning into or out of. Every figure must appear in a verbatim quote checked in code; calendar years and labels such as QE2 are not numerical claims. It writes private summaries plus dashboard-shaped draft files (overview, ideas, private evidence, completeness checklist, and a stance block the reader renders as “Leaning in / Leaning out”) under `superinvestor-letters/_reader_summaries/` in the private vault.

Prompt `letter_detail_v5` (from 2026-10-28) asks for more detail than v4: a 350-500 word overview that opens with the fund's stated results and closes with risks and what the manager says to watch, and 110-180 word idea summaries that include what would change the manager's mind when the letter says so. Thin ideas and thin overviews get one expansion pass from their own verified notes, and the deterministic verifier re-checks everything afterwards. Finished v4 summaries stay valid and publishable. Only new letters, and v4 letters that failed or were quarantined, are summarized with v5. A letter that fails or quarantines three times under the current prompt is parked (`attempts` in its summary file), so the lane keeps moving. Delete its summary file to retry it.

The automated lane is `_system/scripts/auto_fund_letters.py`. On this Mac it runs as the launchd agent `com.magis.fund-letters` (KeepAlive, from this repository's `ssi-fund-letters` worktree), so stop it with `launchctl bootout gui/$(id -u)/com.magis.fund-letters` rather than `kill`. Each cycle repairs saved drafts, summarizes the next batch with the local model, imports every verified draft, publishes it on the machine-verified checks, exports a release, syncs that release to D1/private R2 when `--sync-remote` has its config and credentials, and commits the private summaries to the research vault. `publish_state.json` in the summaries directory records every outcome, so a restart resumes instead of repeating work. Quarantined letters are retried with `--retry-failed`, up to the attempt cap. They are never silently published and never wait on a person.

At startup the lane links every letter to its original PDF in Google Drive, using `superinvestor-letters/drive_import_manifest.json` in the private vault. Releases carry that link to D1 for every letter with a revision. Owners get **Original** on each letter card and **Read original** on the letter page. Both open an in-page reader with the full extracted text, a **PDF** tab that embeds Google Drive's preview (it renders only for a Google account with access to the file), and an **Open in Google Drive** link. The owner-only `action=original` API serves this. Readers get 403, and reader responses never include the link.

```powershell
$env:RESEARCH_VAULT_ROOT = "PATH_TO_PRIVATE_RESEARCH_VAULT"
python _system/scripts/summarize_fund_letter_reader.py --fund FUND_ID --period 2011Q1 --limit 1
python _system/scripts/summarize_fund_letter_reader.py --repair-existing
python _system/scripts/auto_fund_letters.py --batch 5 --cycles 1
python _system/scripts/auto_fund_letters.py --batch 5 --cycles 0 --sync-remote
```

Publication through the local pipeline can also be run one revision at a time, with no human attestation:

```powershell
python _system/scripts/fund_letters.py publish REVISION_ID --automated
python _system/scripts/fund_letters.py export --output _private/fund_letters/releases/RELEASE_NAME
```

The owner interface keeps its six explicit editorial checkboxes for manual publishing; the automated lane does not use them and cannot fabricate them. Its `checks_json` records `mode: machine`, the verifier version, section/idea/evidence counts, and the per-check results for the exact revision.

Export refuses an existing release directory. It creates an immutable content-hashed manifest, append-only `archive.sql`, private source text objects, guarded `activate.sql`, and guarded `rollback.sql`. Full text is stored locally and in private R2, rather than duplicated in the remote D1 database. Sources are required for server-side editing/publication checks. Reader responses use explicit field allowlists and omit URLs, file paths, Drive IDs, raw extracts and evidence.

Apply migration 0023 using the existing deployment’s migration step before importing data. Local import is the release tool’s default:

```powershell
python _system/scripts/sync_fund_letters_release.py _private/fund_letters/releases/RELEASE_NAME --config _cf_project/wrangler.jsonc --max-batches 5
```

Remote imports require `--remote --target-database-id EXACT_UUID`, a matching JSON Wrangler config with `DB` and `PRIVATE_ARTIFACTS` bindings, and the account’s existing D1 budget check. The tool uploads source objects needed for revisions, imports bounded SQL batches, and records durable progress. Rerun the same release to resume. Existing online publications are preserved. `--activate` requests compare-and-set activation only after all import batches finish. `--rollback` restores the release’s prior pointers only where no subsequent online edit intervened. Activation attempts are reported; inspect the published pointers before declaring a release complete. A code rollback alone does not roll back data.

For interface testing:

```powershell
node dashboard/cloudflare/preview-fund-letters.mjs --fixture --reader
node dashboard/cloudflare/preview-fund-letters.mjs --db _private/fund_letters/archive.sqlite --port 8875
```

The preview binds only to loopback and rejects other Host headers. The fixture is synthetic; it is never written into the research archive or deployed.

## Public repository and private source preservation

The repository stays public. `migrate_dashboard_sources.py` preserves each full affected dashboard/catalog/research asset as a content-addressed object in the **private** `research-vault/dashboard-private/objects/` directory, verifies its exact bytes, then replaces its public counterpart with structural metadata only. Unknown field names and nested source prose cannot survive this explicit publication boundary. Original PDFs are copied and verified in that private directory before removal from the public tree. Public JSON, JSONL and CSV counterparts contain only placeholder flags and structural counts. The public `dashboard/private-assets.json` contains only paths of managed public assets and checksums; it contains no source URLs, Drive IDs, evidence, or original-letter paths.

The review branch migration preserved 1,022 dashboard files, 12 shared research files and one original PDF. An append-only private journal recovers interruptions. Old private versions remain available for previous public releases. Git attributes preserve checksum-sensitive bytes across Windows and Linux. The private preservation commits are in `magis-capital-partners/research-vault`; public removal takes effect only when the corresponding public change is merged.

The Cloudflare artifact builder restores exact full versions from the private vault for the owner dashboard; middleware protects every resulting resource. It fails before replacing a previous artifact if a private snapshot is absent or mismatched. Vault checkout and rebuilds hydrate their selected inputs first. A local hydration marker proves that a changed payload came from a full private snapshot; exporting consumes that marker. Unchanged rebuilds do not grow the private journal. The shared preservation action pushes private objects before public staging or deployment, and a guard examines actual staged blobs. Unexpected edits to sanitized managed files require hydration rather than silently replacing their full private versions.

```powershell
python _system/scripts/private_dashboard_assets.py
# Run the authorized dashboard/research builders, then preserve private updates:
python _system/scripts/migrate_dashboard_sources.py
python _system/scripts/audit_fund_letter_exposure.py --strict
python _system/scripts/audit_fund_letter_exposure.py --staged --strict
```

Hydrated files contain private material and must be sanitized before public staging. Do not commit private object storage, local releases or `_private/` to this repository. CI requires the configured private-vault clone token to build managed assets. Deployment-only runs also obtain the private vault.

## Release gates and remaining work

**Remote sync is live and incremental.** The local inventory built by the automated lane contains 19,339 canonical letters across 5,074 fund identities, with 1,050 missing text extracts. Verified batches sync to D1/private R2 through Wrangler OAuth on this Mac (`_cf_project/wrangler.jsonc` with the real D1 UUID and `PRIVATE_ARTIFACTS` bucket). A dedicated Account Analytics API token is optional for the soft D1 budget probe; OAuth alone is enough to upload and activate. The live Fund Letters tab shows activated published revisions as each release lands. Inventory counts are not a claim that the whole corpus has been summarized.

The refined exposure audit examines actual Drive links, letter references, letter extracts and tracked originals. It covers current tracked dashboard assets and letter-related repository data/research. The detailed report is `_private/fund_letters/exposure.json`. Historical public copies cannot be recalled. The audit does not certify forks, git history, external mirrors, other research collections or alternate hosting.

```powershell
python _system/scripts/audit_fund_letter_exposure.py --strict
```

The automated lane has published its first verified batch into the local archive and checkpoints each batch to the private research vault. Neither an inventory nor a failed model run counts as backfill completion; the corpus backfill is the resumable lane, and letters with no readable extract stay quarantined with the reason recorded. Remote publication follows the sync step above, one release per batch, so the Fund Letters tab fills incrementally rather than in one cutover.

GitHub Pages publication is disabled in the publishing action because it cannot enforce the application middleware. The GitHub Pages API returned 404 during inspection; that is not a certificate about cached copies or alternate hosting. Before declaring the live site verified, check actual owner, reader, removed and unauthenticated logins and direct requests on primary, preview and alternate hosts; then clear legacy caches and hosting. Do not describe a local role simulation as a live Access-policy validation.

Relevant Cloudflare references: [JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/), [application path precedence](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/), and [Pages middleware](https://developers.cloudflare.com/pages/functions/middleware/).
