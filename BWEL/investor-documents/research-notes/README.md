# BWEL — Research notes (non-SEC)

Third-party books, articles, and human-provided PDFs. Not in Lawrence base IRR unless promoted in `_system/frameworks/third_party_sources.md`.

## The King of California

| Field | Value |
|-------|--------|
| **Title** | *The King of California: J.G. Boswell and the Making of a Secret American Empire* |
| **Authors** | Mark Arax and Rick Wartzman |
| **Publisher** | PublicAffairs, 2003 |
| **ISBN** | 978-1-58648-028-8 |
| **Role** | Historical / journalistic context on Boswell family, Tulare basin, water, and land (not a filing) |

**Expected path (full PDF, after borrow):** `Arax_Wartzman_2003_The_King_of_California.pdf`

**Search-inside excerpts (in repo):**

- `King_of_California_OL_search_excerpts.md` / `.json` — Open Library FTS harvest (~3,400 paragraphs; not full text)
- Regenerate: `python3 BWEL/investor-documents/scrape_king_of_california.py`
- Reader: https://archive.org/details/kingofcalifornia0000arax/page/n5/mode/2up

**Obtain full PDF:**

1. **Internet Archive (borrow):** https://archive.org/details/kingofcalifornia0000arax  
2. Save PDF to `research-notes/`, then: `python3 BWEL/investor-documents/scrape_king_of_california.py --pdf research-notes/Arax_Wartzman_2003_The_King_of_California.pdf`
3. **Purchase / e-book:** ISBN above

Marvin uses this for **background on water/land history** only; acre-foot counts and valuations must still tie to **OTC annuals** or independent appraisal.
