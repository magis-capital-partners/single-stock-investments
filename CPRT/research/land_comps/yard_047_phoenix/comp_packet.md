# Yard 047 — Phoenix, AZ (comp packet)

**Yard ID:** 47  
**Address:** 615 S 51st Avenue, Phoenix, AZ 85043  
**Method:** Comp-based land only. **GAAP historical cost is not used.**

---

## Step 1 — Ownership and acreage

| Field | Value | Source |
|-------|-------|--------|
| Yard | COPART PHOENIX | Copart directory |
| Assessor acres | **[HUMAN REVIEW]** — Maricopa County Assessor | https://mcassessor.maricopa.gov/ |
| Working acres | **35 acres** [Assumption] — typical major metro salvage yard footprint pending assessor |

---

## Step 2 — Comparables (≥3)

### Comp A — Phoenix industrial land median

| Field | Value |
|-------|-------|
| Market | Phoenix MSA industrial land |
| **Median** | **~$200,000/acre** (2024–2025, bulk parcels) |
| Source | https://www.loopnet.com (market scan) [Assumption] |

### Comp B — Fletcher, NC Copart purchase (rural Sunbelt floor)

| Field | Value |
|-------|-------|
| Price | $8,600,000 / 57 acres |
| **$/acre** | **$150,877** |
| Source | `CPRT/research/land_valuation/transaction_anchors.json` |

### Comp C — Copart San Diego (buyer-specific ceiling)

| Field | Value |
|-------|-------|
| **$/acre** | **$588,235** |
| Source | Yard 059 comp packet |

**Adjustment:** Phoenix metro vs rural NC → **+35%** above Comp B → **~$204K/acre**; aligns with Comp A.

### Comp D — Houston TX industrial (peer sunbelt yard)

| Field | Value |
|-------|-------|
| **$/acre** | **~$180,000** [Assumption] |
| Source | Harris County industrial deed comps |

---

## Step 3 — Fair land value (35 ac working)

| Scenario | $/acre | Fair land |
|----------|--------|-----------|
| Low | $150,000 | $5.3M |
| **Base** | **$200,000** | **$7.0M** |
| High | $250,000 | $8.8M |

**Base fair land:** **$7,000,000** [Assumption] pending assessor acres.

---

## Open items

- [ ] Maricopa APN, owner, exact acres for 615 S 51st Ave
