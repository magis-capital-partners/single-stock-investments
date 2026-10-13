---
# Short idea entry. Adapted from Michael's Short-Selling desk TEMPLATE.md (2026-10-07).
#
# Where this file lives: SSI is a PUBLIC repository. A note that names a real
# company as a short target is written to the PRIVATE research vault at
#   research-vault/short-research/{TICKER}/{YYYY-MM-DD}-{slug}.md
# and only the structured row in _system/research/short-alpha/candidates.json
# plus its `note_ref` pointer are committed to SSI. Field rules:
# _system/research/short-alpha/README.md. `build_short_alpha_dashboard.py
# --check` rejects an unknown category, a bad tag, a short summary over 400
# characters, or `updated_on` before `added_on`. Do not weaken the contract to
# make one note pass.
#
# Front matter keys are the candidate fields. Copy the same values into the
# candidates.json row (ticker, stage, origin, source, category, added_on,
# updated_on, tags, summary, note_ref, frameworks, hypothesis, sources).

ticker: XYZ
security_name: "Company name"
stage: lead                       # lead | researching | ic | live | closed | rejected  (Michael: watching -> lead, active -> researching, closed -> closed, archived -> rejected)
origin: desk_note                 # desk_note for a bot or an author entry
source: research-bot              # bot id or author name, 80 characters or fewer, not an email
category: accounting              # accounting | shitco-concept | supply-side | share-supply | reverse-split | activist-short | borrow-squeeze
added_on: 2026-10-11              # set once
updated_on: 2026-10-11            # move on every material edit; on or after added_on
tags:
  - revenue-quality               # lowercase kebab-case, unique
summary: "One or two sentences a reader can scan on the card. 400 characters or fewer."
note_ref: research-vault/short-research/XYZ/2026-10-11-one-line-slug.md
frameworks: []                    # frameworks.json ids; the category adds its lenses on top
hypothesis: "What the market believes, why it is wrong, and what changes the price."
---

<!-- Delete this comment. Replace every section. Do not leave placeholder sentences. -->

## Thesis

The claim, in a few sentences a colleague can argue with. Name the category the claim really belongs to: a dilution story is `share-supply`, not `accounting`, even when a filing mentions revenue.

## Mechanism

How the claim shows up in filings, the industry, or the share structure. Separate what the desk has read from what it still needs to read.

## What would change our mind

- Evidence that would kill the idea. Write it before arguing the short.

## Open questions

- The question the next reader should answer.

## Sources

Name each document and the date it was read, with the filing locator. A market figure (price, borrow fee, availability, utilization, short interest, position size) appears only with its source and the date it was checked; a borrow snapshot is a reading on a date, not a standing fact. Do not paste paywalled or copyrighted text.
