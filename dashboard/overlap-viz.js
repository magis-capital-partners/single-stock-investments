/* Holder overlap. One line on a concentrated name, one sentence on Michael's book. */
(function () {
  const MIN_HOLDERS = 10;
  let universe = null;
  let universePromise = null;

  function ensureUniverse() {
    if (universe) return Promise.resolve(universe);
    if (!universePromise) {
      universePromise = fetch("/api/v1/research/overlap?scope=universe", { credentials: "same-origin" })
        .then((response) => (response.ok ? response.json() : null))
        .then((payload) => {
          universe = payload;
          return payload;
        })
        .catch(() => null);
    }
    return universePromise;
  }

  function concentrated(row) {
    return Boolean(row)
      && !row.omitted
      && row.hub_name
      && row.holder_count >= MIN_HOLDERS
      && row.top_share != null
      && row.top_share >= 0.25
      && row.top_holder;
  }

  function renderTicker(ticker, escapeHtml) {
    const safe = escapeHtml(ticker);
    return `<p id="overlap-ticker" class="overlap-name-line" data-ticker="${safe}" hidden></p>`;
  }

  function fillTicker(ticker) {
    const slot = document.getElementById("overlap-ticker");
    if (!slot || slot.dataset.ticker !== ticker) return;
    if (!universe) {
      ensureUniverse().then(() => {
        if (document.getElementById("overlap-ticker")?.dataset.ticker === ticker) fillTicker(ticker);
      });
      return;
    }
    const row = (universe.rows || []).find((item) => item.ticker === ticker);
    if (!concentrated(row)) {
      slot.hidden = true;
      slot.textContent = "";
      return;
    }
    slot.hidden = false;
    slot.textContent = `${row.top_holder} holds ${(row.top_share * 100).toFixed(1)}% of the reported value. ${row.holder_count} holders on file.`;
  }

  function bookLine(payload) {
    const stress = payload && payload.stress;
    const hub = stress && stress.hub_holder;
    if (!hub || hub.overlap_share == null) return "";
    const share = (value) => `${(Number(value) * 100).toFixed(1)}%`;
    let text = `Names also reported by ${hub.name} are ${share(hub.overlap_share)} of this book.`;
    const other = stress.random_holder;
    if (other && other.overlap_share != null) {
      text += ` ${other.name} reports ${share(other.overlap_share)}.`;
    }
    return `${text} This is how much of this book sits in names that holder also reports. It is not a loss.`;
  }

  window.OverlapViz = { renderTicker, fillTicker, bookLine };
})();
