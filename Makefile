.PHONY: setup dev backend worker web test typecheck smoke render-demo searxng-up searxng-down

DOCKER ?= $(shell command -v docker 2>/dev/null || { test -x /Applications/Docker.app/Contents/Resources/bin/docker && echo /Applications/Docker.app/Contents/Resources/bin/docker; } || echo docker)
DOCKER_CONTEXT ?=
DOCKER_CONTEXT_ARG = $(if $(DOCKER_CONTEXT),--context $(DOCKER_CONTEXT),)

setup:
	python3 -m pip install -r requirements.txt
	npm --prefix compositor/remotion_renderer install
	npm --prefix web install

backend:
	python3 -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765

worker:
	python3 -m pipeline.jobs.worker

web:
	npm --prefix web run dev -- --host 127.0.0.1 --port 5173

searxng-up:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml up -d

searxng-down:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml down

dev:
	python3 -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765 & python3 -m pipeline.jobs.worker & npm --prefix web run dev -- --host 127.0.0.1 --port 5173

test:
	python3 -m unittest discover -s tests

typecheck:
	python3 -m py_compile pipeline/models.py pipeline/workflow.py pipeline/db/sqlite.py pipeline/db/repository.py pipeline/discovery/discover.py pipeline/research/extract.py pipeline/llm/providers.py pipeline/scripts/generation.py pipeline/visuals/providers.py pipeline/timeline/templates.py pipeline/timeline/validation.py pipeline/timeline/planner.py pipeline/manifest_builder.py pipeline/api/main.py pipeline/jobs/worker.py pipeline/run_episode.py
	npm --prefix compositor/remotion_renderer run typecheck
	npm --prefix web run typecheck

smoke:
	SYNTHPOST_LLM_PROVIDER=mock python3 -m pipeline.run_episode --smoke --render-profile preview

render-demo:
	SYNTHPOST_LLM_PROVIDER=mock python3 -m pipeline.run_episode --create-demo --render-profile preview
