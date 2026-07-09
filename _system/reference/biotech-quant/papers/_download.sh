#!/usr/bin/env bash
# Download biotech quant research PDFs into papers/.
set -u
UA="Mozilla/5.0 (compatible; MarvinResearch/1.0; academic use)"
LOG="_download_log.txt"
: > "$LOG"

fetch () {
  local out="$1" url="$2"
  echo ">>> $out" | tee -a "$LOG"
  curl -sS -L --max-time 120 -A "$UA" -o "$out" "$url" 2>>"$LOG"
  if file "$out" 2>/dev/null | grep -qi 'PDF document'; then
    local sz; sz=$(wc -c < "$out" | tr -d ' ')
    echo "    OK  $sz bytes  <- $url" | tee -a "$LOG"
  else
    # Windows/Git Bash may lack file(1); check %PDF magic
    if head -c 5 "$out" 2>/dev/null | grep -q '%PDF'; then
      local sz; sz=$(wc -c < "$out" | tr -d ' ')
      echo "    OK  $sz bytes  <- $url" | tee -a "$LOG"
    else
      echo "    FAIL (not a PDF) <- $url" | tee -a "$LOG"
      rm -f "$out"
    fi
  fi
}

# Verdad Capital white paper (Mailchimp CDN link from verdadcap.com/archive/biotech-investing)
fetch "verdad_biotech_investing_2026.pdf" \
  "https://mcusercontent.com/6dc62f307511d466ff78a94fe/files/2d4df1a6-ecf8-7535-cf83-1bd259ea8328/Verdad_WhitePaper_R5.pdf"

echo "=== SUMMARY ===" | tee -a "$LOG"
ls -la *.pdf 2>/dev/null | tee -a "$LOG" || true
