# Research QA pipeline (Marvin + Milly)
# Usage:
#   make research-check TICKER=KEWL DATE=2026-06-01
#   make research-check-all
#   make milly-repass TICKER=QDEL

PYTHON ?= python
SCRIPTS := _system/scripts

TICKER ?=
DATE ?= $(shell date +%Y-%m-%d)

.PHONY: research-check research-check-all evidence milly-repass book-estimate book-estimate-all holdco-uplift short-scan hk-scan hk-cross-check-all hk-extract-refresh third-party-scan-all cross-check-all

research-check:
ifndef TICKER
	$(error Set TICKER= e.g. make research-check TICKER=KEWL DATE=2026-06-01)
endif
	$(PYTHON) $(SCRIPTS)/marvin_cloud_refresh.py $(TICKER) --date $(DATE) --skip-milly --strict-evidence
	@echo OK: $(TICKER) research-check

research-check-all:
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py
	$(PYTHON) $(SCRIPTS)/lint_deep_dive.py --milly
	$(PYTHON) $(SCRIPTS)/lint_adversarial.py
	@echo OK: portfolio research-check-all

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
