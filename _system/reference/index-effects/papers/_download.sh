#!/usr/bin/env bash
# Download index inclusion/exclusion ("index effect") research papers.
# Each row: "output_filename|url". Validates that the result is a real PDF.
set -u
UA="Mozilla/5.0 (compatible; MarvinResearch/1.0; academic use)"
LOG="_download_log.txt"
: > "$LOG"

fetch () {
  local out="$1" url="$2"
  echo ">>> $out" | tee -a "$LOG"
  curl -sS -L --max-time 120 -A "$UA" -o "$out" "$url" 2>>"$LOG"
  if file "$out" | grep -qi 'PDF document'; then
    local sz; sz=$(stat -c %s "$out")
    echo "    OK  $sz bytes  <- $url" | tee -a "$LOG"
  else
    echo "    FAIL (not a PDF) <- $url" | tee -a "$LOG"
    head -c 200 "$out" | tr -d '\0' >> "$LOG"; echo "" >> "$LOG"
    rm -f "$out"
  fi
}

# --- Academic papers (open-access / author copies) ---
fetch "shleifer_1986_do_demand_curves_slope_down.pdf"                     "https://scholar.harvard.edu/files/shleifer/files/demand_curves.pdf"
fetch "wurgler_zhuravskaya_2002_does_arbitrage_flatten_demand_curves.pdf" "https://pages.stern.nyu.edu/~jwurgler/papers/arbitrage.pdf"
fetch "barberis_shleifer_wurgler_2005_comovement.pdf"                     "https://pages.stern.nyu.edu/~jwurgler/papers/comovement.pdf"
fetch "petajisto_2011_index_premium_hidden_cost.pdf"                      "https://www.petajisto.net/papers/petajisto%202011%20jef%20-%20index%20premium.pdf"
fetch "chang_hong_liskovich_2015_regression_discontinuity_indexing_nber_w19290.pdf" "https://www.nber.org/system/files/working_papers/w19290/w19290.pdf"
fetch "bennett_stulz_wang_2020_joining_sp500_nber_w27593.pdf"            "https://www.nber.org/system/files/working_papers/w27593/w27593.pdf"

echo "=== SUMMARY ===" | tee -a "$LOG"
ls -la *.pdf | tee -a "$LOG"
