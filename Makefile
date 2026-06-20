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

.PHONY: research-check research-check-all depth-check depth-audit evidence milly-repass book-estimate book-estimate-all holdco-uplift short-scan hk-scan hk-cross-check-all hk-extract-refresh third-party-scan-all cross-check-all transcript-sync batch-refresh evidence-check darwin-pit-check darwin-build darwin-pit-audit darwin-sync-external darwin-explore persona-lens persona-insights persona-check sumzero-index

persona-lens:
	$(PYTHON) $(SCRIPTS)/fetch_superinvestor_letters.py --all --build
	$(PYTHON) $(SCRIPTS)/persona_lens.py --all
	$(PYTHON) $(SCRIPTS)/append_persona_memory.py --date $(DATE)
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	@echo OK: persona-lens pipeline

persona-fetch-letters:
	$(PYTHON) $(SCRIPTS)/fetch_superinvestor_letters.py --all --build
	@echo OK: persona-fetch-letters

persona-insights:
	$(PYTHON) $(SCRIPTS)/fetch_terminalvalue_sources.py
	$(PYTHON) $(SCRIPTS)/build_sumzero_index.py
	$(PYTHON) $(SCRIPTS)/build_insights.py
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py
	$(PYTHON) $(SCRIPTS)/validate_dashboard_data.py
	@echo OK: persona-insights

sumzero-index:
	$(PYTHON) $(SCRIPTS)/build_sumzero_index.py
	@echo OK: sumzero-index

persona-check:
	$(PYTHON) $(SCRIPTS)/lint_persona_lens.py --portfolio
	@echo OK: persona-check

darwin-build:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast --account all
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py

darwin-roth:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast --account roth

darwin-taxable:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast --account taxable

darwin-sync-external:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --sync-external

darwin-explore:
	$(PYTHON) $(SCRIPTS)/build_darwin_portfolio.py --fast
	$(PYTHON) $(SCRIPTS)/build_dashboard_data.py

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

depth-check:
ifndef TICKER
	$(error Set TICKER=)
endif
	$(PYTHON) $(SCRIPTS)/lint_deep_dive_depth.py $(TICKER) --strict
	@echo OK: $(TICKER) depth-check

depth-audit:
	$(PYTHON) $(SCRIPTS)/audit_deep_dive_depth.py --portfolio --date $(DATE)
	@echo OK: depth-audit $(DATE)

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
