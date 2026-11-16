# Exact-source large primary PDF recovery

The original `filing:0001213900-26-119240` exhausted six attempts on November 13
with `Announcement PDF requires verified readable text`. Preserve that original
job, all source bytes, first-observation clocks and the failed trial reviews.

The checksum-verified exhibit `ea031214601ex99-1.pdf` is 4,131,692 bytes, SHA-256
`61bcd17da2e271511e736fe00a1db8e8a6e3d76c79654c7efb635dfe85e0bd70`.
It has 513 native-text pages, one above the external reader's 512-page limit.
The original reader deterministically rejects it. Changing only that ceiling in
an isolated replay reads all 513 pages, 1,742,776 characters, in under a second;
no page needs OCR or visual text supplementation.

The external reader now has an exact-digest, exact-page-count approval for this
exhibit. The standard 120-page limit and unreviewed external 512-page limit stay
unchanged. Byte, encryption, native completeness, output and execution-time
limits still apply. The approval is archived through the existing document
review callback, with the child result bound again to the source digest/pages.
No OCR financial value or announcement term is supplied by the approval.

One versioned recovery hook archives the complete original failure before a
bounded retry of this exact job. It does not retry unrelated PDFs or write a
completed state on their behalf. Normal dispatch must actually complete it.
The healthy collector must load the repair through a normal bounded handoff
unless the owner explicitly authorizes an earlier research-only handoff.

The publisher interval from November 15 00:06–14:48 UTC had independently
reached late archival completion at November 16 00:02 UTC before this repair.
Its original interval/proof and article bodies require independent hash and
boundary checks; closure does not reconstruct original-clock observations.

The trial ended November 13. These repairs never change its immutable criteria,
daily grades, policies, decisions or fills, and never create catch-up fills.
