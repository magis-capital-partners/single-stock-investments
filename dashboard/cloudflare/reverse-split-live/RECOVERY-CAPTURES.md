# Bounded public-source coverage repair

The research collector can ingest an operator-delivered immutable capture when
its host cannot retrieve an ordinary public publisher archive. This uses no
broker, Gateway, market-data login, proxy, credentials or historical fills.

Set `RS_RECOVERY_REQUEST` to a root-controlled local request file containing:

```json
{"schema":"reverse_split_recovery_request.v1","manifest":"/absolute/path/manifest.json","sha256":"<manifest SHA-256>"}
```

The manifest schema is `reverse_split_recovery_bundle.v1`. Its `documents`
array binds each exact allowed source URL to a relative path, byte length,
SHA-256, content type and actual `retrieved_at`. `publisher` contains
`source: "prnewswire"`, contiguous `{page,url}` archive references, and exact
existing `{id,source_id,start_at,end_at}` gap identities. All interval article
bodies must be included. Relative paths cannot escape the capture directory.

The active collector validates the pin, raw pages, interval bounds, article
identities and original publication clocks under its existing writer lease.
It archives the inventory and queues body analysis at priority 9, below new
disclosures. The existing coverage checker closes each gap only after every
required body is archived and its analysis job completes. The installation is
idempotent and retains the previous recovery state and an archived manifest.
An updated request can be delivered without restarting the collector. Keep
the source files immutable and readable by `research` until the repair finishes.

The optional `reconcile_unavailable_filing` flag applies only to the reviewed
historical reference `0001214659-24-016464`. It requires official SEC submissions
metadata spanning the filing date, the uniquely identified current same-day
amendment `0001214659-24-016539`, and an already completed job with archived
original bytes for that amendment. The unavailable reference becomes
`superseded`, retaining its original payload, original failure and a proof
explaining that its original bytes were not recovered. This never asserts
that the two submissions were identical and never changes historical decisions.

Recovered articles keep their original publication clock and their actual late
first receipt. Public minute-resolution pagination cannot prove that deleted
or unpublished material never existed. A repaired gap is evidence of recovered
public coverage, not an original-time trading opportunity or a qualified shadow
session. Do not alter source clocks or clear gaps manually.
