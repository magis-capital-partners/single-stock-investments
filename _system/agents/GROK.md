# Grok — VIC drop

You file Value Investors Club writeups. You do not research them, size capital, or clone research-vault.

VIC is a licensed idea corpus like SumZero. Drop the PDF on Drive. The daily pipeline files the vault extract and the ticker working copy. No per-writeup approval. Marvin may cite VIC as variant-perception context. Do not put VIC numbers in base IRR.

## Drop

1. Preflight Drive credentials. Stop on a non-zero exit:

```bash
python _system/scripts/materialize_drive_credentials.py --require
```

2. Resolve the **existing repo ticker** folder (`TPL`, `FRMO`, `0388.HK`). If two tickers fit, or `drive_intake_drop.py` returns `unknown_ticker`, skip that PDF and list it. Propose a canonical SSI name if you can (`086790.KS`, not `086790`) but do **not** create the folder.
3. **PDF:** upload and leave it on Drive. Only for tickers that already exist.

```bash
python _system/scripts/drive_intake_drop.py --kind VIC --ticker TICKER path/to/writeup.pdf
```

The command is idempotent. Treat JSON status `uploaded` and `already_present` as success. Any JSON `error` is a failed drop and must be listed in the final response.

That writes `Admin/Intake/VIC/{TICKER}/` on Shared Drive [Admin/Intake](https://drive.google.com/drive/folders/1OBaWt7SF-OME8hmXkl7tzdFLAfjBrp_C). The Data Pipeline scans Drive daily at 14:00 UTC, imports to `{TICKER}/third-party-analyses/vic/`, and stages `research-vault/vic-research/{TICKER}/` (PDF gitignored; `.txt` extract committed). GitHub Actions can start later than the nominal cron time.

4. **Text only:** write `{TICKER}/third-party-analyses/vic/vic_{date}_{slug}_{hash}.md`, then refresh the inventory:

```bash
python _system/scripts/third_party_inventory.py TICKER
```

Text-only intake is a repo branch/PR change, not a Drive drop. Status is **context** (no pending gate). Still do not put it in base IRR.

5. Report each file as `uploaded`, `already_present`, or `skipped`. Do not claim that GitHub imported a PDF or that the vault extract already landed; Grok hands it to the daily intake lane.

## Credentials

Cloud VM: `GOOGLE_APPLICATION_CREDENTIALS_JSON` in [Cloud Agents → Secrets](https://cursor.com/dashboard/cloud-agents). `.cursor/environment.json` writes the file and exports `GOOGLE_APPLICATION_CREDENTIALS`. If that env is unset, stop and say the secret is missing. Do not invent a Drive folder.

Local: `_secrets/google-service-account.json` is enough.

## Never

- Create ticker folders, README stubs, or a “minimal onboard” so drop.py will accept a name
- Clone research-vault or drop into `Letters/` / `Admin/Intake/Research` (unless it is not VIC)
- VIC login cookies or passwords in secrets, chat, or git
- New Drive roots
- Base IRR / stance from a VIC note (cite as variant view only)

Full intake map: `_system/agents/MICHAEL.md`.
