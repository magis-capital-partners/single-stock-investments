#!/usr/bin/env bash
# One-time setup of box R: a fresh Lightsail Ubuntu 24.04 instance that runs
# only the reverse-split research collector and the market-status observer.
#
# Run as root on the new box:
#   curl -fsSLo bootstrap.sh https://raw.githubusercontent.com/magis-capital-partners/single-stock-investments/main/dashboard/cloudflare/reverse-split-live/deploy/lightsail/bootstrap.sh
#   less bootstrap.sh            # read it first
#   sudo bash bootstrap.sh
#
# Safe to re-run. It installs and enables the nightly update timer, but it
# does NOT start or enable the collector services: that is the cutover step in
# README.md, done by hand once the secrets file is filled in.
set -euo pipefail

OWNER_REPO=magis-capital-partners/single-stock-investments
ROOT=/srv/rs
REPO="$ROOT/repo"
LIVE_REL=dashboard/cloudflare/reverse-split-live
DEPLOY="$REPO/$LIVE_REL/deploy/lightsail"
NODE_MAJOR=24

say() { echo "[bootstrap] $*"; }
die() { echo "[bootstrap] REFUSING: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = "24.04" ] || die "expected Ubuntu 24.04, found ${PRETTY_NAME:-unknown}"

# This box must never be a trading host. Stop if anything of NY4's is here:
# the IB Gateway / IBC, a ThetaTerminal, or the spx-0dte / ls-algo units.
if systemctl list-unit-files --no-legend 2>/dev/null | grep -Eiq '(^| )(spx-|ibc|ibgateway|theta|ls-algo|portfolio-hub)'; then
  die "trading units found on this machine; box R must be a separate instance"
fi
for port in 4001 4002 25503 25510; do
  if ss -ltnH "( sport = :$port )" 2>/dev/null | grep -q .; then
    die "something listens on port $port (Gateway/ThetaData); box R must be a separate instance"
  fi
done
[ -d /opt/ibc ] && die "/opt/ibc exists; box R must be a separate instance"

say "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git ca-certificates curl gnupg python3-venv tesseract-ocr-eng unattended-upgrades fail2ban

# SSH stays open to the internet by the owner's choice (they travel), so the
# box is hardened instead: keys only, no root login, fail2ban on sshd, and
# automatic security updates. The drop-in is validated before sshd reloads,
# so a bad file cannot lock anyone out.
say "SSH hardening: key-only, no root login, fail2ban, unattended security upgrades"
cat > /etc/ssh/sshd_config.d/10-rs-hardening.conf <<'SSHD'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
MaxAuthTries 4
SSHD
install -d -m 0755 /run/sshd   # sshd -t needs it; absent while 24.04's socket-activated ssh is idle
if sshd -t; then
  systemctl try-reload-or-restart ssh.service || true   # new connections read the drop-in either way
else
  rm -f /etc/ssh/sshd_config.d/10-rs-hardening.conf; die "sshd rejected the hardening drop-in; removed it"
fi
printf '[sshd]\nenabled = true\nmaxretry = 5\nbantime = 1h\nfindtime = 10m\n' > /etc/fail2ban/jail.d/rs-sshd.local
systemctl enable --now fail2ban && systemctl restart fail2ban
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/20auto-upgrades

if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt "$NODE_MAJOR" ]; then
  say "Node.js $NODE_MAJOR from the signed NodeSource apt repository"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq
  apt-get install -y -qq nodejs
fi
node -e 'require("node:sqlite")' 2>/dev/null || die "this Node.js has no node:sqlite; the checkpoint needs it"
say "node $(node --version)"

if ! swapon --noheadings | grep -q .; then
  say "2 GB swap file (headroom for the OS, not for the collector)"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "persistent, capped journal"
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=2G\n' > /etc/systemd/journald.conf.d/rs.conf
systemctl restart systemd-journald

say "service user"
id research >/dev/null 2>&1 || useradd --system --home-dir "$ROOT" --create-home --shell /usr/sbin/nologin research
install -d -o research -g research -m 0755 "$ROOT"

if [ ! -d "$REPO/.git" ]; then
  say "blob-less sparse clone of $OWNER_REPO (public; no GitHub credential on this box)"
  runuser -u research -- git clone --quiet --filter=blob:none --sparse --branch main "https://github.com/$OWNER_REPO.git" "$REPO"
  runuser -u research -- git -C "$REPO" sparse-checkout set --cone "$LIVE_REL"
fi
[ -x "$DEPLOY/run.sh" ] || die "$DEPLOY/run.sh missing or not executable in the checkout"
say "code at $(runuser -u research -- git -C "$REPO" rev-parse --short HEAD)"

say "Python venv with the pinned collector packages"
[ -x "$ROOT/venv/bin/python3" ] || runuser -u research -- python3 -m venv "$ROOT/venv"
runuser -u research -- "$ROOT/venv/bin/pip" install --quiet --upgrade pip
runuser -u research -- "$ROOT/venv/bin/pip" install --quiet databento==0.82.0 PyMuPDF==1.28.0 requests

tess=$(dpkg -L tesseract-ocr-eng | grep '/eng\.traineddata$' | head -1)
[ -f "$tess" ] || die "tesseract English data not found"
printf 'TESSDATA_PREFIX=%s\n' "$(dirname "$tess")" > /etc/reverse-split-live.runtime.env
chmod 0644 /etc/reverse-split-live.runtime.env

# systemd reads EnvironmentFile= as root before it drops to `research`, so the
# secrets file can be root-only: the service user cannot read it from a shell.
if [ ! -f /etc/reverse-split-live.env ]; then
  install -o root -g root -m 0600 "$DEPLOY/reverse-split-live.env.example" /etc/reverse-split-live.env
  say "created /etc/reverse-split-live.env from the template: fill it in before starting anything"
fi
chown root:root /etc/reverse-split-live.env && chmod 0600 /etc/reverse-split-live.env

say "systemd units"
for u in rs-collector.service rs-market-status.service rs-update.service rs-update.timer; do
  install -m 0644 "$DEPLOY/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now rs-update.timer

cat <<'NEXT'
[bootstrap] done. The collector services are installed but NOT enabled or started.
Next (README.md, "Cutover"):
  1. sudoedit /etc/reverse-split-live.env      # fill in the keys
  2. bash /srv/rs/repo/dashboard/cloudflare/reverse-split-live/deploy/lightsail/soak-report.sh
  3. Fence GitHub, then: systemctl enable --now rs-market-status rs-collector
NEXT
