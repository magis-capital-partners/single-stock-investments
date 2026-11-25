# Box R: the reverse-split collector on Lightsail

Box R is one Lightsail instance that does exactly two things, all day, every day:

| Service | What it does | Replaces |
|---|---|---|
| `rs-collector` | `collector.mjs --watch`: SEC and press-release feeds, Databento quotes, IBKR borrow file, simulated entries and exits, checkpoints | the `collect` job of `reverse-split-live.yml` and the warm successor `prepare-and-observe` in `reverse-split-shadow-warm.yml` (270-minute GitHub sessions) |
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

1. **Instance.** Lightsail, region us-east-1, Linux, **Ubuntu 24.04 LTS**, the **16 GB / 4 vCPU /
   320 GB** plan ($84/month). The production box is `magis-collector-3` (us-east-1a), restored on
   2026-11-17 from a snapshot of the 8 GB `magis-collector-2`. The 8 GB plan did not fit: the
   collector peaks at 6.6 GiB and was CPU-bound on 2 vCPUs. `bootstrap.sh` refuses other Ubuntu
   releases: 24.04 matches the GitHub runner the collector is tested on (Python 3.12).
2. **Static IP.** `magis-collector-ip`, 100.51.253.151, attached to the instance. Keep it
   attached: Lightsail charges for a static IP that is not attached to a running instance.
3. **Firewall** (instance > Networking). Only SSH (22). It is open to all addresses because the
   owner travels; `bootstrap.sh` compensates with key-only SSH, no root login, fail2ban and
   unattended security upgrades. Nothing else inbound: both services only make outgoing calls.
   Use a key pair made for this box rather than the region's default key, and keep the `.pem`
   out of every repository and chat.
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
(root:root 0600; systemd reads it as root, so the service user cannot read it from a shell).

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
| Memory | Three full sessions on the full current ledger | `soak-report.sh` peak stays under `MemoryHigh` with at least 1 GiB left for the OS. (The 8 GB box failed this on 2026-11-17; the 16 GB box peaked at 6.6 GiB.) |
| CPU | Same three sessions | Burst capacity never reaches zero, in particular during checkpoint compression. |
| Process death | After hours: `sudo systemctl kill -s SIGKILL rs-collector` | Restarts in 30 s, restores the latest checkpoint, retakes the lease (at most 10 minutes), no duplicated or lost rows on the dashboard. |
| Death during a checkpoint upload | Same, timed while the journal shows a checkpoint being written | Same as above, and the restored generation's checksums match. |
| Network loss | `sudo iptables -I OUTPUT -m owner --uid-owner research -j REJECT && sudo systemd-run --on-active=300 /usr/sbin/iptables -D OUTPUT -m owner --uid-owner research -j REJECT` (blocks only the service user, removes itself after 5 minutes; SSH is unaffected) | Collector reports degraded sources, then recovers on its own; source gaps are recorded, never filled with invented times. |
| Restore onto a clean machine | Build a second instance with `bootstrap.sh`. **Stop box R first** (`systemctl disable --now rs-collector rs-market-status`), then enable the services on the new instance. | The new instance restores from R2 and resumes; announcement, decision and policy counts match before and after. Keep one instance and delete the other. Never run both. |
| Disk | Daily `df -h /` and the private `/tmp` size in `soak-report.sh` | More than half the disk free after a week. |
| Transfer | Lightsail console, network out, first week | Projected month stays inside the plan's allowance. A full ~142 MB checkpoint every 2 minutes would be ~3 TB a month by itself. |

When the checkpoint PUT response times out, the collector checks R2 metadata
for the original unique key for up to 10.5 seconds. It commits only after an
exact key, size and ETag match and the usual lease-checked pointer update.
`upload_confirmation: storage_metadata` marks this path in the publisher audit.
`upload_timeout_at` records the client timeout and `upload_completed_at` records
when the client confirmed the object. An unverifiable write leaves the prior
checkpoint in place. The operations report still has its own state-age guard.

With the continuous refresher enabled, a second worker prepares the first
operations report from the exact captured bytes while the checkpoint is
compressed and uploaded.
It cannot publish anything itself. The refresher only uses the result once
its generation has committed, then applies the usual age and receipt checks.
The publication audit identifies this path as `render_mode: prepared_during_upload`.

The checkpoint reader supports a full gzip image or a full image with one
changed-block overlay. It validates both objects and the SHA-256 of the entire
reconstructed SQLite file. The collector retains every full image needed by
either of its two retained generations. The writer starts with a full image,
then uses an overlay only when its gzip payload is under 60% of a new full
image. A collector without `RS_CHECKPOINT_DELTA=1` still writes full images.
Deploy and verify the compatible reader before enabling overlay writes. To
roll back across the introduction of overlay support, first stop writing
overlays on a compatible revision and verify a new full checkpoint has committed.

## 5. Day to day

- **Code updates:** `rs-update.timer` at 20:30 ET. A new commit that does not change the collector
  folder is fast-forwarded without a restart. A commit that does change it is taken only after
  GitHub's "Reverse-split live service" push run for it succeeded (that run executes the test
  suites and applies the D1 migrations). Then the box runs local checks, installs changed unit
  files, restarts, and rolls back if the collector is not stable 3 minutes later.
  `journalctl -u rs-update` shows each night's decision.
- **Logs:** `journalctl -u rs-collector -u rs-market-status --since -1h`.
- **Health:** `sudo bash .../soak-report.sh --since -24h`. It prints the memory limits in effect
  (drop-ins included) and the Node heap flag the running collector actually got.
- **Restarts after a crash** retake the box's own lease at once: the collector records its lease
  owner id in `/var/lib/rs-collector/owner`, and the next process may take over exactly that
  lease. Any other owner's lease (GitHub after a rollback) is never displaced.
- **No local overrides.** The heap flag (`run.sh`), the memory limits (unit file) and SQLite's
  `synchronous=OFF` (`checkpoint.mjs`) live in the repo. Do not add drop-ins under
  `/etc/systemd/system/rs-collector.service.d/`; `soak-report.sh` lists any that exist.

### Removing the 2026-11-17 hand overrides (once this change is on the box)

The nightly update installs the new unit file and restarts the collector. The next morning,
check `journalctl -u rs-update` says it is running the new commit, then:

```bash
sudo rm /etc/systemd/system/rs-collector.service.d/20-heap.conf /etc/systemd/system/rs-collector.service.d/10-no-fsync.conf
sudo rmdir /etc/systemd/system/rs-collector.service.d
sudo systemctl daemon-reload && sudo systemctl restart rs-collector
sudo bash /srv/rs/repo/dashboard/cloudflare/reverse-split-live/deploy/lightsail/soak-report.sh
```

The report should show `MemoryHigh=12.0G MemoryMax=13.2G`, no drop-ins, and the
`--max-old-space-size=4096` heap flag. Do this outside 09:00-16:30 ET.

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
