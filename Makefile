.PHONY: setup dev backend worker web remote remote-status remote-off test typecheck smoke render-demo searxng-up searxng-down

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
DOCKER ?= $(shell command -v docker 2>/dev/null || { test -x /Applications/Docker.app/Contents/Resources/bin/docker && echo /Applications/Docker.app/Contents/Resources/bin/docker; } || echo docker)
DOCKER_CONTEXT ?=
DOCKER_CONTEXT_ARG = $(if $(DOCKER_CONTEXT),--context $(DOCKER_CONTEXT),)

$(PYTHON):
	python3 -m venv $(VENV)

setup: $(PYTHON)
	$(PYTHON) -m pip install -r requirements.txt
	npm --prefix compositor/remotion_renderer install
	npm --prefix web install

backend:
	$(PYTHON) -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765

worker:
	$(PYTHON) -m pipeline.jobs.worker

web:
	npm --prefix web run dev -- --host 127.0.0.1 --port 5173

searxng-up:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml up -d

searxng-down:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml down

dev:
	$(PYTHON) -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765 & $(PYTHON) -m pipeline.jobs.worker & npm --prefix web run dev -- --host 127.0.0.1 --port 5173

remote:
	./tools/run_remote_studio.sh

remote-status:
	@tailscale serve status 2>/dev/null || tailscale --socket="$$HOME/.synthpost/tailscaled.sock" serve status

remote-off:
	@tailscale serve --https=443 off 2>/dev/null || tailscale --socket="$$HOME/.synthpost/tailscaled.sock" serve --https=443 off

test:
	$(PYTHON) -m unittest discover -s tests

typecheck:
	$(PYTHON) -m py_compile pipeline/models.py pipeline/workflow.py pipeline/db/sqlite.py pipeline/db/repository.py pipeline/discovery/discover.py pipeline/research/extract.py pipeline/llm/providers.py pipeline/scripts/generation.py pipeline/visuals/providers.py pipeline/timeline/templates.py pipeline/timeline/validation.py pipeline/timeline/planner.py pipeline/manifest_builder.py pipeline/api/main.py pipeline/jobs/worker.py pipeline/run_episode.py
	npm --prefix compositor/remotion_renderer run typecheck
	npm --prefix web run typecheck

smoke:
	SYNTHPOST_LLM_PROVIDER=mock $(PYTHON) -m pipeline.run_episode --smoke --render-profile preview

render-demo:
	SYNTHPOST_LLM_PROVIDER=mock $(PYTHON) -m pipeline.run_episode --create-demo --render-profile preview
