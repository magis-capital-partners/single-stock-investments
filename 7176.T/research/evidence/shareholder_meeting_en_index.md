# Shareholder meeting notices — English translations (7176.T)

Full-text English translations (machine, paragraph-by-paragraph). Japanese PDFs use embedded fonts; raw PDF extract was unusable for claims until `_text_en` was refreshed.

| Date | Document | English file |
|------|----------|--------------|
| 2025-06-06 | 19th AGM notice (`19NoticeJ`) | `research/evidence/_text_en/20250606_第19期定時株主総会招集ご通知__19NoticeJ.pdf.en.txt` |
| 2024-06-05 | 18th AGM notice (`18NoticeJ`) | `research/evidence/_text_en/20240605_第18期定時株主総会招集ご通知__18NoticeJ.pdf.en.txt` |
| 2023-07-19 | Extraordinary AGM (`17-1NoticeJ`) | `research/evidence/_text_en/20230719_臨時株主総会招集ご通知__17-1NoticeJ.pdf.en.txt` |
| 2023-06-07 | 17th AGM notice (`17NoticeJ`) | `research/evidence/_text_en/20230607_第17期定時株主総会招集ご通知__17NoticeJ.pdf.en.txt` |
| 2016-11-29 | Record date notice (EGM) | `research/evidence/_text_en/20161129_臨時株主総会召集のための基準日設定公告__Pnotice1611-2.pdf.en.txt` |

**Regenerate:**

```bash
python3 _system/scripts/translate_text_file.py \
  7176.T/research/evidence/_text/<basename>.txt \
  7176.T/research/evidence/_text_en/<basename>.en.txt \
  --source-note 03_Events/Shareholder_Meeting/<pdf>
```

**Note:** `build_management_evidence.py` keyword claim patterns are for transcripts/mining names; AGM notices may still show **0 claims** unless patterns are extended. Full prose is in the `.en.txt` files above.
