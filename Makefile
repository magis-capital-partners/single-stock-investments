# Research QA pipeline (Marvin + Milly)
# Usage:
#   make research-check TICKER=KEWL DATE=2026-06-01
#   make research-check-all
#   make milly-repass TICKER=QDEL
#   make batch-refresh DATE=2026-06-02

PYTHON ?= python3
SCRIPTS := _system/scripts
DATE ?= $(shell date +%Y-%m-%d)

TICKER ?=
DATE ?= $(shell date +%Y-%m-%d)

.PHONY: research-check research-check-all evidence milly-repass book-estimate book-estimate-all holdco-uplift short-scan hk-scan hk-cross-check-all hk-extract-refresh third-party-scan-all cross-check-all transcript-sync batch-refresh evidence-check darwin-pit-check darwin-build darwin-pit-audit

darwin-build:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast

darwin-pit-audit:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --pit-audit --fast

darwin-pit-check:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast
	$(PYTHON) $(SCRIPTS)/check_darwin_pit.py

research-check:
ifndef TICKER
	$(error Set TICKER= e.g. make research-check TICKER=KEWL DATE=2026-06-01)
endif
	$(PYTHON) $(SCRIPTS)/marvin_cloud_refresh.py $(TICKER) --date $(DATE) --skip-milly --strict-evidence
	@echo OK: $(TICKER) research-check

research-check-all:
	$(PYTHON) $(SCRIPTS)/batch_portfolio_refresh.py --date $(DATE) --strict-evidence
	$(PYTHON) $(SCRIPTS)/lint_adversarial.py
	@echo OK: portfolio research-check-all

batch-refresh:
	$(PYTHON) $(SCRIPTS)/batch_portfolio_refresh.py --date $(DATE) --strict-evidence
	@echo OK: batch-refresh $(DATE)

evidence-check:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/check_evidence_completeness.py $(TICKER)
	@echo OK: $(TICKER) evidence-check

evidence:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py $(TICKER)

milly-repass:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/milly_repass.py $(TICKER)

book-estimate:
ifndef TICKER
	$(error Set TICKER= e.g. make book-estimate TICKER=FRMO)
endif
	$(PYTHON) $(SCRIPTS)/current_book_estimate.py $(TICKER) --write
	@echo OK: $(TICKER) book-estimate

book-estimate-all:
	$(PYTHON) $(SCRIPTS)/current_book_estimate.py --all --write
	@echo OK: book-estimate-all

holdco-uplift:
ifndef TICKER
	$(error Set TICKER= e.g. make holdco-uplift TICKER=FRMO)
endif
	$(PYTHON) $(SCRIPTS)/holdco_uplift_build.py $(TICKER) --write
	@echo OK: $(TICKER) holdco-uplift

short-scan:
	$(PYTHON) $(SCRIPTS)/short_scan_batch.py

hk-scan:
ifndef TICKER
	$(error Set TICKER= e.g. make hk-scan TICKER=TPL)
endif
	$(PYTHON) $(SCRIPTS)/scan_hk_sources.py $(TICKER) --write-references --strict
	$(PYTHON) $(SCRIPTS)/check_hk_cross_checks.py $(TICKER)
	@echo OK: $(TICKER) hk-scan

hk-cross-check-all:
	$(PYTHON) $(SCRIPTS)/check_hk_cross_checks.py
	@echo OK: hk-cross-check-all

hk-extract-refresh:
	$(PYTHON) $(SCRIPTS)/refresh_hk_extracts.py
	@echo OK: hk-extract-refresh

third-party-scan-all:
	$(PYTHON) $(SCRIPTS)/scan_third_party_sources.py --all --with-hk --date $(or $(DATE),$(shell date +%Y-%m-%d))
	@echo OK: third-party-scan-all

cross-check-all:
	$(PYTHON) $(SCRIPTS)/check_cross_checks.py $(if $(STRICT),--strict,)
	@echo OK: cross-check-all

transcript-sync:
	$(PYTHON) $(SCRIPTS)/download_transcripts.py --register-legacy $(if $(TICKER),$(TICKER),)
	$(PYTHON) $(SCRIPTS)/transcript_gap_report.py
	@echo OK: transcript-sync
