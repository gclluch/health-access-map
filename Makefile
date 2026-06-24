# Health Access Map -- orchestration
# Requires: .venv (python deps), node_modules (mapshaper), frontend/node_modules.
PY = .venv/bin/python
UVICORN = .venv/bin/uvicorn

.PHONY: help setup preflight data data-ca data-national api web build-web clean-nppes acceptance gate amenable

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
	cp data/processed/zcta.geojson frontend/public/zcta.geojson

data data-national:
	$(PY) -m pipeline.run --force
	cp data/processed/zcta.geojson frontend/public/zcta.geojson

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

clean-nppes:
	$(PY) -m pipeline.run --cleanup
