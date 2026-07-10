.PHONY: setup index report check

PY := .venv/bin/python3

setup: ## Create venv + install tooling deps (PyYAML)
	python3 -m venv .venv
	.venv/bin/pip install --quiet pyyaml

index: ## Rebuild the derived index from the vault
	$(PY) tools/indexer.py

report: ## Rebuild index + print open questions, contradiction candidates, unbound claims
	$(PY) tools/indexer.py --report

check: index ## Alias: schema conformance check = the indexer parses everything cleanly
