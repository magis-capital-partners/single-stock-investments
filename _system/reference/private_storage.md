# Private research storage

Bulk research bytes belong in the existing private R2 bucket. The private
`magis-capital-partners/research-catalog` repository contains small hash-bound
pointers. The existing research-vault history remains unchanged and readable.

`_system/config/private_storage.json` pins the account, bucket, catalog repository
identity, and lossless transport limits. The activation flag initially remains
false while the new transport is verified. Explicit bootstrap commands can
register an approved archive and test the real CI credentials before activation.

## Integrity

- Store each immutable encoded chunk by its SHA-256. Verify a complete readback
  before committing a catalog pointer. An existing differing object is an error.
- Restore every original byte, including whitespace, line endings, source text,
  and paid output. Verify both chunk hashes and the final complete-file hash.
- Keep the catalog private and reject a changed repository identity. A catalog
  shard is limited to 1 MiB; total catalog metadata is limited to 100 MiB.
- Use an isolated catalog Git cache and alternate publication index. Never reset
  a research-vault checkout. Ref updates are non-forced; stale overlapping
  updates fail closed while independently updated paths remain preserved.
- Preserve original ledger events in order and values. An older incoming ledger
  cannot erase existing reservations, completed events, or unknown usage.
- Keep native model input, source/reference budgets, paid stage-cache identities,
  compiler, financial identity, economic and independent-review gates unchanged.

## Approved V recovery

The checked configuration pins the owner's already approved V archive, contract
and immutable handoff. Its complete ZIP includes current paid records and
original prelaunch bytes. Registration verifies the ordinary strict compiler,
approved review, derivation receipts and separate author/challenger identities.
It never calls a model or authors an assumption.

```
python _system/scripts/private_storage_bootstrap.py register --ticker V --limit 1 --archive <approved-private-archive>
python _system/scripts/private_storage_bootstrap.py check --ticker V --limit 1
python _system/scripts/private_storage_bootstrap.py prepare --ticker V --limit 1
```

`register` preserves the verified archive and its catalog pointer. `check`
downloads and revalidates that complete archive, then preserves a genuine
storage-preflight audit receipt. `prepare` publishes its exact approved private
members for the normal deterministic build. All three operations are distinct
from model approval, a company build, price refresh or hosting publication.

The `private-storage-check` repository event runs the check on trusted main with
the configured CI credentials. It logs only identities, counts and status;
private payloads and credential values must never enter logs or public artifacts.

## Access and retention

Local operations reuse the existing authorized Wrangler session. CI uses its
existing Cloudflare token and research-vault service credential; a separate
catalog credential is supported when explicitly configured. Tokens are passed in
environment configuration, not command arguments or committed files. No public
bucket access is enabled.

Paid records, admission events, primary evidence, approved handoffs, unique audit
proofs and their original source identities are protected from automatic expiry.
Disposable-log, preview and rollback retention settings describe eligible
rebuildable data only. Removal requires a reference audit and verified complete
restoration; absence from today's source manifest alone is not deletion proof.
