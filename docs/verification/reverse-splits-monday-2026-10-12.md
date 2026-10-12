# Monday reverse-splits verification

Verified October 12 2026 against main `775173fa0c37d027e1d0230422e7b5d274f9510c`.

The [dispatched heal run](https://github.com/magis-capital-partners/single-stock-investments/actions/runs/38280867798/job/114917578978)
completed its reverse-splits job at `2026-10-12T17:02:01Z`, from checkout
`6021f76db26d6fa65b4014ef2dca1d17b312f576`. Import, discovery/clocks, export,
strict health validation and artifact commit all succeeded. The export commit
is `775173fa0c37d027e1d0230422e7b5d274f9510c`.

The exported events ledger grew from 632 to 663 rows (+31). Announcements
changed from 22,879 to 22,788; that table decreased by 91, so this is not a
claim that every ledger gained rows. Two hash-chained decisions remained
unchanged. Strict reverse-split validation reports zero structural errors and
healthy source status.

The committed lane receipt still had no successful run and `in_flight: true`.
It was regenerated with the official builder, using GitHub job-level evidence:

```sh
python _system/scripts/build_lane_receipts.py \
  --repository magis-capital-partners/single-stock-investments \
  --lane data-pipeline-reverse-splits
```

The rebuilt receipt records run `38280867798`, job `114917578978`, success
at `2026-10-12T17:02:01Z`, and `in_flight: false`. The builder reported no API
errors. The new optional scope refreshes one declared lane without writing
other receipts or listing unrelated workflows. Its default full-build behavior
and work-done success rules are unchanged. Unknown lane names fail before
any API call. Tests cover both isolation and invalid scope.

Before this PR the required Python suite and explicit workflow extra suites
ran: 1,060 passed, 7 skipped, 56 subtests, with the existing D1 timer assertion
failure that main already reports through `KNOWN_FAILURES`. Sources, briefs,
strict reverse splits, strict separations and Short Alpha checks passed.
Graph P3 and P6 stayed OK. Sparse-checkout E5 missing-file findings and existing
E7 are reported; a separate full-checkout comparison clears E5 but retains E7.
No scratch graph baseline is committed.

Not verified: profitability, price coverage, broker execution or borrow access.
This verifies the discovery/export job and its receipt, not a new full book.
No Gateway or ThetaData service was contacted. No supervisor healer or
notification job was dispatched. Human review and merge are required.
