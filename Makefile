.PHONY: setup index report check state watch dev verify dynamics-test

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

ui: index ## Generate the static deal dashboard export (usage: make ui DEAL=aurora)
	$(PY) tools/ui.py $(DEAL)

app: index ## Run the live app (http://127.0.0.1:4191)
	.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 4191

watch: ## Watch vault/inbox/ and auto-trigger pipeline on new artifacts
	$(PY) tools/watcher.py

dev: index ## Run app + inbox watcher together (two panes via tmux, or run separately)
	@echo "Starting app on :4191  — open a second terminal and run: make watch"
	.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 4191

agents: index ## Deploy the agent runtime (watches vault, acts under contracts)
	$(PY) agents/runtime.py

contracts: ## Show what the machine contracts load
	$(PY) tools/contracts.py

extract: ## Extract unextracted inbox files for all deals (or --deal DEAL --file FILE)
	$(PY) tools/extract.py $(ARGS)

derive: ## Aggregation pass: derive ultimate-parent concentrations from any customer schedule in inbox
	$(PY) tools/derive_concentrations.py $(ARGS)

grade-keystone: ## Run the Keystone Layer-1 + Layer-2 arc grader (answer key never ingested)
	$(PY) tools/grade_keystone.py

grade-keystone-arc: ## Run arc tests only (Layer-2 event chronology)
	$(PY) tools/grade_keystone.py --arc

bind-keystone: ## Retroactively bind Layer-1 keystone claims to questions via subject-to-QID map
	$(PY) tools/bind_keystone_claims.py

verify: ## Run the full test suite: regression + V7 acceptance + e2e + cascade + grounding
	@$(PY) tools/verify_all.py $(ARGS)

dynamics-test: ## Run the embedded state-transition runtime and backend integration suite
	@cd backend/dynamics && python3 -m unittest discover -s tests -v

grounding: ## Grounding gate over extracted claims (usage: make grounding DEAL=keystone)
	$(PY) tools/grounding_gate.py --claims pipeline_out/e3/K-IC/e3_claims.json \
		--deal $(or $(DEAL),keystone) --out pipeline_out/e3/K-IC/grounding_review.json
