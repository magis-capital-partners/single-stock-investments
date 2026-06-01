# Research QA pipeline (Marvin + Milly)
# Usage:
#   make research-check TICKER=QDEL
#   make research-check-all
#   make milly-repass TICKER=QDEL

PYTHON ?= python
SCRIPTS := _system/scripts

TICKER ?=

.PHONY: research-check research-check-all evidence milly-repass short-scan hk-scan hk-cross-check-all third-party-scan-all cross-check-all

research-check:
ifndef TICKER
	$(error Set TICKER= e.g. make research-check TICKER=QDEL)
endif
	$(PYTHON) $(SCRIPTS)/build_filing_evidence.py $(TICKER)
	$(PYTHON) $(SCRIPTS)/lint_deep_dive.py $(TICKER) --milly
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

third-party-scan-all:
	$(PYTHON) $(SCRIPTS)/scan_third_party_sources.py --all --with-hk --date $(or $(DATE),$(shell date +%Y-%m-%d))
	@echo OK: third-party-scan-all

cross-check-all:
	$(PYTHON) $(SCRIPTS)/check_cross_checks.py $(if $(STRICT),--strict,)
	@echo OK: cross-check-all
