#!/usr/bin/env bash
# Read-only health and sizing report for box R. Changes nothing.
#   sudo bash soak-report.sh            # now
#   sudo bash soak-report.sh --since "-24h"
# Use it before cutover (prerequisites), during the load test (memory, CPU,
# restarts) and to set MemoryHigh/MemoryMax in the unit files from measurements.
set -uo pipefail
since="-6h"; [ "${1:-}" = "--since" ] && since="${2:--6h}"

hr() { printf '\n== %s\n' "$*"; }
gib() { awk -v b="$1" 'BEGIN{ if (b ~ /^[0-9]+$/) printf "%.2f GiB", b/1073741824; else print b }'; }

hr "prerequisites"
for k in CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID DATABENTO_API_KEY POLYGON_API_KEY IBKR_FLEX_BORROW_TOKEN IBKR_FLEX_BORROW_QUERY_ID; do
  if grep -Eq "^$k=.+" /etc/reverse-split-live.env 2>/dev/null; then echo "ok    $k is set"; else echo "MISS  $k is empty or absent"; fi
done
for k in RS_WARM_DISPATCH_TOKEN GITHUB_REPOSITORY GITHUB_TOKEN GH_TOKEN; do
  grep -Eq "^$k=" /etc/reverse-split-live.env 2>/dev/null && echo "BAD   $k must not be in the env file"
done
echo "node   $(node --version 2>/dev/null || echo missing)"
echo "python $(/srv/rs/venv/bin/python3 -c 'import databento, fitz, sys; print(sys.version.split()[0], "databento", databento.__version__)' 2>/dev/null || echo 'venv incomplete')"
echo "code   $(runuser -u research -- git -C /srv/rs/repo log -1 --format='%h %cI %s' 2>/dev/null)"

hr "services"
for u in rs-collector rs-market-status rs-update.timer; do
  systemctl show "$u" -p ActiveState -p SubState -p NRestarts -p MemoryCurrent -p MemoryPeak -p CPUUsageNSec -p ActiveEnterTimestamp 2>/dev/null |
  awk -F= -v u="$u" '{v[$1]=$2} END{
    printf "%-17s %s/%s restarts=%s since=%s\n", u, v["ActiveState"], v["SubState"], v["NRestarts"], v["ActiveEnterTimestamp"];
    if (v["MemoryCurrent"] ~ /^[0-9]+$/) printf "%-17s memory now %.2f GiB, peak %.2f GiB, cpu %.0f s\n", "", v["MemoryCurrent"]/1073741824, (v["MemoryPeak"] ~ /^[0-9]+$/ ? v["MemoryPeak"]/1073741824 : 0), v["CPUUsageNSec"]/1e9 }'
done
grep -E '^(MemoryHigh|MemoryMax)=' /etc/systemd/system/rs-collector.service | tr '\n' ' '; echo

hr "machine"
free -m | sed -n '1,3p'
df -h / | tail -1
echo "load $(cut -d' ' -f1-3 /proc/loadavg)   (Lightsail CPU is burstable: watch 'Burst capacity' in the console)"
for d in /tmp/systemd-private-*-rs-collector.service-*/tmp; do [ -d "$d" ] && du -sh "$d" 2>/dev/null; done

hr "events since $since"
journalctl -u rs-collector -u rs-market-status --since "$since" --no-pager -o cat 2>/dev/null |
  grep -Eo '"event":"[a-z_]+"|collector_failed|market_status_source_failed|lease[a-z_ ]*lost|Out of memory|oom-kill|prepared_waiting_for_lease' |
  sort | uniq -c | sort -rn | head -20
journalctl -k --since "$since" --no-pager 2>/dev/null | grep -i 'out of memory' | tail -3
journalctl -u rs-update --since "-8d" --no-pager -o cat 2>/dev/null | grep '\[rs-update' | tail -5
