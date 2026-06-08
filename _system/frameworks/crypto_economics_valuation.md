# Crypto economics valuation overlay

**Purpose:** For holdings with material **bitcoin**, **mining**, or **stablecoin** economics, document what is in Lawrence IRR math versus live network context.

**Wisdom:** Horizon Kinetics Cryptocurrency Compendium (`hk_pdfs/Horizon_Kinetics_Cryptocurrency_Compendium.pdf`); Stahl interview on mining cost + margin (`Stahl-Worth-The-Time-Predictive-Attributes-extract.txt`).

**Companion:** `optionality_valuation.md` · `segment_cashflow_valuation.md` · `equity_stub_valuation.md` (levered treasury names)

---

## When to trigger

Set `btc_overlay` in `valuation.json` when ticker appears in `_system/portfolio/holdings_crypto.json`.

| Exposure | Examples | Primary context |
|----------|----------|-----------------|
| `treasury` | MSTR | Spot vs look-through NAV; protocol mining floor |
| `miner` | CMSG | Hashprice vs fleet power contracts |
| `platform` | GLXY | Network activity, fee/vol regime |
| `stablecoin` | CRCL | USDC supply, reserve yield, regulation |

**Future sleeve:** `ethereum` in `holdings_crypto.json` (reserved; not v1).

---

## Required JSON shape

```json
"btc_overlay": {
  "as_of": "YYYY-MM-DD",
  "crypto_exposure": "treasury | miner | platform | stablecoin",
  "status": "partial | complete",
  "in_base_irr": false,
  "themes": [],
  "mining_economics_context": {},
  "in_model": {},
  "not_in_model_requires_refresh": []
}
```

**Hard rule:** `in_base_irr` stays `false` unless human sets promotion under **[HUMAN REVIEW]**.

---

## Marvin report requirements

In **Business & moat**, after option scan:

### `#### Bitcoin economics — model coverage` (BTC/miner/platform)

Or `#### Stablecoin economics — model coverage` for `stablecoin` exposure.

Table: **Theme | Latest metric | Filing fact | In base IRR?**

Minimum rows when `btc_network_economics` tagged:

1. Bitcoin spot vs filing mark  
2. Network hash rate / difficulty  
3. Hashprice / breakeven power (miners) or protocol floor context (treasury)  
4. mNAV / wrapper premium (MSTR only)

For **CRCL** (`stablecoin`):

1. USDC market cap / circulating supply  
2. Reserve yield path (10-K)  
3. Regulation / GENIUS Act context **[Assumption]** until filed  

---

## Mechanical refresh

1. `fetch_crypto_panel.py` → `_system/reference/market-data/crypto/manifest.json`  
2. `apply_btc_context_overlay.py {TICKER}` → `btc_overlay` + `evidence/crypto_context_{date}.md`  
3. `fetch_equity_prices.py` before `marvin_valuation.py --write` (live equity + BTC spot alignment)

---

## Milly checks

| Check | Action |
|-------|--------|
| Tagged in `holdings_crypto.json` but no `btc_overlay` | `btc_coverage: incomplete` |
| Placeholder `inputs.price` with active `btc_overlay` | Inference risk |
| Miner without hashprice row | Dive gap |
