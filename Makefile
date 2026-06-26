# Health Access Map -- orchestration
# Requires: .venv (python deps), node_modules (mapshaper), frontend/node_modules.
PY = .venv/bin/python
UVICORN = .venv/bin/uvicorn

.PHONY: help setup preflight data data-ca data-national api web build-web clean-nppes acceptance gate amenable subcounty causal prod-check verify-csp trends

help:
	@echo "make setup        - create venv + install python/node deps"
	@echo "make preflight    - environment checks"
	@echo "make data-ca      - build the CA dev vertical slice"
	@echo "make data         - build the full national dataset (~33k ZIPs)"
	@echo "make api          - run FastAPI backend on :8000"
	@echo "make web          - run Vite dev server on :5173"
	@echo "make build-web    - production build of the frontend"
	@echo "make acceptance   - run the acceptance test suite"
	@echo "make gate         - diagnostics + bootstrap-CI gate (95% CIs on every margin)"
	@echo "make amenable     - one-step amenable-mortality re-gate (after a WONDER export)"
	@echo "make subcounty    - consolidated sub-county validity scorecard (5 states + 2 national)"
	@echo "make causal       - causal/actionability frontier: negative-control + temporal event study"
	@echo "make trends       - display-only poverty-rank trend (two ACS vintages) -> trends.json"
	@echo "make prod-check   - predeploy checks on a real data build"
	@echo "make verify-csp   - render the prod build under the nginx CSP; fail on any violation"
	@echo "make clean-nppes  - delete the 10 GB extracted NPPES CSV"

setup:
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip freeze > requirements.lock
	npm install
	cd frontend && npm install

preflight:
	$(PY) -m pipeline.preflight

data-ca:
	$(PY) -m pipeline.run --dev-state CA --force

data data-national:
	$(PY) -m pipeline.run --force

api:
	$(UVICORN) backend.main:app --reload --port 8000

web:
	cd frontend && npm run dev

build-web:
	cd frontend && npm run build

acceptance:
	$(PY) -m pytest tests -v

gate:
	$(PY) -m pipeline.diagnostics
	$(PY) -m pipeline.bootstrap_gate

amenable:
	$(PY) -m pipeline.regate_amenable

subcounty:
	$(PY) -m pipeline.validate_subcounty --all

causal:
	$(PY) -m pipeline.validate_placebo
	$(PY) -m pipeline.validate_temporal

prod-check:
	$(PY) -m pytest tests -q
	cd frontend && npm run typecheck
	cd frontend && npm test
	cd frontend && npm run build
	cd frontend && node scripts/verify-csp.mjs
	$(PY) -m pipeline.verify_bands --require-calibration
	$(PY) -m pipeline.diagnostics
	docker compose config >/dev/null

trends:
	$(PY) -m pipeline.build_trends

verify-csp:
	cd frontend && npm run build && node scripts/verify-csp.mjs

clean-nppes:
	$(PY) -m pipeline.run --cleanup
