# Box R: the reverse-split collector on Lightsail

Box R is one Lightsail instance that does exactly two things, all day, every day:

| Service | What it does | Replaces |
|---|---|---|
| `rs-collector` | `collector.mjs --watch`: SEC and press-release feeds, Databento quotes, IBKR borrow file, simulated entries and exits, checkpoints | the `collect` job of `reverse-split-live.yml` (270-minute GitHub sessions) |
| `rs-market-status` | `market-status-source.mjs`: Nasdaq Trader halts and short-sale restrictions, once a minute in session | the `observe` job of `reverse-split-market-status.yml` |

Everything else stays on GitHub: the deploy job (tests and D1 migrations), financial preparation,
financial harvest, borrow history, and the review watchdog. The watchdog is deliberately not on
this box, so a dead box is still noticed.

**What box R never has:** broker or order access, an IB Gateway client id, ThetaData credentials,
an NY4 SSH key, Clear Street / DC-Execution keys, or a GitHub token. It is research only; no
cohort can place an order. It is not NY4 and not the SPX nightly box; `bootstrap.sh` refuses to
run on a machine with trading units on it.

**Who may write.** Only the holder of the collector lease (D1 `rs_state`) writes research state,
and only the holder of `exchange_status_lease` writes market-status evidence. The repository
variable `RS_COLLECTOR_HOST=lightsail` stops GitHub from starting its own collector and
observer, so after cutover GitHub cannot even try.

## Files

| File | Purpose |
|---|---|
| `bootstrap.sh` | One-time setup on a fresh Ubuntu 24.04 instance. Safe to re-run. Does not start the services. |
| `run.sh` | What systemd runs. Same commands as the GitHub jobs, without the GitHub-only variables. |
| `rs-collector.service`, `rs-market-status.service` | The two services. Memory limits are a starting point for the load test. |
| `update.sh`, `rs-update.service`, `rs-update.timer` | 20:30 ET nightly: move to a GitHub-tested `origin/main`, restart, roll back on failure. |
| `reverse-split-live.env.example` | Template for `/etc/reverse-split-live.env`. Names only, never values. |
| `soak-report.sh` | Read-only: prerequisites, memory now/peak, restarts, CPU, disk, recent errors. |

The older `../reverse-split-collector.service` is superseded: its 512 MB and 25% CPU limits do not
fit the measured workload (3.9 GiB in use, 5.6 GiB peak on 2026-11-16).

## 1. Owner steps (AWS and Cloudflare)

Only the owner can do these.

1. **Instance.** Lightsail, region us-east-1, Linux, Ubuntu 24.04 LTS, the 8 GB / 2 vCPU / 160 GB
   plan. Name it `rs-box-r`. The 8 GB plan is a load-test candidate, not a proven fit (section 4).
2. **Static IP.** Create one and attach it.
3. **Firewall** (instance > Networking). Remove the default HTTP rule. Restrict SSH (22) to your
   own IP. Nothing else inbound: both services only make outgoing calls.
4. **Snapshots.** Turn on automatic daily snapshots. They protect the machine setup; the research
   data is protected by the collector's own checksummed checkpoints in R2.
5. **Alarms** (instance > Metrics, email notification): status check failed; CPU burst capacity
   below 20%. Lightsail CPU is burstable, so a 2-vCPU listing is not two full cores all day.
6. **Cloudflare token.** Create a new API token for this box only, with the narrowest
   permissions the token screen allows for the research D1 database and R2 bucket. Do not reuse
   the GitHub secret. Revoking this token is the instant kill switch for the box.
7. **Databento.** The box replaces GitHub as the one live consumer; it does not add a second
   one. Connection limits are per team and dataset, so other users of the same key count against
   the same limit. Confirm there is headroom before cutover.

## 2. Bootstrap

```bash
ssh ubuntu@<static-ip>
curl -fsSLo bootstrap.sh https://raw.githubusercontent.com/magis-capital-partners/single-stock-investments/main/dashboard/cloudflare/reverse-split-live/deploy/lightsail/bootstrap.sh
less bootstrap.sh
sudo bash bootstrap.sh
sudoedit /etc/reverse-split-live.env
sudo bash /srv/rs/repo/dashboard/cloudflare/reverse-split-live/deploy/lightsail/soak-report.sh
```

Every line under "prerequisites" must read `ok` and no `BAD` line may appear.

Layout: code in `/srv/rs/repo` (blob-less sparse clone of the public repo, only the collector
folder), Python in `/srv/rs/venv` (`databento==0.82.0`, `PyMuPDF==1.28.0`), Node 24 from the
signed NodeSource repository, service user `research`, secrets in `/etc/reverse-split-live.env`
(root:research 0640).

## 3. Cutover

Do this in the evening (after 20:00 ET) or on a weekend, never during the US session. It takes
about 15 minutes. GitHub keeps running until step 3.

1. **Merge this change.** The new `if:` conditions are inert until the variable exists.
2. **Fence GitHub:**
   ```bash
   gh variable set RS_COLLECTOR_HOST --body lightsail --repo magis-capital-partners/single-stock-investments
   ```
   From now on no new GitHub collector or observer run starts (scheduled or continuation).
3. **Let the running GitHub sessions end.** The cleanest way is to wait: each session ends by
   itself within 270 minutes, checkpoints, releases its lease, and no continuation starts now.
   To go faster, cancel them. GitHub then signals the job and kills it about 10 seconds later.
   The collector may not finish its final checkpoint in that time, so the last one-minute
   checkpoint stands and the lease expires within 10 minutes.
   ```bash
   gh run list --repo magis-capital-partners/single-stock-investments --workflow reverse-split-live.yml --status in_progress
   gh run list --repo magis-capital-partners/single-stock-investments --workflow reverse-split-market-status.yml --status in_progress
   gh run cancel <run-id> --repo magis-capital-partners/single-stock-investments
   ```
   Do not cancel a `deploy` run; only `collect` and `observe`.
4. **Start box R:**
   ```bash
   sudo systemctl enable --now rs-market-status rs-collector
   journalctl -fu rs-collector
   ```
   The collector waits up to 30 minutes for the lease. A lease that was not released cleanly
   expires within 10 minutes, and the box takes it then.
5. **Check within 15 minutes:** the dashboard health shows a fresh heartbeat whose
   `pipeline_commit` is the box's commit (`git -C /srv/rs/repo rev-parse HEAD`);
   `soak-report.sh` shows both services active with no restarts.
6. **Check at the next session (09:30-16:00 ET):** Databento quotes actually arrive for the action
   names after the handover, not only a heartbeat. Check the quote-feed status and per-name quote
   ages on the dashboard. The review watchdog stays green.

## 4. Load test: pass all of these before calling the box done

Record each result, with the date and `soak-report.sh` output, in a dated note next to this file.

| Test | How | Pass |
|---|---|---|
| Memory | Three full sessions on the full current ledger | `soak-report.sh` peak stays under `MemoryHigh` with at least 1 GiB left for the OS. If not: snapshot, create a 16 GB instance from it, repeat. Then set `MemoryHigh`/`MemoryMax` from the measured peak. |
| CPU | Same three sessions | Burst capacity never reaches zero, in particular during checkpoint compression. |
| Process death | After hours: `sudo systemctl kill -s SIGKILL rs-collector` | Restarts in 30 s, restores the latest checkpoint, retakes the lease (at most 10 minutes), no duplicated or lost rows on the dashboard. |
| Death during a checkpoint upload | Same, timed while the journal shows a checkpoint being written | Same as above, and the restored generation's checksums match. |
| Network loss | `sudo iptables -I OUTPUT -m owner --uid-owner research -j REJECT && sudo systemd-run --on-active=300 /usr/sbin/iptables -D OUTPUT -m owner --uid-owner research -j REJECT` (blocks only the service user, removes itself after 5 minutes; SSH is unaffected) | Collector reports degraded sources, then recovers on its own; source gaps are recorded, never filled with invented times. |
| Restore onto a clean machine | Build a second instance with `bootstrap.sh`. **Stop box R first** (`systemctl disable --now rs-collector rs-market-status`), then enable the services on the new instance. | The new instance restores from R2 and resumes; announcement, decision and policy counts match before and after. Keep one instance and delete the other. Never run both. |
| Disk | Daily `df -h /` and the private `/tmp` size in `soak-report.sh` | More than half the disk free after a week. |
| Transfer | Lightsail console, network out, first week | Projected month stays inside the plan's allowance. A full ~142 MB checkpoint every 2 minutes would be ~3 TB a month by itself. |

## 5. Day to day

- **Code updates:** `rs-update.timer` at 20:30 ET. A new commit that does not change the collector
  folder is fast-forwarded without a restart. A commit that does change it is taken only after
  GitHub's "Reverse-split live service" push run for it succeeded (that run executes the test
  suites and applies the D1 migrations). Then the box runs local checks, installs changed unit
  files, restarts, and rolls back if the collector is not stable 3 minutes later.
  `journalctl -u rs-update` shows each night's decision.
- **Logs:** `journalctl -u rs-collector -u rs-market-status --since -1h`.
- **Health:** `sudo bash .../soak-report.sh --since -24h`.

## 6. What pages you

- **GitHub review watchdog** (`reverse-split-review.yml`, 08:17-17:47 ET on weekdays): the run
  fails, and GitHub emails, when its problem list changes: heartbeat older than 3 minutes, a stale
  source, failed analysis jobs. A box that dies overnight is noticed at 08:17.
- **Lightsail alarms** from step 1.5: status check and CPU burst capacity.
- **Not paged yet:** memory or disk pressure inside the box (use `soak-report.sh`), and overnight
  outages (see follow-ups).

## 7. Rollback (box R to GitHub)

```bash
sudo systemctl disable --now rs-collector rs-market-status    # on box R: checkpoints and releases the leases
gh variable delete RS_COLLECTOR_HOST --repo magis-capital-partners/single-stock-investments
gh api --method POST repos/magis-capital-partners/single-stock-investments/dispatches -f event_type=reverse-split-shadow-continue
gh api --method POST repos/magis-capital-partners/single-stock-investments/dispatches -f event_type=reverse-split-status-continue
```

If box R cannot be reached, run only the last three commands. Its leases expire within 10 minutes
and the GitHub jobs take them. Afterwards, check that the heartbeat's `pipeline_commit` belongs to
the GitHub run. Revoke the box's Cloudflare token if the box itself is suspect.

## Follow-ups not in this change

- Automatic GitHub takeover when the box's heartbeat is stale, instead of the manual rollback.
- A watchdog schedule that also covers nights and weekends.
- Reducing collector memory: separating quote intake from PDF and financial work.
- Box S (the SPX nightly's live part) is a separate machine and a separate plan. Nothing here
  touches it.
