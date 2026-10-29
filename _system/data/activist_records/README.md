# Activist and short-seller track records

Planned home for one file per activist or short seller. Nothing in here is a
claim, a valuation, or an approved memory. The files are a record of what a
firm asked for and what happened, with the source next to each campaign.

`index.json` lists the firms. It starts empty. Campaign write-ups land in a
follow-up.

## One file per firm

Use either markdown or JSON. Prefer JSON when a later check will read the
file. Name the file with a short slug, for example `elliott.json` or
`hindenburg.md`.

Each file should carry:

- Firm name.
- CIKs the firm files under, including vehicles that show up on a Schedule 13D cover page.
- Campaigns. One campaign has:
  - ticker of the subject company
  - dates (first filing or letter, and the end date when there is one)
  - the ask (board seats, sale, capital return, or whatever the firm actually requested)
  - the outcome (settled, withdrawn, lost the vote, partial, still open)
  - return versus the index, only where a source states it, and in percent, not rescaled
  - sources (filing URL, accession, letter, or article)

Do not invent a return. If no source states one, leave it out. Do not copy a
number from a feed row that has not been checked against the filing.

## Index

`index.json` is the list of those files:

```json
{"firms": []}
```

A later pass appends objects with `slug`, `name`, `ciks`, and `path`. Until
that pass, `firms` stays an empty list.
