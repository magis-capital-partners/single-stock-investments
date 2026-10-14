# Greenblatt reference

Catalogue pointer only. No book text is committed to this repository; authorized text extracts belong in the private research vault under `investment-wisdom/greenblatt/`.

| Title | Where the copy is | Text extract | Used by |
|---|---|---|---|
| *You Can Be a Stock Market Genius* (Joel Greenblatt, 1997) | Shared Drive `Research Sources/Books/Value Investing/Joel Greenblatt`, file id `1LwfqcmaUU7X8uCMsoteeF8nRFt9mDNRe` (56.9 MB, 150 pages) | **Not yet.** The Drive copy is a page scan with no text layer (pymupdf read 2,742 characters across 150 pages on 2026-10-12). It needs OCR before a vault extract exists: `fitz` with Tesseract (`page.get_textpage_ocr()`) or any OCR pass, then commit the `.txt` to `research-vault/investment-wisdom/greenblatt/` and link it from `_system/data/separations/README.md` and the Special Situations desk prompt. | Special Situations desk ("the book is the checklist" in `_system/prompts/grok_scan_agents.md`); the magic-formula rules in `_system/lenses/personas.json` are public and need no text. |

The Special Situations desk's spinoff, merger-security, warrant, restructuring and forced-seller lanes follow this book's chapter structure (`_system/scripts/build_special_situations.py`). Until the extract exists, a desk bot that cannot open the Drive PDF must say the book was unread rather than paraphrase it from memory.
