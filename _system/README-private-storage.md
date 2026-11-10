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
