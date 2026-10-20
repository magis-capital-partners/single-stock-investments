# Discovery pool candidates — 2026-10-20

**Status:** implemented 2026-10-20. The three podcasts, nine YouTube rows, the guest names, and the three officers are in the registries. Second-wave shows (Joys of Compounding, the Good Investing podcast, ACQ2) are still waiting. The leave-off list was not added.
**Checked:** iTunes catalogue counts, live RSS, and YouTube Atom feeds on 2026-10-20.
**Book this is aimed at:** the hold-stance names (Japan Exchange, Amazon, Brookfield, Danaher, FRMO, Alphabet, Gyrodyne, ICE, QuidelOrtho, S&P Global, Teqnion) and the existing public-market pool (value, compounders, capital allocation, special situations, croupiers). a16z stays off.

## How to spend the budget

A podcast with `"watchlist": true` pulls every episode on the feed. An episode whose link page is not a transcript costs about half an hour of Whisper, and the Mac spends two hours at a time on that queue.

A YouTube channel with `"ingest": true` is read from the channel RSS feed. That feed returns the latest 15 videos only. Captions are the cheap path. The uploads playlist is stored so `resolve_youtube_channel.py --verify` can refresh it. Turning that playlist into an ingesting playlist is a separate decision: it walks the whole history through the API. Leave the history off for the channels below.

A name in `podcast_guest_registry.json` makes Monday's search look for that person on other shows, and the episode is kept when the title or notes mention them, a company, or a ticker. That is the cheap way to widen coverage.

## Add these three podcasts

Full feeds. Small enough that the back catalogue is the point. None of them is near the 1,000-episode Podcast Index cap.

| Show | Episodes | Newest | Whisper if no transcript | Why this book |
|---|---:|---|---|---|
| Behind the Balance Sheet | 71 | 2026-10-15 | ~35 hours | Working investors. Recent guests include Tobias Carlisle, Alex Roepers, Rich Pzena, David Gardner. |
| Far From The Finishing Post | 35 | 2026-10-06 | ~18 hours | Capital-cycle managers. A current episode is James Davolos of Horizon Kinetics. |
| Stock Spin-off Investing | 18 | 2026-10-19 | ~9 hours | One situation per episode, ticker in the title (Coffee Stain, Comcast, Lionsgate Studios). |

Behind the Balance Sheet does publish transcripts at `behindthebalancesheet.com/podcasts-singles/`. The RSS `<link>` is a Spotify page, and the fetcher follows that link, so those pages will not be harvested and the 71 episodes go to Whisper. Set `prefer_transcript_urls` anyway so a later link fix picks the site up. The YouTube channel `@BehindTheBalanceSheet` is clips and a trailer in the latest 15 (`Podcast #63 ... Trailer`, "The Investing Lesson David Gardner Got at 18"). Register it with `"ingest": false` so it is not turned on as if it were the show.

Far From The Finishing Post and Stock Spin-off Investing have no transcript tag and no useful YouTube channel. Troy's handle search did not resolve. `@TAML` is a dormant unrelated channel.

```json
{
  "show_id": "behind_the_balance_sheet",
  "title": "Behind the Balance Sheet",
  "rss_url": "https://anchor.fm/s/5f616d54/podcast/rss",
  "homepage": "https://behindthebalancesheet.com/podcasts/",
  "podcast_index_term": "Behind the Balance Sheet Stephen Clapham",
  "prefer_transcript_urls": ["behindthebalancesheet.com", "transcript"],
  "watchlist": true,
  "rate_limit_seconds": 1.0
}
```

```json
{
  "show_id": "far_from_the_finishing_post",
  "title": "Far From The Finishing Post",
  "rss_url": "https://rss.buzzsprout.com/1545967.rss",
  "homepage": "https://www.taml.co.uk/",
  "podcast_index_term": "Far From The Finishing Post Troy",
  "prefer_transcript_urls": ["transcript"],
  "watchlist": true,
  "rate_limit_seconds": 1.0
}
```

```json
{
  "show_id": "stock_spinoff",
  "title": "Stock Spin-off Investing",
  "rss_url": "https://anchor.fm/s/fcb3ca70/podcast/rss",
  "homepage": "",
  "podcast_index_term": "Stock Spin-off Investing Rich Howe",
  "prefer_transcript_urls": ["transcript"],
  "watchlist": true,
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UC_ri3Dcch5ZKslG7Wa-8Kaw",
  "title": "Behind the Balance Sheet",
  "handle": "@BehindTheBalanceSheet",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_ri3Dcch5ZKslG7Wa-8Kaw",
  "uploads_playlist_id": "UU_ri3Dcch5ZKslG7Wa-8Kaw",
  "tier": "duplicate",
  "trust": "broad",
  "ingest": false,
  "dedupe_against_show_id": "behind_the_balance_sheet",
  "guest_ids": [],
  "notes": "Probed 2026-10-20. Latest 15 are clips and a trailer. The podcast feed is the source.",
  "rate_limit_seconds": 1.0
}
```

## Add these YouTube channels

`"ingest": true` on the channel. Captions, latest 15, no podcast twin. After pasting, run `python _system/scripts/resolve_youtube_channel.py --verify`.

| Channel | Handle | Latest window on 2026-10-20 | Trust | Role |
|---|---|---|---|---|
| Markel Group | from the reunion videos | 2024-2026 Reunion and Omaha brunch, Tom Gayner on every meeting | high | operator |
| Brookfield | `@BrookfieldCorporation` | September-October 2026 investor day, including Bruce Flatt with Howard Marks | high | operator |
| The Acquirers Podcast | `@TheAcquirersPodcast` | About one video a day: Korea activism, Markel, Las Vegas, value | high | allocator |
| MicroCapClub | `@MicroCapClub` | Exchanges with James Davolos, Italian HVAC roll-up, Michael Fritzell | high | allocator |
| The Business Brew | `@TheBusinessBrew` | Investor interviews, including a Fairfax episode. Window runs back to Dec 2025 | high | allocator |
| Oaktree | `@OaktreeCapital` | Marks memos plus the 2026 conference | high | allocator |
| Good Investing Talks | from Podchaser, confirmed live | Real interviews (Deere, Nintendo, Cardlytics, Gisela Baur) mixed with Omaha travel tips | broad | allocator |
| Aswath Damodaran | `@AswathDamodaranonValuation` | Essays (SpaceX, indexing, AI) plus two course sessions in the same 15 | broad | broad |

The Acquirers Podcast feed is 450 episodes with no show-site transcript. MicroCapClub's feed is 129. The Business Brew's feed is 204, and its `podcast:transcript` tags are not read by `fetch_podcast_transcript.py` (it follows the episode link, which is Spotify). Leave those three RSS feeds off. The YouTube window is the forward path.

Oaktree overlaps The Memo. Same treatment as the Pabrai channel: ingest the videos, set `dedupe_against_show_id` to `memo_howard_marks`. Title match is what dedupes, so a memo whose video title differs from the podcast title can still arrive twice.

Good Investing's podcast (100 episodes, `https://www.good-investing.net/feed/podcast/`) has episode links on `good-investing.net`. One page fetched today, the Gisela Baur episode, was about 11,000 characters and the body in view was site navigation plus a guest directory. The word "transcript" on that page points at Berkshire meeting transcripts. The length fallback in the fetcher can store that page as if it were the interview. Use the YouTube channel until someone checks a harvested file.

Damodaran's channel has on the order of 1,200 videos. The RSS window is 15. Do not add the uploads playlist as an ingesting playlist.

Markel channel id `UCxvWYkbVv4cDOmAHqikNT0g` was taken from the 2025 Omaha brunch video. `@MarkelGroup` is a 404. `@MKLGroup` is an unrelated channel.

```json
{
  "channel_id": "UCxvWYkbVv4cDOmAHqikNT0g",
  "title": "Markel Group",
  "handle": "",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCxvWYkbVv4cDOmAHqikNT0g",
  "uploads_playlist_id": "UUxvWYkbVv4cDOmAHqikNT0g",
  "tier": "native",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Shareholder reunion and Omaha brunch. Latest 15 on 2026-10-20 runs from the 2024 reunion through the 2026 reunion. Older meetings sit outside the RSS window.",
  "analysis_role": "operator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCVQqnwSap9-WmNWzx7pX4Bw",
  "title": "Brookfield",
  "handle": "@BrookfieldCorporation",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCVQqnwSap9-WmNWzx7pX4Bw",
  "uploads_playlist_id": "UUVQqnwSap9-WmNWzx7pX4Bw",
  "tier": "native",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Core hold BN. Latest 15 on 2026-10-20 are the 2026 investor day, including Bruce Flatt with Howard Marks.",
  "analysis_role": "operator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCJ27FwJZ3hsMrPCviG5gCFg",
  "title": "The Acquirers Podcast",
  "handle": "@TheAcquirersPodcast",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCJ27FwJZ3hsMrPCviG5gCFg",
  "uploads_playlist_id": "UUJ27FwJZ3hsMrPCviG5gCFg",
  "tier": "native",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Forward window only. The RSS podcast is 450 episodes (https://anchor.fm/s/9603714/podcast/rss) and stays off. This channel publishes about one video a day, so the 15-slot feed is about two weeks.",
  "analysis_role": "allocator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCzX4HLkD7eXBgzVwHMZlhmg",
  "title": "MicroCapClub",
  "handle": "@MicroCapClub",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCzX4HLkD7eXBgzVwHMZlhmg",
  "uploads_playlist_id": "UUzX4HLkD7eXBgzVwHMZlhmg",
  "tier": "native",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Forward window only. Podcast feed is 129 episodes (https://anchor.fm/s/fa8b8aa8/podcast/rss) and stays off. 2026-10-19 upload is James Davolos on exchanges. Two of the latest 15 are #shorts and the metadata gate rejects those.",
  "analysis_role": "allocator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCBywIfdQy7Nyb2RfRb_Z0eg",
  "title": "The Business Brew",
  "handle": "@TheBusinessBrew",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCBywIfdQy7Nyb2RfRb_Z0eg",
  "uploads_playlist_id": "UUBywIfdQy7Nyb2RfRb_Z0eg",
  "tier": "native",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Forward window only. Podcast feed is 204 episodes (https://anchor.fm/s/8d780590/podcast/rss) and stays off. Includes Revisiting Fairfax Financial.",
  "analysis_role": "allocator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCfzbRPUn_YvJCl6npbZKXJA",
  "title": "Oaktree",
  "handle": "@OaktreeCapital",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCfzbRPUn_YvJCl6npbZKXJA",
  "uploads_playlist_id": "UUfzbRPUn_YvJCl6npbZKXJA",
  "tier": "guest",
  "trust": "high",
  "ingest": true,
  "dedupe_against_show_id": "memo_howard_marks",
  "guest_ids": ["marks_credit_cycle"],
  "notes": "Memos plus the 2026 Oaktree conference. Item-level dedupe against The Memo.",
  "analysis_role": "allocator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UC5Z-C01O2VlpeD1rMs_HS2Q",
  "title": "Good Investing Talks",
  "handle": "",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC5Z-C01O2VlpeD1rMs_HS2Q",
  "uploads_playlist_id": "UU5Z-C01O2VlpeD1rMs_HS2Q",
  "tier": "native",
  "trust": "broad",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "European and US compounder interviews, plus Omaha travel guides in the same window. trust=broad so the transcript gate drops the packing tips. A second channel, @GoodInvesting (UCOv_nc2p0bt5jIr1D78VqFg), is a different feed. Podcast stays off until a harvested episode page is confirmed to be the interview and not the site chrome.",
  "analysis_role": "allocator",
  "rate_limit_seconds": 1.0
}
```

```json
{
  "channel_id": "UCLvnJL8htRR1T9cbSccaoVw",
  "title": "Aswath Damodaran",
  "handle": "@AswathDamodaranonValuation",
  "rss_url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLvnJL8htRR1T9cbSccaoVw",
  "uploads_playlist_id": "UULvnJL8htRR1T9cbSccaoVw",
  "tier": "native",
  "trust": "broad",
  "ingest": true,
  "dedupe_against_show_id": null,
  "guest_ids": [],
  "notes": "Rolling essays. Course archive is about 1,200 videos and must not be ingested as a playlist. Two course sessions were inside the latest 15 on 2026-10-20.",
  "analysis_role": "broad",
  "rate_limit_seconds": 1.0
}
```

## Add these people

Monday's search returns a handful of episodes per query. A name here catches a guest spot on a show we do not subscribe to.

On the existing `hk` guest, add aliases `Steven Bregman` and `James Davolos`, and search queries `James Davolos` and `Steven Bregman`. The MicroCapClub exchange episode is filed under Davolos. The current queries are `Horizon Kinetics podcast` and `Murray Stahl Horizon`, which do not contain his name.

New `guest_only` rows, priority 2:

| guest_id | Who | Search queries | Hole this fills |
|---|---|---|---|
| gayner | Tom Gayner / Markel | Tom Gayner, Markel Gayner podcast | Insurance compounder. The Markel channel is the meetings. This catches him everywhere else. |
| thorndike | Will Thorndike | Will Thorndike, The Outsiders podcast | Capital allocation. The pattern behind Teqnion and Danaher. |
| mauboussin | Michael Mauboussin | Michael Mauboussin, Mauboussin podcast | Expectations and base rates. He is a guest, and he has no show of his own in this pool. |
| mayer | Chris Mayer | Chris Mayer, 100 Baggers podcast | Long-horizon compounders. |
| dorsey | Pat Dorsey | Pat Dorsey, Dorsey moat podcast | Moats, the compounder lens. |
| wilkinson | Andrew Wilkinson / Tiny | Andrew Wilkinson Tiny, Tiny Capital podcast | Serial acquirers, the public-market cousin of Teqnion. His own feeds are tiny (Tiny Office Hours is 4 episodes, Never Enough is 11). |
| fritzell | Michael Fritzell / Asian Century Stocks | Michael Fritzell, Asian Century Stocks | Japan and Asia. The hold list has Japan Exchange, Teqnion's region, and several Tokyo names. No current show covers that. |
| roepers | Alex Roepers | Alex Roepers, Atlantic Investment Management | Mid-cap activism. He is a recurring Behind the Balance Sheet guest. |
| nygren | Bill Nygren / Oakmark | Bill Nygren, Oakmark podcast | Quality value. Named on the Behind the Balance Sheet catalogue. |
| huber | John Huber / Saber Capital | John Huber Saber, Saber Capital podcast | Concentrated quality. |
| brenton | Andrew Brenton / Turtle Creek | Andrew Brenton, Turtle Creek podcast | Canadian compounders. |

`officer_directory.json` currently has one person, Martin Carlesund of Evolution. Two hold-stance operators are worth the same treatment:

- Johan Steene, Teqnion (`TEQ.ST`). The deep dive already treats him as founder CEO. Daniel Zhang appears with him in the Value Bridge interview indexed under `TEQ.ST/third-party-analyses/references.md`. Confirm both against the latest filing before adding.
- Bruce Flatt, Brookfield. The 2026-10-01 Brookfield upload is titled as a fireside chat with him and Howard Marks.

The other hold-stance CEOs (Japan Exchange, Danaher, ICE, S&P Global, Amazon, Alphabet) belong in that file too, once a filing is the source. This pass did not re-read those proxies.

## Second wave, after the first harvest has a known admit rate

| Source | Size | Why it waits |
|---|---|---|
| Joys of Compounding | 49 episodes, `https://feeds.megaphone.fm/aoi`, newest 2026-10-07 | Same Colossus family as Invest Like the Best. Episode 40 is Luca Ferrari of Bending Spoons on acquisitions. Add with `prefer_transcript_urls` of `joincolossus.com` and `transcript`. Colossus transcript pages have required a free login. If the harvest comes back empty, this is another Whisper queue of about 25 hours. |
| Good Investing Talks podcast | 100 episodes | Only after one harvested page is confirmed to be the interview. The YouTube channel above is the forward path. |
| ACQ2 by Acquired | 112 episodes, `https://feeds.transistor.fm/acq2` | Interviews (Shopify, Andrew Ross Sorkin). Acquired itself is already in the pool. Closer to that show's tech-history lane than to a stock pitch. |

## Leave these off

| Source | Episodes or what the feed actually is | Why it stays off |
|---|---|---|
| Odd Lots | 1,297 | Over the 1,000 cap, so the older catalogue needs Podcast Index keys. Three episodes a week of macro. This is the a16z problem: one show becomes a quarter of the corpus. |
| We Study Billionaires | 1,232 | Same cap, and a large share of episodes are personal finance. |
| Masters in Business | 817 | Near the cap. The feed mixes hour-long interviews with 20-minute segments. |
| Excess Returns | 577 | Useful guests, and Substack has transcripts, but the episode link is not that page. A 577-episode Whisper queue. |
| Founders | 462 | David Senra reading biographies. Business history, little ticker discovery, and no published transcript to lean on. |
| The Knowledge Project | 291, `https://feeds.megaphone.fm/FSMI7575968096` | Broad life-and-business show. Hand-edited transcripts sit behind a Farnam Street membership. Ackman and Munger episodes are already in range of the guest search. |
| How I Invest | 444 | Allocator interviews. Capital Allocators is already the watchlist show for that job. |
| The Meb Faber Show | 722 | Asset allocation and factors. Flirting with Models already covers that lane, and its registered feed is alive (128 items, newest 2026-10-12). |
| Rational Reminder | 454 | Evidence-based personal finance. |
| Grant's Current Yield | 209, newest in the feed 2025-12-13 | Credit, which The Memo already covers. The site is the subscription. No transcript in the feed. |
| In Good Company | 294, `https://feeds.acast.com/public/shows/622618c7057f3400120d15db` | This is the Norges Bank show. That channel is already `"ingest": true`. A second copy. |
| The Special Situations Report | `https://anchor.fm/s/ff8c7a94/podcast/rss` | Already in the registry as `special_situation_investing`. |
| 50X | 9 | Colossus case studies, newest 2025-05-21, and the subject in the window is private (Asurion). |
| Value Hive, Focused Compounding, Chit Chat Stocks, The Compound and Friends | 350 to 824 | Large, mixed, and the same ideas already arrive through Yet Another Value, Business Breakdowns, and Invest Like the Best. |

YouTube channels that resolved to the wrong thing, or to marketing:

| What was tried | What came back |
|---|---|
| `@SPGlobal` | A channel whose latest titles are a Holi celebration and "Har Har Mahadev". The feed title is "SP Global". Name match would have accepted it. Leave it unresolved. |
| `@DanaherCorporation` | Real Danaher. Latest titles are partnership and sustainability films, from June 2026. An investor-day playlist would be the add. The channel feed is brand. |
| `@ICE_Markets` | Real ICE, and one conversation with Apollo, inside a window of product spots (Flat Branch Home Loans). Same pattern as Danaher. |
| `@PershingSquare` | Dormant about 17 years. Target-era videos. |
| `@RobinHoodNYC` | Page title "ROBIN HOOD", feed title "Fair Housing Justice Center". The 2016 Druckenmiller conference video is a reupload on a dormant personal channel. |
| `@iveybusiness` | Feed is Western University ("Find Your Community"). The Ben Graham Centre stays in `unresolved`, as it was on 2026-09-03. |
| `@BaillieGifford` | Feed title came back "Scottish Mortgage". Growth-trust marketing. |
| `@LondonValueInvestor` | Dormant since 2022. |
| Fairfax, Horizon Kinetics, Giverny, Constellation | No public channel under the handles tried. Fairfax India has an empty feed. |

## Order to paste

1. The three podcast objects, plus the Behind the Balance Sheet YouTube row with `"ingest": false`.
2. Markel, Brookfield, MicroCapClub, Acquirers, Business Brew, Oaktree. Then Good Investing Talks at `trust: broad`. Damodaran last, and only the channel, not its course playlist.
3. The `hk` aliases, then the new guest rows, then Johan Steene and Bruce Flatt in the officer directory after the filing check.

Run `resolve_youtube_channel.py --verify` before the next video discover. The first Monday after the podcast paste is the Whisper bill: about 124 episodes across the three shows, on the order of 60 hours, behind whatever is already in `whisper_backlog.json`.
