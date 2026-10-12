# Local hub render checks

Run `node dashboard/preview/spa-harness.mjs <scratch-output-directory>` from the repository root. The harness calls production render functions with committed data and checks the desk brief, candidate fields, six-cell lens strip, reverse-split panel, split-off terms, forced-seller rows and MDT Separation card. It also checks that the feed-status payload contains the new feed IDs. Its output directory is optional and should stay outside git.

For the actual SPA, run `python -m http.server 8795 --bind 127.0.0.1 --directory dashboard`, then open `http://127.0.0.1:8795/`. Verify Ideas > Inbox, Shorts, Special Situations, MDT detail and Insights > Data Health. Capture browser screenshots and console errors separately. Local authenticated `api/*` requests return 404; the harness does not claim to exercise those APIs or the hosted Access login.

Existing Michael preview files are separate research artifacts. The harness never modifies them, the source ledgers, derived payloads or browser storage in a user's session.
