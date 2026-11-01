# What the complete allocation experiment found

The experiment tested all 38 registered policies under three cost/fill scenarios, both account capacities, and both budget regimes: 456 fixed-policy cases. It replayed 3,025 distinct execution profiles, all 119 single-issuer omissions for every case, strongest-one/five omissions, and annual selection using earlier completed issuer outcomes. All names remained assumed tradable. All 36 original numerical control cases reproduced.

The principal finding is that weak-close confirmation improves the historical cash-burn screen's risk/profit tradeoff much more than the tested sizing scores. The chronological selector did not beat the fixed cash-burn control over the full historical account path.

## Three-issuer account with common gross and squeeze budgets

| Policy | Base net marked P&L | Worst closing drawdown | Higher-cost stress net | Entries |
|---|---:|---:|---:|---:|
| Cash burn, $100k maximum | $153,552 | −$213,273 | $60,680 | 73 |
| Cash burn + rapid repeat gate | $129,700 | −$44,571 | $84,421 | 40 |
| Cash burn + weak-close gate | $129,996 | −$9,855 | $93,184 | 45 |
| Cash burn + both gates | $9,314 | −$3,879 | $4,887 | 16 |
| Rank and size repeat / weak close | $83,642 | −$61,104 | $52,984 | 73 |
| Rank alone | $153,765 | −$213,273 | $60,736 | 73 |

These are retrospective comparisons under fixed assumptions, not observed executions. The weak-close overlay retains approximately 85% of the cash-burn account profit with approximately 95% less worst closing drawdown. It uses less actual filled capital: $218,748 versus $445,118, so the capital difference also matters.

The stricter triple gate reduces the sample to 17 qualifying events and 16 filled entries from 14 issuers. Requiring every signal removes most of the dollar opportunity in this sample.

## Sizing versus selection

At the same intended daily allocation pool, uniform sizing produces $93,817 net and a $113,044 closing drawdown. Signal-weighted sizing produces exactly the same net, drawdown and filled dollars. Ranking adds only $212, with unchanged drawdown; combining ranking and sizing adds the same $212. Requested tier weights frequently do not alter the partial fills the market-volume model permits.

The $25k/$50k/$100k variable tiers lower absolute drawdown and deployed capital, but do not establish an improvement at matched intended daily capital. Grouping related financial evidence avoids duplicate bonuses; the tested grouped/shrunk scores still do not beat the strongest simple historical screens. The tested squeeze overlays do not change the three-slot cash-burn or core-score outcomes.

## Chronological and concentration checks

The account has insufficient completed traded-issuer training evidence to choose an alternative for 2024 or 2025, so it retains the fixed cash-burn fallback. Before 2026 it selects cash burn plus weak close. The resulting complete account path earns $152,134 versus $153,552 for fixed cash burn, with the same $213,273 worst closing drawdown. The 2026 result is $57,109 versus $58,527 for fixed cash burn.

The weak-close overlay remains profitable when any one issuer is removed and admissions are rerun; the worst such result is $69,047. Removing its strongest five issuers and reallocating leaves −$102. The adaptive account also becomes negative after removing its strongest five issuers and retraining. Profits therefore remain concentrated across a handful of issuers.

The full historical period was already inspected before this experiment. Chronological replay checks causality and stability, but does not create an untouched holdout. The weak-close overlay is the most useful candidate for a subsequent fixed-rule comparison; this experiment does not establish a superior sizing algorithm for deployment.

See [all comparisons and methodology](REPORT.md) and the [registered protocol](protocol.json). Numerical publication: `0dee2805aa5569a4c5c7cfd93460eacdcb3c75615944b3b1322e7e8cd020c4be`.
