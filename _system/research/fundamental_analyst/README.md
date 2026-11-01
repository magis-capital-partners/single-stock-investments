# Fundamental Analyst Friday refresh

The Fundamental Analyst records lens calls in a case log, then once a week
opens one additive pull request so those calls are graded with the rest of
the dated predictions.

The graded record is a v3 falsifier spec in
`{TICKER}/research/falsifier_specs.json`. `resolve_falsifiers.py` scores a
valid spec after its review date. The graph-invariants E2 check scores the
spec once the graph can mark it typed: the spec has to match a current
valuation-contract component. A spec that is valid but has no component is
still stored. E2 does not count it, and that absence is not a CI failure.

## What the Friday PR adds

Run:

```bash
python _system/scripts/fundamental_analyst_weekly.py \
  --case-log CASE_LOG.md \
  --irr-csv CORE_IRR_RANK_YYYY-MM-DD.csv \
  --irr-md CORE_IRR_RANK_YYYY-MM-DD.md \
  --core-list CORE_LIST.md \
  --as-of YYYY-MM-DD
```

The script is additive.

* A new case-log table row becomes one falsifier spec. The spec keeps the
  repo ticker, the call, one numeric test, the case log and the lens as the
  source, and the row's review date as both the first observable date and
  the resolution deadline. A review date that is already due is refused.
* The same spec id is never edited. A changed view is a new row and a new spec.
* A dated thesis card is written to
  `{TICKER}/research/fundamental_analyst/thesis_card_{call-date}.json`.
  It does not replace `{TICKER}/research/thesis_card.json`.
* The IRR rank is copied to
  `_system/research/fundamental_analyst/core_irr_rank_{as-of}.csv`, `.md`,
  and `.json`. A later Friday writes a new date. It does not overwrite the
  previous file. Prices in that file are recorded facts from the rank.
  Returns, owner cash, growth, and exit multiples are inferences.
* Facts and inferences that belong in `claims.jsonl` are submitted with
  `agent_proposals.py` and stay `pending_human_review`. The script does not
  write verified claims.
* Call-date prices are appended to
  `{TICKER}/research/fundamental_analyst/observations.jsonl`. The review
  observation is appended later, on or after the review date. Old rows stay.

Probability was not stated on the 2026-10-28 calls, so those specs are
diagnostic. They are not calibration-eligible and they are not Brier-scored.

The automerge gate rejects a Cursor pull request that does not add
`{TICKER}/research/research_agent_manifest.json` or committee artifacts.
The script writes that manifest and a matching `agent_run_state.json` when
the ticker has primary evidence and does not already have the pair. A ticker
with no primary evidence, including 1211.HK until PR #1332 lands its
documents, is skipped so the gate is not handed a manifest it would reject.

## What this refresh does not do

It does not delete or rewrite existing research. It does not touch broker,
Gateway, or order code. It does not edit a past case-log call or reason.
Evidence notes that are not the one registered test stay in the case log
for the human review. They are listed in `refresh_{as-of}.json`.

## 2026-10-29 registration

Eight calls from 2026-10-28, all with review date 2027-04-28.

| Spec id | Ticker | Test |
|---|---|---|
| `b3sa3-sa-stahl-hk-listing-close-2027-04-28` | B3SA3.SA | close at or below R$12.42 |
| `b3sa3-sa-hohn-fee-increase-2027-04-28` | B3SA3.SA | realised fee or price/mix change above 0% |
| `nu-stahl-hk-credit-spread-share-2027-04-28` | NU | credit-spread share of earnings under 50% |
| `nu-hohn-bank-adjusted-irr-2027-04-28` | NU | bank-adjusted IRR above 15% per year |
| `frmi-stahl-hk-underlying-value-2027-04-28` | FRMI | underlying value change below 0% |
| `frmi-hohn-base-irr-2027-04-28` | FRMI | base IRR at least 15% per year |
| `1211-hk-multilens-listing-close-2027-04-28` | 1211.HK | close at or below HK$48.3 |
| `googl-multilens-listing-close-2027-04-28` | GOOGL | close at or below $118 |

B3 in the case log is B3SA3.SA. BYD in the case log is 1211.HK (BYD Company
H-shares), not Boyd Gaming. 1211.HK is not on main yet. PR #1332 adds the
company. The spec is kept. There is no valuation contract to fingerprint, so
E2 will not count it until that contract exists.

B3SA3.SA and FRMI have empty ownership maps, so those four specs have the
same limit: valid for `resolve_falsifiers.py`, not typed for E2 until a
contract component exists. NU and GOOGL match a current component, so E2
counts them. None of the eight review dates is due.

The 15% rank does not include PBT or LB. Both were added to the core list
on 2026-10-29 and are named in `core_irr_rank_2026-10-29.json` as absent.
No IRR was invented for them. NU, FRMI, and 1211.HK are case-log names.
They are not on the core list.

The 50% credit-spread cutoff for NU is an assumption. The case log does not
state one. The rank's growth rates and exit multiples are assumptions too.
