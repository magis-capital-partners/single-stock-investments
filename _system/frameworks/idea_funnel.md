# Idea Funnel (MOI)

**Purpose:** Pre–deep-dive gate. MOI ranks ~20 candidates to 3–5 before full research. Marvin uses this for **watchlist**, **onboard**, and **new names** outside core holdings.

**Source:** Mihaljevic, *Manual of Ideas* Ch 1 + Wiley description of ranking methodology.

---

## Pipeline

```
Screen (quant, news, superinvestor) 
  → moi_bucket tag 
  → MOI three questions (brief) 
  → Uses/misuses skim 
  → Proceed to deep dive OR pass (decision_log)
```

Wire into `investment_process.md` § Discover.

---

## Gate — proceed to full dive when

| # | Criterion |
|---|-----------|
| 1 | `moi_bucket` set |
| 2 | MOI three questions answered (even if brief) |
| 3 | No **disqualifying misuse** (e.g. no catalyst on SOTP, clone without verify plan) |
| 4 | Return sketch > portfolio median **or** strategic sleeve need (croupier basket, optionality sleeve) |

Human can override; document in `[HUMAN REVIEW]`.

---

## Small-cap investability screen (Ch 7)

Before full dive on micro/small names, optional hard gate (adjust to Oakcliff size):

| Check | Example threshold |
|-------|-------------------|
| Market cap | > $50M |
| Revenue | > $10M trailing |
| Insider ownership | ≥ 1% |
| Avg daily dollar volume | > $500K |
| Employees | > 10 |

**Wrong-reason screen:** low P/E from one-time gain, pass on wrong metric.

**Hidden inflection:** legacy declining segment + profitable growth segment → `small_cap_inflection`; require segment split in dive.

---

## International pre-check (Ch 10)

For non-US listings (8697.T, TEQ.ST, LSEG, etc.):

- How **global** is revenue vs domestic listing?  
- Country / jurisdiction downside — exclude worst rather than chase EM growth alone  
- Prefer **regional expert** coattails over generic screens  
- Currency, withholding, governance → `[HUMAN REVIEW]`

---

## Output

- **Pass:** one line in `{TICKER}/research/decision_log.md`  
- **Proceed:** run standard Marvin pipeline (`build_filing_evidence.py` → dive)
