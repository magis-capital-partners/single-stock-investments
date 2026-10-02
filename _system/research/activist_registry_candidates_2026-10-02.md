# Activist registry candidates

**Date:** 2026-10-02
**Registry path:** `_system/frameworks/activist_firm_registry.json`

## Ingest config audit

- OK — site_index/press_wire firms have domains or aliases.

## Unknown / SEC filer IDs (top counts)

| Firm ID | Hits |
|---------|------|
| `sec_filer:brookfield_asset_management_inc` | 78 |
| `sec_filer:telluray_holdings_llc` | 62 |
| `sec_filer:berkshire_hathaway_inc` | 57 |
| `sec_filer:franklin_resources_inc` | 55 |
| `sec_filer:riot_platforms_inc` | 46 |
| `sec_filer:charles_w_ergen` | 44 |
| `sec_filer:warren_e_buffett` | 42 |
| `sec_filer:dennis_j_wilson_anamered_investments_inc_lipo_investments_usa_inc_wilson_5_found` | 33 |
| `sec_filer:bam_partners_trust` | 32 |
| `sec_filer:general_electric_company` | 31 |
| `sec_filer:mjh_partners_ii_llc` | 27 |
| `sec_filer:anamered_investments_inc` | 27 |
| `sec_filer:boots_parallel_1_lp` | 26 |
| `sec_filer:board_of_directors_of_metlife_inc_as_an_entity` | 23 |
| `sec_filer:nextera_energy_inc` | 22 |
| `sec_filer:ae_red_holdings_llc` | 22 |
| `sec_filer:gilead_sciences_inc` | 21 |
| `sec_filer:abel_avellan` | 19 |
| `sec_filer:bbai_ultimate_holdings_llc` | 19 |
| `sec_filer:antony_p_ressler` | 18 |
| `sec_filer:advance_publications_inc` | 18 |
| `sec_filer:horizon_kinetics_asset_management_llc` | 18 |
| `sec_filer:tether_global_investments_fund_s_i_c_a_f_s_a` | 17 |
| `sec_filer:liberty_broadband_corporation` | 17 |
| `sec_filer:walgreens_boots_alliance_holdings_llc` | 17 |
| `sec_filer:roman_dbdr_tech_sponsor_llc` | 17 |
| `sec_filer:deutsche_telekom_ag_irs_identification_number_not_applicable` | 17 |
| `sec_filer:softbank_group_capital_ltd` | 17 |
| `sec_filer:mondel_z_international_inc` | 16 |
| `sec_filer:rockwell_automation_inc` | 15 |

## Sample unresolved rows

- **AAL** `sec_filer:american_airlines_group_inc` (sec_edgar) 2025-12-19
- **ACGL** `sec_filer:arch_capital_group_ltd` (sec_edgar) 2021-07-07
- **ACGL** `sec_filer:arch_capital_group_ltd` (sec_edgar) 2021-02-19
- **ACHR** `sec_filer:hight_drive_growth_llc` (sec_edgar) 2022-05-20
- **ACHR** `sec_filer:capri_growth_llc` (sec_edgar) 2022-06-28
- **ACHR** `sec_filer:capri_growth_llc` (sec_edgar) 2024-11-18
- **ACHR** `sec_filer:brett_adcock` (sec_edgar) 2021-09-27
- **ACHR** `sec_filer:adam_goldstein` (sec_edgar) 2021-09-27
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2023-07-18
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2024-10-08
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2024-10-29
- **ACMR** `sec_filer:shanghai_science_and_technology_venture_capital_group_co_ltd` (sec_edgar) 2023-06-13
- **ACN** `sec_filer:accenture_plc` (sec_edgar) 2023-03-30
- **AIZ** `sec_filer:tpg_advisors_vi_aiv_inc` (sec_edgar) 2018-09-14
- **AIZ** `sec_filer:tpg_advisors_vi_aiv_inc` (sec_edgar) 2018-09-20
- **AIZ** `sec_filer:tpg_advisors_vi_aiv_inc` (sec_edgar) 2019-03-25
- **AIZ** `sec_filer:tpg_advisors_vi_aiv_inc` (sec_edgar) 2018-06-08
- **AIZ** `sec_filer:tpg_advisors_vi_aiv_inc` (sec_edgar) 2018-06-11
- **ALL** `sec_filer:the_allstate_corporation` (sec_edgar) 2020-07-16
- **AMD** `sec_filer:mubadala_investment_company_pjsc` (sec_edgar) 2018-08-02

## Inactive registry firms still indexed

- `citron` — review or remove from indexes
- `hindenburg` — review or remove from indexes
- `iceberg` — review or remove from indexes

## Suggested JSON stub (human applies)

```json
{ "id": "new_firm_id", "name": "Publisher Name", "side": "short", "active": true, "ingest_methods": ["site_index"], "ingest_method": "site_index" }
```

