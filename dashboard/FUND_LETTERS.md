# Fund Letters

The shared reader lives at `/fund-letters/` and in the dashboard’s Fund Letters tab. It reads published revisions through `/api/fund-letters`. It never reads the legacy extract-based dashboard shards.

## Access boundary

The verified owner identities are `drew@magiscapitalpartners.com` and `mike@magiscapitalpartners.com`. Every other admitted human identity is a reader. Service tokens cannot become human readers or owners.

Root Pages middleware runs on **every path**, including static assets, guessed filenames, manifests, preview hosts and APIs. `_routes.json` has no exclusions. Only the reader shell, its two assets and its API are reader-accessible. A reader opening `/` is redirected to the reader. Owner APIs also check ownership themselves. Exact POST ingestion routes retain their existing cryptographic machine authentication; there is no ingestion-prefix exemption.

Configure `CF_ACCESS_TEAM_DOMAIN` and `CF_ACCESS_AUD` in both production and preview environments. Missing identity configuration denies access. Use a Cloudflare Access application covering the entire hostname, with the intended approved-user policy. Application authorization restricts those admitted users further. If more-specific Access applications exist, reconcile their audiences/policies before release. An ordinary Cloudflare account is not admission to the application. Keep R2 public access disabled.

`CF_ACCESS_REVOKED_EMAILS` supports immediate application-level denial of an email. Revoke the user’s Access sessions as well when removing admission. No-store responses prevent shared/browser cache reuse by role. Previously cached or publicly distributed copies require separate cleanup.

Local development bypass requires `PORTFOLIO_AUTH_MODE=development` **and** a localhost request. It cannot enable access on a deployed hostname.

## Canonical archive and editorial processing

Schema: `dashboard/cloudflare/migrations/0023_fund_letters.sql`. Funds, canonical letters, source sections, idea discussions, evidence, immutable revisions, review issues, processing checkpoints and releases are separate records. Published pointers identify the reader-visible revision; a failed later attempt does not remove an existing publication.

All local generated data goes under ignored `_private/fund_letters/`. The inventory starts from the complete private vault, reuses established fund normalization, and hashes full normalized text. It collapses exact copies within a fund, preserves distinct same-quarter letters, and recovers nonidentical editions from prior duplicate-source lists for review. Uncertain identities and alternate sources remain in the owner queue. It does not auto-merge distinct strategies.

Dates are separate: reporting period, verified printed date, independently supplied publication date, first ingestion, revision creation and summary publication. Quarter/month endpoints, filename dates and file modification dates are not promoted to verified printed dates. Unknown exact dates remain visibly unknown. Owners can correct dates with a recorded evidence note.

Synthesis maps **every** source passage, including tables and footnotes, independent of the ticker universe. It covers public and private companies, credit, shorts, special situations, unnamed investments, sector/macro arguments and portfolio reasoning. Table-only references stay factual notes. Passage inventories are cached by canonical content and pipeline version; repeated ideas are consolidated for the letter. `--retry-failed` retries failed work. Generation never publishes automatically.

Validation checks full passage reconciliation, unique idea IDs, exact private evidence quotes, numerical support, dated comparisons, source-link leakage and copied twelve-word sequences. These mechanical checks supplement editorial review. Publishing requires recorded confirmation of all six checks: complete document, idea coverage, claim accuracy, numerical accuracy, original writing and historical dates. Unresolved identity, extraction or alternate-source issues block publication. Unknown printed dates can remain unknown.

Owner review controls expose original-letter links, private references/evidence, draft editing, revision selection, explicit editorial checks and issue resolution. Saving creates a new revision. Publishing an older revision restores it while retaining the later revisions. Optimistic concurrency rejects publication against a stale published pointer.

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

For publication through the local pipeline, provide an explicit JSON object setting the six `EDITORIAL_CHECKS` keys to true after review:

```powershell
python _system/scripts/fund_letters.py publish REVISION_ID --author EDITOR --attestations PRIVATE_CHECKS.json
python _system/scripts/fund_letters.py export --output _private/fund_letters/releases/RELEASE_NAME
```

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

The repository stays public. `migrate_dashboard_sources.py` preserves each full affected dashboard/catalog/research asset as a content-addressed object in the **private** `research-vault/dashboard-private/objects/` directory, verifies its exact bytes, then sanitizes its public counterpart. Original PDFs are copied and verified in that private directory before removal from the public tree. The public `dashboard/private-assets.json` contains only paths of managed public assets and checksums; it contains no source URLs, Drive IDs, evidence, or original-letter paths.

The review branch migration preserved 1,022 dashboard files, 12 shared research files and one original PDF. An append-only private journal recovers interruptions. Old private versions remain available for previous public releases. Git attributes preserve checksum-sensitive bytes across Windows and Linux. The private preservation commits are in `magis-capital-partners/research-vault`; public removal takes effect only when the corresponding public change is merged.

The Cloudflare artifact builder restores exact full versions from the private vault for the owner dashboard; middleware protects every resulting resource. It fails before replacing a previous artifact if a private snapshot is absent or mismatched. Rebuilds hydrate their selected inputs first. The commit action preserves/pushes private objects before staging public counterparts, and a guard examines actual staged blobs. Unexpected edits to sanitized managed files require hydration rather than silently replacing their full private versions.

```powershell
python _system/scripts/private_dashboard_assets.py
# Run the authorized dashboard/research builders, then preserve private updates:
python _system/scripts/migrate_dashboard_sources.py
python _system/scripts/audit_fund_letter_exposure.py --strict
python _system/scripts/audit_fund_letter_exposure.py --staged --strict
```

Hydrated files contain private material and must be sanitized before public staging. Do not commit private object storage, local releases or `_private/` to this repository. CI requires the configured private-vault clone token to build managed assets. Deployment-only runs also obtain the private vault.

## Release gates and remaining work

**This implementation has not been cut over to production.** The local inventory contains 12,892 canonical letters across 2,346 fund identities, with 104 missing text extracts. These are inventory counts, not a claim that the corpus has been summarized, identity-reviewed or published.

The initial broad exposure scan included unrelated provenance fields; the refined audit examines actual Drive links, letter references, letter extracts and tracked originals. It covers current tracked dashboard assets and letter-related repository data/research. The detailed report is `_private/fund_letters/exposure.json`. Historical public copies cannot be recalled. The audit does not certify forks, git history, external mirrors, other research collections or alternate hosting.

```powershell
python _system/scripts/audit_fund_letter_exposure.py --strict
```

The initial local-model pilot failed claim/evidence/number checks and was retained privately as failed drafts. One complete Comus letter has a manually corrected original draft awaiting owner review. There are **zero published letters**; neither an inventory nor a failed model run counts as backfill completion. A model/editorial process must pass the representative pilot before corpus generation and publication proceed.

GitHub Pages publication is disabled in the publishing action because it cannot enforce the application middleware. The GitHub Pages API returned 404 during inspection; that is not a certificate about cached copies or alternate hosting. Before production activation: merge the sanitized public counterparts; review a pilot containing long, short, complex, scanned and older letters against complete originals; resolve extraction failures; complete the resumable corpus backfill; verify actual owner/reader/removed/unauthenticated logins and direct requests on primary, preview and alternate hosts; then clear legacy caches and hosting. Do not describe a local role simulation as a live Access-policy validation.

Relevant Cloudflare references: [JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/), [application path precedence](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/), and [Pages middleware](https://developers.cloudflare.com/pages/functions/middleware/).
