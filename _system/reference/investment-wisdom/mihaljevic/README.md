# John Mihaljevic — Manual of Ideas

**Primary (licensed):** `Manual-of-Ideas-1st-Edition-2013.epub` or `Manual-of-Ideas-2nd-Edition.pdf`  
**Full text (after EPUB install):** `Manual-of-Ideas-full-text.txt`  
**Workspace extract:** `Manual-of-Ideas-chapter-reference.txt` — chapter map + key takeaways  
**Comprehensive rules:** `_system/frameworks/moi_company_evaluation.md`  
**Framework pointers:** `moi_lens.md`, `idea_funnel.md`, `special_situation_lens.md`, `equity_stub_valuation.md`

## Install licensed EPUB or PDF

1. Purchase from [Wiley](https://www.wiley.com/en-us/The+Manual+of+Ideas%3A+The+Proven+Framework+for+Finding+the+Best+Value+Investments%2C+2nd+Edition-p-9781119270324) or your retailer.
2. Copy to `.source/` **or** set `MOI_EPUB_SOURCE` / `MOI_PDF_SOURCE`.
3. Run:

```bash
python _system/scripts/download_moi_book.py
python _system/scripts/build_wisdom_manifest.py
```

EPUB install also writes `Manual-of-Ideas-full-text.txt` for agent full-text read. If no source is found, the script builds `Manual-of-Ideas-Marvin-Reference.pdf` from the chapter extract (not a substitute for the book).

## Apply in Marvin

| MOI chapter | Marvin hook |
|-------------|-------------|
| 1 Capital allocator | `moi_lens.md` — owner mindset, valuation bounds |
| 2 Deep value | `deep_value` moi_bucket; net-net guardrails |
| 3 SOTP | `optionality_valuation.md` — discount magnitude |
| 4 Good + cheap | `quality_checklist.md` — Magic Formula misuses |
| 5 Jockey | `hohn_business_analysis.md` — management invert |
| 6 Follow leaders | `mental_models.md` — cloning conviction score |
| 7 Small cap | `idea_funnel.md` — investability screen |
| 8 Special situations | `special_situation_lens.md` |
| 9 Equity stubs | `equity_stub_valuation.md` |
| 10 International | `investment_process.md` — non-US checklist |

**Memory tag:** `[PROPOSED MOI]` until human promotes to `_system/memory/MEMORY.md`.
