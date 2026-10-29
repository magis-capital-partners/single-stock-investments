# Desk lens: Activism campaigns (Activism desk)
Written 2026-10-29 by Activism desk. Scope: how a 13D campaign or a short report is likely to play out (whether the board gives ground, how fast, whether a contest settles, whether a short claim gets confirmed). It never decides whether a business is worth owning, never values a company, and is never by itself the reason to buy or short. Records and case data: `/workspace/shared/magis/activist_records/` (one file per firm, `index.json`, `score.py`).

## 1. The lens
- A 13D is a dated, sworn statement of intent. Read the cover page (who, how much) and Item 4 (what they want) at the filing date, and grade the outcome later from filings. Never mix the two.
- What moves boards is a formal contest step (nomination notice, slate, special-meeting request), not stake size or a 13G-to-13D switch alone. Once that step is filed, companies almost always settle before the vote, usually within about three months.
- Board seats are cheap for a board to give. A sale is not. Sale and strategic-alternative asks take longer and often end in seats with no sale.
- Not every 13D is a campaign. Control holders, merger or spin recipients and financing investors file 13Ds too. Classify first.
- A short report is a claim, not a finding. In our sample a listed confirming event (restatement, SEC/DOJ action, auditor resignation, guidance or dividend cut, delisting) followed about 1 report in 8, and specific "hard" claims did no better than soft ones.

## 2. Rules (decision tests)
Score format: fired / right / wrong / mixed (hit rate = right ÷ (right + wrong)). "untested" when fired < 5. Graded on cases in `activist_records/index.json` → `rule_cases`, as of 2026-10-29.

| ID | Test (one line, answerable yes/no or with a number) | Source (document, date, page or accession) | Proven wrong if | Score (fired / right / wrong / mixed) | Cases |
|---|---|---|---|---|---|
| ACT-01 | Did the filer switch from 13G to 13D with a specific Item 4 ask? If yes, expect a board concession within 90 days. | ETWO 13D 0000902664-23-005125; INV 13D 0002041777-26-000001; PBT 13D 0001104659-25-098559 | Fewer than half of switch-with-ask cases get a concession within 90 days, once n ≥ 5 | untested (3 / 1 / 1 / 1) | ELL-ETWO (143 d), SFV-PBT (67 d), ASC-INV (mixed) |
| ACT-02 | Does Item 4 at the first 13D name a concrete demand (seats, CEO, sale, structure)? If yes, expect a concession within 90 days. | 13Ds listed in Cases; settlement 8-Ks in firm files | Hit rate falls below 50% over the next 10 cases | 11 / 6 / 4 / 1 (60%) | right: ELL-LUV, SBD-ROG23, SBD-ALIT, SBD-BILL, ICN-JBLU, SFV-PBT; wrong: ELL-ETWO, JAN-RPD, JAN-LW, JAN-ALKT; mixed: ASC-INV |
| ACT-03 | Does the ask (at filing or added later) include a sale or strategic-alternatives review? If yes, expect the first concession more than 90 days after the first 13D, and seats rather than a sale. | AQN 6-K 0001174169-23-000043; ETWO 8-K 0000950170-24-027603; RPD 8-K 0001193125-25-060853; LW 8-K 0001679273-25-000041; TRIP 8-K 0001193125-26-118642 | Sale-type asks get a concession within 90 days in most new cases | 5 / 4 / 1 / 0 (80%) | right: ELL-ETWO 143, JAN-RPD 175, JAN-LW 255, SBD-TRIP 262; wrong: SBD-AQN 41 (review predated the 13D) |
| ACT-04 | Has the activist filed a formal contest step (nomination notice, slate, special-meeting request)? If yes, expect a settlement before any vote. | settlement 8-Ks/6-Ks in firm files; PBT vote 8-K 0001193125-25-324783 | Two or more of the next five contest cases go to a vote | 10 / 9 / 1 / 0 (90%) | right: ELL-LUV, SBD-ROG23, SBD-AQN, SBD-ALIT, SBD-QRVO, SBD-TRIP, SBD-BILL, JAN-RPD, JAN-LW; wrong: SFV-PBT (trust, no board; vote held and won) |
| ACT-05 | Days from the first contest step to settlement ≤ 90? | same as ACT-04 | Median gap in new cases exceeds 90 days | 10 / 8 / 2 / 0 (80%) | right: JAN-RPD 10, SBD-AQN 28, SBD-TRIP 33, SBD-QRVO 35, SBD-BILL 40, ELL-LUV 71, SBD-ROG23 73, SBD-ALIT 79; wrong: JAN-LW 91, SFV-PBT (no settlement) |
| ACT-06 | Is the 13D a control (≥20%), merger-derived, spin-derived or financing holding with no activist demand? If yes, do not score it as a campaign and do not expect an issuer sale within 12 months. | SDRL 0000902664-23-002466; TFPM 0000902664-23-002314; UNIT 0000902664-25-003448; UAN 0001104659-24-035665; SEG 0000930413-24-002266; MGM 13D/A 0001104659-26-119439; ANGI 0001104659-25-031452 | An issuer in this class agrees to a sale within 12 months | 7 / 7 / 0 / 0 (100%) | ELL-SDRL, ELL-TFPM, ELL-UNIT, ICN-UAN, PSH-SEG, IAC-MGM (holder's own bid withdrawn 2026-09-23), IAC-ANGI |
| ACT-07 | Did a 13D/A take the filer below 5%? If yes, treat the campaign as over: no new 13D on that issuer within 12 months. | exit 13D/As in firm files; ALKT 13D 0000902664-26-002944 | Two or more re-entries within 12 months in the next ten exits | 7 / 6 / 1 / 0 (86%) | right: SBD-ROG23, VAC-RKT, SBD-HR, SBD-FTRE, JAN-LW, ANC-MBCN; wrong: JAN-ALKT (back in 48 days) |
| ACT-08 | Does the firm's record on earlier resolved campaigns (at the filing date) predict concession vs no concession better than stake size at filing (≥ median 7.8%)? | firm files; leave-one-out on 13 cases with a prior record | Track record does no better than stake size or the always-yes base rate over 10 new cases | 13 / 12 / 1 / 0 (92%); stake size 9 of 13; always-yes 11 of 13 | right: 12 cases (10 Starboard, ELL-LUV, ICN-CTRI, VAC-LLYV); wrong: SBD-MTCH. Edge over base rate is one case (VAC-LLYV). Provisional. |
| ~~ACT-09~~ | ~~Is the short claim hard (specific, checkable accounting/legal fact)? If yes, expect a listed confirming event more often than for soft claims.~~ Retired 2026-10-29. | short-report tables in firm files | Hard-claim confirm rate ≤ soft-claim rate (met) | 17 / 2 / 15 / 0 (12%) vs soft 1 of 8 (12.5%) | hard confirmed: muddy_waters:APP [web], fuzzy_panda:NUAI (restatement, not on core claim); soft confirmed: muddy_waters:BXMT |
| ACT-10 | Is there only a short report (no filing-based confirmation yet)? If yes, assume no listed confirming event within the next 6–18 months; size and label it as a claim. | short-report tables; Fugazi scorecard (existing, not duplicated) | Confirming events follow in more than 25% of reports aged ≥ 180 days | 39 / 34 / 5 / 0 (87%) | wrong (confirmed): muddy_waters:APP [web], muddy_waters:BXMT, fuzzy_panda:NUAI, fugazi:ADN, fugazi:DTCK. Rest in index.json |

- **Concession** means the first settlement or cooperation agreement, board seat, strategic review or sale announcement, or activist-won vote. A CEO change alone does not count. Days are from the first 13D filing date; a concession signed before the 13D counts as day 0.
- **Candidate mapping (2026-10-29):** candidate 1 (13G→13D switch) kept as ACT-01, untested, and broadened as ACT-02. Candidate 2 (sale asks resolve faster) failed 1 of 5 (sale median 175 days vs 69.5 days for other asks) and is reversed as ACT-03. Candidate 3 narrowed to "settle before the vote" (ACT-04), because most settlements came after nominations were filed, not before the nomination deadline; ACT-05 adds the clock. Candidate 4 (hard short claims confirm more often) is retired as ACT-09 and replaced by ACT-10. Candidate 5 kept as ACT-06. Candidate 6 kept as ACT-08, provisional. ACT-07 is new.

## 3. Quick screen
- ACT-01, ACT-02: EDGAR submissions for the filer; prior SC 13G / SCHEDULE 13G on the same issuer; Item 4 text (XML `<item4>` on post-Dec 2024 filings).
- ACT-03: Item 4 and any 13D/A letter exhibit for "sale", "strategic alternatives", "review of all options".
- ACT-04, ACT-05: 13D/A exhibits (nomination notice, slate press release, special-meeting request); issuer 8-K items 1.01/5.02 for cooperation agreements.
- ACT-06: cover-page percent (≥20%), and Item 3/4 for merger, spin, rights-offering or preferred-financing language.
- ACT-07: `<percentOfClass>` (or row 13) on each 13D/A; a new SCHEDULE 13D on the same issuer.
- ACT-08: `activist_records/<firm>.md` summary tables.
- ACT-10: issuer 8-K items 4.01, 4.02, 3.01; Form 25; full-text search for "subpoena", "Wells notice", "short seller".

## 4. Failure modes and falsifiers
- Sample is Starboard-heavy: 11 of 24 campaigns and 10 of 13 ACT-08 cases. Elliott, Trian, Pershing and Ancora run most recent work below 5%, so EDGAR shows few or no 13D campaigns for them (thin coverage).
- Most first 13Ds have a generic Item 4 (Starboard, ValueAct). The real ask often appears weeks later (AQN 7 days, TRIP 229 days). ACT-02 only uses the ask at filing; later asks are dated separately.
- SFV-PBT is a royalty trust with a trustee, not a board, so it fails ACT-04/05 by structure. Consider excluding trusts once more cases exist.
- SBD-AQN: the company said its sale review was already under way before the 13D, so the 41-day "concession" may not be caused by the campaign.
- ASC-INV: board changes at 71 days were not made with Ascent, and Ascent said on 2026-05-05 it would stay inactive, then escalated on 2026-10-19. Scored mixed.
- Short-report outcomes: guidance cuts were not scanned systematically; APP's SEC probe is press-reported [web], not in EDGAR; NUAI's restatement is not on the core claim. Fugazi has no claim field, so it feeds ACT-10 only.
- Unresolved campaigns (ICN-MNRO, VAC-FWONA, JAN-ALKT, ASC-INV, SFV-PBT final vote 2026-11-23) will move ACT-02, ACT-04 and ACT-08 when they close.

## 5. Sources and evidence
- [F] SEC EDGAR, read 2026-10-29: submissions API, full-text search (forms SC 13D, SCHEDULE 13D and amendments), filing archives. Every accession is in the firm files and `index.json`.
- [F] Issuer 8-Ks and 6-Ks for settlements, reviews, sales, votes, restatements and auditor changes (accessions in firm files).
- [WEB] Short-report dates and claims: muddywatersresearch.com; repo snapshots of sprucepointcap.com and fuzzypandaresearch.com under `/workspace/ssi_ro/_system/reference/activist-reports/`.
- [WEB] APP SEC probe: Bloomberg report of 2025-10-06, also Reuters and CNBC. ELF denial: company press release 2024-11-21.
- [F]/[WEB] Fugazi outcomes: existing scorecard `/workspace/ssi_ro/_system/reference/activist-reports/short_scorecard/Fugazi_Research.md` (reused, not duplicated).
- [I] The claim-type split (hard/soft), the ask-type labels and the "concession" definition are desk judgments, written down in `activist_records/README.md`.

## 6. Change log
- 2026-10-29: lens created with ACT-01 to ACT-10 scored on 24 campaigns (19 resolved), 8 non-campaign 13Ds (7 used in ACT-06) and 39 short reports aged 180+ days (25 from Muddy Waters, Spruce Point and Fuzzy Panda; 14 from the Fugazi scorecard). ACT-09 (candidate 4) retired on the same day: hard claims confirmed 2 of 17 vs soft 1 of 8. Candidate 2 reversed into ACT-03. Reason: first scoring against activist_records. Triggering cases: all in activist_records/index.json.
