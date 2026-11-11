# Private research storage

Git holds code, a small private catalog and the append-only admission ledger. Private R2 holds complete evidence, paid histories, approved handoffs and bulk artifacts. The old research vault stays read-only at its pinned commit; its history is never rewritten by these tools.

All writes use private_storage.py. It verifies complete upload/download hashes before the catalog advances, preserves original bytes and supports old chunk layouts. Legacy bulk files can share bounded immutable packs; file boundaries, raw hashes and original Git blob identities remain explicit. Cold path indexes keep bulk metadata out of the active Git catalog. New current pointers take precedence over immutable historical copies.

## Recovery and publication

Use the saved approved handoff and publish_underwriting.py for recovery. Do not pay for another author because a build, archive, merge or hosting step failed. Each company has one publication-stage record. A model is complete only after its private archive, exact-company build, current-head checks, main merge, price refresh, served-value agreement, hosting and authenticated live verification.

The real admission ledger remains append-only. Raw serialization differences never authorize a reset or reclassification of unknown usage. Native model caps, evidence, identity, economic, replay and independent-review checks are separate from storage transport and remain unchanged.

## Legacy migration

Run migrate_private_storage.py against a new owned staging repository, with the exact configured legacy commit. Every source path and Git blob is inventoried, downloaded in bounded batches, preserved in R2 and completely read back before its immutable batch index is committed. Interrupted work resumes from verified batches. No source-vault write is made. --release-staging-packs releases only newly downloaded duplicate transport packs after complete private verification; original vault Git objects and pre-existing metadata packs remain.

Do not activate legacy_archive_manifest until the completion proof includes every inventoried path. The cold manifest must bind the configured legacy commit and all 256 path shards. Source files absent from the current source-archive manifest are retained; absence alone is never a pruning reason.

## Reversible local retention

private_storage_retention.py plans only known runtime caches and redundant temporary publication indexes. Apply requires the exact manifest hash, a complete private backup with a verified full restoration, fresh native process inventory, both unchanged launcher/worker locks and a byte-for-byte candidate recheck. It unlinks individual exact files only. Changed candidates stay. It never deletes directories, original Git history, locks, paid outputs, packets, primary evidence or unique audit proofs.

Registered disposable successful logs expire after 14 days, reproducible previews after 30 days, and five recent rollback deployments plus all referenced deployments remain. Unknown or unregistered files and required evidence/paid audits never expire automatically. These age rules select candidates; they do not bypass archival, reference, ownership or exact-list gates.

Legacy hosted history requires a separately authorized removal after a complete recoverable export. Removing files from a Git working tree does not reclaim old Git history.

## Object transport verification

REST remains supported. The optional `s3_existing_api_token` transport uses only the existing configured Cloudflare API token; signing values are derived in memory and never logged or saved. Verify the complete approved V archive and a real private audit write with the `private-storage-check` event before activation. A failed preflight leaves the configured default unchanged.

Verification uses the documented token owner scope. The `cfat_` format identifies an account token. Legacy values can use `s3_token_owner` (`account` or `user`); automatic legacy scope discovery tries the other documented endpoint only after HTTP 400, with the same token and pinned account. Authentication, permission and server failures never switch scopes or transports. Token whitespace normalization matches the existing REST path. No credential, permission or security setting is created or modified.

Activation evidence: trusted-main private-storage check run 42952008707 completed a real S3 read/write round trip using the existing configured token. It validated all 75 complete approved V members, the unchanged 294-row ledger, approved contract and immutable handoff; no model call ran. The configured object transport now uses this verified path. Local signed-in OAuth remains supported through REST when no API token is configured. Legacy migration uses the existing maximum 256-file batch, unchanged complete 64-MiB packs and the same 100-minute resumable job bound.

Large logical migration batches retain the existing 256-file maximum, but each Git download requests at most 16 exact original blob identities. The existing 180-second source-command bound and 100-minute job bound remain. A failed download leaves every prior verified batch intact; no incomplete logical batch advances the catalog.

## Complete legacy archive activation

The pinned legacy tree at 486141e428ad5b241c37a29f8b5f65ed1da0e2d9 is fully preserved: 141,700 original paths, 141,038 distinct Git blobs and 123,142,738,203 original bytes. All 556 verified batch indexes agree exactly with the 256 cold path indexes. Independent complete readback verified the source listing, original Git identities and modes, cold restoration, and the current 294-event ledger over its preserved 286-event historical copy. The transfer job reached its unchanged 100-minute bound during final index checks; independent verification completed those checks before activation.

The configured immutable manifest is legacy/486141e428ad5b241c37a29f8b5f65ed1da0e2d9/manifests/9d78c2cccd888997c53c672716cf14ddd688b09d6b9373205a9091d749f124dd.json. Current catalog records take precedence over this historical snapshot. The original research-vault repository and its Git history remain read-only and unchanged. This activation changes storage lookup only; paid records, company attempts, model assumptions and review/compiler/admission gates remain intact.
