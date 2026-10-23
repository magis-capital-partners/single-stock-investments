# Security-aware event relevance

The event pipeline verifies subjects and comparisons before deciding importance.
Importance is an attention ranking, not a probability or expected-return forecast.

## Data contracts

- `security_profiles.py` shares economic identity with readiness. It uses documented identity overrides, registry metadata, and the security master. A valuation route cannot establish instrument identity. Missing classification stays unresolved. Share-class aliases are explicit; different share classes remain separate.
- Ownership records preserve issuer CIK/name/ticker, reporting-owner CIK/name, security title, transaction code, transaction date, filing date, accession, and transaction index. A multi-symbol issuer header is resolved using the security class. Acquisitions are never assumed to be discretionary purchases. Trades in other issuers cannot inflate the reporting owner's conviction score.
- `xbrl_context.py` preserves reporting periods, consolidated context, units, scale, sign, and entity. Incompatible periods, conflicting values, missing context, or units are flagged. A crossing of zero is described without a misleading percentage headline.
- `event_relevance.py` keeps fact confidence separate from interpretation confidence. Fund accounting, indirect exposure, secondary sector metrics, and unresolved identity are capped before final presentation. Existing promotion floors and specialist scores cannot bypass those caps. Valid custody, tracking, fee, and redemption risks remain eligible.
- Filing publication date, reporting period, transaction/effective date, and processing date have different meanings. Rebuilding a filing does not make it new news.

## Profiles and adjustments

Shared profiles cover operating companies, asset funds, spot crypto funds, futures funds, leveraged/inverse funds, REITs, banks, insurers, and holding companies. Add supported primary evidence to `_system/reference/security_identity_overrides.json`; `economic_profile` and `underlying_exposure` are independent of valuation choices. A company-specific `metric_importance` entry can demote a metric to context only when it supplies `importance: context`, a reason, and evidence. It cannot promote unverified facts.

ETHA's identity is backed by [iShares](https://www.ishares.com/us/products/337614/ishares-ethereum-trust). Its [2025 10-K](https://www.sec.gov/Archives/edgar/data/2000638/000143774926006054/etha20251231_10k.htm) reports fund gains/losses, not operating-company earnings power. Berkshire's [September 2026 Form 4](https://www.sec.gov/Archives/edgar/data/1067983/000119312526397059/0001193125-26-397059.txt) distinguishes LEN Class A and LEN.B purchases. JPMorgan's [business description](https://www.jpmorganchase.com/about), Realty Income's [company description](https://www.realtyincome.com/who-we-are), and Berkshire's [reports](https://www.berkshirehathaway.com/reports.html) support the sector profile seeds.

## Rebuild and review

Normal `build_insights.py` runs apply the new interpretation automatically. For a bounded migration of the already published feed, use `python _system/scripts/refresh_event_relevance.py --apply --report PATH`. This preserves all other insight/media catalogs and reconciles the event shard and manifest together. The report records before/after rankings and counts of known error classes, not an invented precision estimate for unlabeled events.

`python _system/scripts/backfill_ownership_identity.py --fetch` repairs the retained ownership stories from rate-limited public SEC HTTPS submissions. Without `--fetch`, it performs no network reads. Builds consume the local `ownership_cache.json` and the regular transaction cache. No ThetaData or broker resources are used.

The event detail drawer offers Wrong company, Wrong interpretation, Already known, Clear flag, and Export flags. Flags alter that browser's feed without rewriting source facts. Use `refresh_event_relevance.py --feedback event-review-flags.json --report PATH` to measure remaining disagreements against matched event IDs. Shared rule changes still require evidence and regression coverage.

Regression checks run in `.github/workflows/event-relevance-tests.yml`, including issuer/actor attribution, share classes, missing codes, financial context, distinct dates, profile behavior, fund risks, score-gate precedence, escaping, and saved review flags.
