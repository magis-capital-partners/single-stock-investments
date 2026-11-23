# RS live shadow on NY4: pinned install, verification and rollback

**Status: a plan for the owner's explicit NY4 authorization. Nothing here runs
without it.** Merging the PRs installs nothing. No NY4 work, Gateway connection,
timer activation or arm file follows from a merge. Each numbered stage below is
its own owner word.

What shadow is: client 60 on the shared NY4 Gateway, with the dedicated shadow
journal (`run --shadow`). It runs every entry gate on the real account and
transmits no order. `ARM.json` does not exist, and shadow refuses to start
while RS holds live names.

## 0. Preconditions (before any NY4 evening)

1. **CI green** on SSI #1823, ls-algo #70 and spx-0dte #681.
2. **Registry merges, one after another, never together.** Before each merge,
   check that the canonical bytes are identical in all three repos:
   * raw file sha256 `b7d2766708eecb89ad6c9a824786227ec62b4c0f363c6f4bcd60d56549e07c3b`;
   * canonical hash `2b8e284e47c5372afd2f2af587b03d1941c263b53c169496f44343205250f268`;
   * version `2026-11-18.1`.

   Check the pins against them in each repo too: SSI `ib_gateway_registry.py`,
   spx-0dte `live/ib_client_registry.py`, and ls-algo `config/ib_client_ids.yml`.
   Order: SSI (canonical) first, then spx-0dte #681, then ls-algo #70. Each merge
   needs the owner's words.

   **Done 2026-11-19.** Bytes and pins were checked identical before each merge:
   * SSI #1823 merged by the repo's agent-branch auto-merge (`a4c8934f`);
   * spx-0dte #681 merged on the owner's word (`8f3ba503`);
   * ls-algo #70 merged on the owner's word (squash `6bee24a5`).
3. **No activation while deployed registries disagree.**
   * spx-0dte's NY4 tree must carry #681 through its normal deploy, outside
     hours, with its own gates and `--approved`. #681 changes pins and docs
     only, and restarts nothing in SPX's strategy.
   * **ls-algo needs no deploy step.** NY4's ls-algo checkout pulls `main`
     itself; its `main` carries NY4's own screener and EOD commits and their
     merge commits. So #70 (claims reader plus registry) goes live at ls-algo's
     next pull after the merge. Confirm on the box that `/home/spx/ls-algo` is at
     or after `6bee24a5`. That is BEFORE the claims
     directory exists, and a missing directory means "no claims" there. The
     hazard moves to the moment step 2 creates the directory; see the note on
     that line.
4. **Owner inputs:**
   * the IBKR account number for `config.json`;
   * an R2 "Object Read only" token scoped to the
     `single-stock-reverse-splits-evidence` bucket. Only its S3 Access Key ID
     and Secret Access Key go on NY4. No Cloudflare administration, no write or
     delete, no Box R secret, no broker credential;
   * one reviewed ticker and conid for the probe.

## 1. Build the release on the laptop (pinned; no GitHub token or deploy key on NY4)

```text
COMMIT=<the approved merged SSI main commit>
git -C <ssi checkout> archive --format=tar --prefix=rs-live-$COMMIT/ $COMMIT _system/__init__.py _system/trading | gzip -n > rs-live-$COMMIT.tar.gz
python -m pip download --dest wheelhouse --only-binary=:all: --platform manylinux2014_x86_64 --python-version 3.12 -r _system/trading/rs_paper_executor/requirements.txt
sha256sum rs-live-$COMMIT.tar.gz wheelhouse/* > rs-live-$COMMIT.sha256
```

Copy the archive, `wheelhouse/` and `rs-live-$COMMIT.sha256` to NY4 with the
existing SSH access. The R2 credential is never in this transfer; the owner
types it into `operations.env` on NY4 with `sudoedit`.

## 2. Install on NY4

A weekday evening after 16:20 ET, as root, with the owner's word. Not between
Sunday 23:05 and Monday 07:10 ET, while the Gateway is closed. Nothing here
touches the Gateway or ThetaData, and no SPX unit is restarted.

**Why the claims directory waits for idle ls-algo.** ls-algo #70 is already
live, because NY4 pulls its `main`. An ls-algo job that started BEFORE
`usermod -aG ib-claims spx` runs without that group. If the 2750 directory
appears while that job runs, the job cannot list it, which is a global failure
for that ls-algo run. So create the directory only while no ls-algo unit is
active. Every later job starts with the group.

```text
sha256sum -c rs-live-$COMMIT.sha256                       # refuse on any mismatch
groupadd --system ib-claims
usermod -aG ib-claims spx                                  # ls-algo runs as spx
useradd --system --home-dir /srv/rs-live --shell /usr/sbin/nologin rs-live
usermod -aG ib-claims rs-live
install -d -o root    -g root     -m 0755 /srv/rs-live /srv/rs-live/releases
systemctl list-units 'ls-algo*' --state=activating,active --no-legend   # MUST print nothing
install -d -o rs-live -g ib-claims -m 2750 /var/lib/ib-account-claims    # only after the check above
install -d -o rs-live -g rs-live  -m 0750 /var/lib/rs-live /var/lib/rs-live/feed
install -d -o root    -g rs-live  -m 0750 /etc/rs-live          # the service cannot arm itself
tar -xzf rs-live-$COMMIT.tar.gz -C /srv/rs-live/releases && mv /srv/rs-live/releases/rs-live-$COMMIT /srv/rs-live/releases/$COMMIT
ln -sfn /srv/rs-live/releases/$COMMIT /srv/rs-live/repo
python3.12 -m venv /srv/rs-live/venv
/srv/rs-live/venv/bin/pip install --no-index --find-links ./wheelhouse -r /srv/rs-live/repo/_system/trading/rs_paper_executor/requirements.txt
setfacl -m u:rs-live:--x /home/spx /home/spx/spx-0dte /home/spx/spx-0dte/data
setfacl -R -m u:rs-live:r-X /home/spx/spx-0dte/data/live
setfacl -R -d -m u:rs-live:r-X /home/spx/spx-0dte/data/live
```

Files:
* `/etc/rs-live/config.json` (`root:rs-live 0640`): `config.live.example.json`
  with the account filled in. Its policy values are the owner's pilot settings
  of 2026-11-19. Do not change them here.
* `/etc/rs-live/operations.env` (`root:root 0600`): `RS_OPERATIONS_S3_ENDPOINT`,
  `RS_OPERATIONS_ACCESS_KEY_ID` and `RS_OPERATIONS_SECRET_ACCESS_KEY`.
* `/var/lib/rs-live/evidence.json` (`rs-live 0640`): from `evidence.example.json`.
* `/etc/rs-live-approved`: install approval, not an arm.
* `rs-live-executor.service`, `rs-live-executor.timer` and
  `rs-live-operations.service` into `/etc/systemd/system/`, then
  `systemctl daemon-reload`. **Do not enable anything.**

`R=/srv/rs-live/venv/bin/python -m _system.trading.rs_paper_executor` below, run
from `/srv/rs-live/repo`.

## 3. Verify (same evening, before anything is enabled)

1. **Paths, as the service user:** `sudo -u rs-live $R preflight --config /etc/rs-live/config.json`.
   It checks that the SPX tree and its newest day are readable, and that the
   claims and publish directories are writable. It exits 2 and names each
   failure. It writes nothing.
2. **SPX's files after atomic replacement.** The default ACL has to reach files
   that spx-0dte REPLACES, not only the ones present now. Prove the mechanism
   with spx-0dte's own writer in a scratch folder, never inside SPX's tree:

   ```text
   install -d -o spx -g spx -m 0750 /home/spx/.rs-acl-check
   setfacl -m u:rs-live:r-x /home/spx/.rs-acl-check; setfacl -d -m u:rs-live:r-X /home/spx/.rs-acl-check
   sudo -u spx bash -c 'cd /home/spx/spx-0dte/live && /home/spx/spx-0dte/.venv/bin/python -c "from pathlib import Path; from heartbeat import _atomic_write_text as w; p=Path(\"/home/spx/.rs-acl-check/x.json\"); w(p, \"1\"); w(p, \"2\")"'
   sudo -u rs-live cat /home/spx/.rs-acl-check/x.json        # must print 2
   getfacl /home/spx/.rs-acl-check/x.json                     # user:rs-live:r-- (effective r)
   rm -r /home/spx/.rs-acl-check
   ```

   That is SPX's own interpreter (`SPX_PYTHON` in `scripts/linux/spx-env.sh`:
   `.venv`, else `python3`). `heartbeat.py` imports only the standard library.
   The next morning, the shadow
   journal confirms the real tree. A refusal reason `SPX book margin directory
   unreadable` in `shadow-report` means the grant failed.
3. **The claims file, readable by spx before ls-algo's next run reads it:**
   ```text
   sudo -u rs-live $R claims-init --config /etc/rs-live/config.json   # writes reverse-split.json (no claims), no socket
   sudo -u spx id -nG | grep -w ib-claims                              # sudo opens a fresh login: current groups
   sudo -u spx ls -l /var/lib/ib-account-claims && sudo -u spx cat /var/lib/ib-account-claims/reverse-split.json
   ```
   Running processes do not acquire the new group. None of SPX's long-running
   units reads the claims, so none is restarted. ls-algo's four units are
   one-shot jobs as `spx` and pick the group up at their next normal start.
4. **ls-algo's reader, once, as spx:** check that `/home/spx/ls-algo` is at or
   after `6bee24a5`, then load its foreign claims as spx. It must report no
   claims and no error. An unreadable claims directory is a global failure
   there, which is why the group comes first and the directory waits for idle
   ls-algo.
5. **Registry agreement on the box:**
   ```text
   sha256sum /srv/rs-live/repo/_system/trading/ib_gateway_client_registry.v1.json /home/spx/spx-0dte/config/ib_gateway_client_registry.v1.json /home/spx/ls-algo/config/ib_gateway_client_registry.v1.json
   ```
   All three must print `b7d27667...`. Stop here if any differs.
6. **Feed, one fetch.** The credential reaches the process only through systemd:
   ```text
   sudo systemd-run --wait --pipe -p User=rs-live -p WorkingDirectory=/srv/rs-live/repo -p EnvironmentFile=/etc/rs-live/operations.env $R operations-fetch --once --config /etc/rs-live/config.json --feed-dir /var/lib/rs-live/feed
   ```
   Exit 0 means a fresh snapshot. Box R publishes less often when idle, so an
   evening exit 3 (older than 120 s) is information, not a failure. A 403
   means the token is wrong.
7. **The only connection of the evening:**
   `sudo -u rs-live $R probe --config /etc/rs-live/config.json --connect-live --symbol <TICKER> --conid <CONID> --report /var/lib/rs-live/probe.json`.
   It opens one session as client 60, makes no journal, runs a 1-share WhatIf
   and transmits nothing. Its quote checks need regular hours.

## 4. Enable (a separate owner word)

`systemctl enable --now rs-live-executor.timer`. The first shadow session starts at
09:05 ET on the next weekday. The fetcher starts with the executor and stops with it.
After each close:

```text
sudo -u rs-live $R shadow-report --config /etc/rs-live/config.json --state /var/lib/rs-live/shadow.sqlite --report /var/lib/rs-live/shadow-$(date +%F).json
sudo -u rs-live $R operations-cadence --config /etc/rs-live/config.json --feed-dir /var/lib/rs-live/feed
```

The stage-P paper report and its journal come from the laptop. Pass them with
`--mechanics-report/--mechanics-journal` when reviewing (any machine works,
read-only).

## 5. Rollback

Nothing below touches SPX's services or the Gateway.

* **Pause.** `systemctl disable --now rs-live-executor.timer && systemctl stop rs-live-executor rs-live-operations`.
  The shadow journal holds no orders or positions. Confirm with
  `$R status --config /etc/rs-live/config.json --state /var/lib/rs-live/shadow.sqlite`;
  it should show 0 unresolved and 0 positions. Nothing at IBKR needs unwinding.
* **Code.** `ln -sfn /srv/rs-live/releases/<previous commit> /srv/rs-live/repo`,
  reinstall the venv if `requirements.txt` changed, and start at the next session.
  Keep the two previous releases.
* **Feed credential.** Delete `/etc/rs-live/operations.env` and revoke the token in
  Cloudflare.
* **Full uninstall, after pausing:**
  1. Archive `/var/lib/rs-live/shadow.sqlite` (it is the evidence).
  2. Remove the three units, `/etc/rs-live`, `/srv/rs-live` and `/var/lib/rs-live`.
  3. Remove the ACL:
     ```text
     setfacl -R -x u:rs-live /home/spx/spx-0dte/data/live
     setfacl -R -d -x u:rs-live /home/spx/spx-0dte/data/live
     setfacl -x u:rs-live /home/spx /home/spx/spx-0dte /home/spx/spx-0dte/data
     ```
  4. Leave `/var/lib/ib-account-claims/reverse-split.json` in place while ls-algo #70
     runs. It holds no claims. A missing directory means "no claims" to ls-algo,
     but an unreadable one is a global failure there.
  5. `userdel rs-live`. Keep the `ib-claims` group until ls-algo stops reading claims.
* **Registry.** Revert only with RS stopped, so client 60 is unused. Revert all
  three repos, one after another, then deploy them in the same order.

## 6. Not in this plan

* No arm file and no pilot.
* No Gateway restart, no SPX restart, no ThetaData.

Before any live arming, all of these are needed:
* ls-algo protection deployed;
* the hub attribution PR;
* watchdog 140;
* off-host monitoring;
* the daily account reconciliation (`account_ownership.py`).

## 7. Evidence producers (#1825; only once #1825 is merged)

Without them, `/var/lib/rs-live/evidence.json` stays the empty example, and
every candidate is refused at the evidence step. They are a separate owner
word from stages 2 to 4.

* **No credential.** They read Box R's snapshot from
  `/var/lib/rs-live/feed/operations.json`, which `rs-live-operations` writes.
* **No socket to the Gateway, no client ID, no ThetaData.**
* **Egress from NY4**, which needs the owner's OK:
  * `www.nasdaqtrader.com:443` and `www.sec.gov:443`;
  * `ftp2.interactivebrokers.com:21`. This is anonymous FTP, so passive-mode
    data ports must be allowed outbound too.

They are part of the same release archive (`_system/trading`), and need no
extra wheels.

Install, the same evening as stage 2 or later, as root:

```text
install -d -o rs-live -g rs-live -m 0750 /var/lib/rs-live/evidence-archive
install -o root -g rs-live -m 0640 /srv/rs-live/repo/_system/trading/rs_evidence/config.example.json /etc/rs-live/producers.json
sudoedit /etc/rs-live/producers.json   # set user_agent (the owner's SEC contact) and terms_mode; nothing else
install -m 0644 /srv/rs-live/repo/_system/trading/rs_evidence/rs-evidence-producers.service /srv/rs-live/repo/_system/trading/rs_evidence/rs-evidence-producers.timer /etc/systemd/system/
systemctl daemon-reload                # do not enable
```

`/var/lib/rs-live/evidence.json` from stage 2 can stay. The producers rewrite
it section by section, each under its own lock.

Verify, before enabling anything. Here
`P=/srv/rs-live/venv/bin/python -m _system.trading.rs_evidence`, run from
`/srv/rs-live/repo`:

```text
sudo -u rs-live $P once --config /etc/rs-live/producers.json --only references,ibkr_file,identity,borrow
sudo -u rs-live $P status --config /etc/rs-live/producers.json
```

* `once` fetches SymDir and SEC once, plus IBKR's file once. The halt, Rule
  201 and eligibility tasks are skipped outside the session.
* `status` prints the row counts, the ages and `entry_gaps`: the exact field
  that blocks each name.
* **Today's expected blockers:**
  * `eligibility.intraday_ssr_clearance_source_absent`, which only an SSR
    source clears;
  * `identity.owner_review_required` until reviews exist.

Enable is a separate owner word: `systemctl enable --now rs-evidence-producers.timer`.
It starts at 09:00 ET, before the executor's 09:05, and ends by
`RuntimeMaxSec`. The unit runs `Nice=15` and `CPUQuota=10%` (rule 8).

Rollback:
* `systemctl disable --now rs-evidence-producers.timer && systemctl stop rs-evidence-producers`.
* The executor then sees the evidence age out and refuses every entry.
* Archive `/var/lib/rs-live/evidence.json`, `evidence-archive/` and
  `reviews.jsonl` before an uninstall. They are the evidence history.
