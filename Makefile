.PHONY: setup index report check state

PY := .venv/bin/python3

setup: ## Create venv + install tooling deps (PyYAML)
	python3 -m venv .venv
	.venv/bin/pip install --quiet pyyaml

index: ## Rebuild the derived index from the vault
	$(PY) tools/indexer.py

report: ## Rebuild index + print open questions, contradiction candidates, unbound claims
	$(PY) tools/indexer.py --report

check: index ## Alias: schema conformance check = the indexer parses everything cleanly

state: index ## Derive deal state by replaying events (usage: make state DEAL=aurora)
	$(PY) tools/engine.py $(DEAL) --write

ui: index ## Generate the deal dashboard (usage: make ui DEAL=aurora)
	$(PY) tools/ui.py $(DEAL)
