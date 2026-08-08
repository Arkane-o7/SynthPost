.PHONY: help setup setup-tts dev backend worker workers web remote remote-status remote-off test test-unit test-avatar typecheck build check doctor config-check smoke smoke-parallel render-demo searxng-up searxng-down clean-dev

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
DOTS_TTS_VENV ?= .venv-dots-tts
DOTS_TTS_PYTHON ?= $(DOTS_TTS_VENV)/bin/python
DOTS_TTS_MODEL_VARIANT ?= int4
DOTS_TTS_MODEL_DIR ?= .cache/dots-tts/$(DOTS_TTS_MODEL_VARIANT)
DOTS_TTS_READY ?= .cache/dots-tts/.$(DOTS_TTS_MODEL_VARIANT).ready
DOCKER ?= $(shell command -v docker 2>/dev/null || { test -x /Applications/Docker.app/Contents/Resources/bin/docker && echo /Applications/Docker.app/Contents/Resources/bin/docker; } || echo docker)
DOCKER_CONTEXT ?=
DOCKER_CONTEXT_ARG = $(if $(DOCKER_CONTEXT),--context $(DOCKER_CONTEXT),)
LANE ?= all
SLOT ?=

help:
	@echo "SynthPost developer commands"
	@echo "  setup          Install Python, Studio, and Remotion dependencies"
	@echo "  setup-tts      Install dots.tts-MLX and download the local SOAR int4 model"
	@echo "  dev            Start API, configured parallel worker pool, and Studio"
	@echo "  workers        Start the configured multi-process worker pool"
	@echo "  test           Run deterministic root Python tests"
	@echo "  test-avatar    Run Avatar Engine unit tests (no render)"
	@echo "  typecheck      Compile Python and type-check both TypeScript apps"
	@echo "  build          Build the Studio production bundle"
	@echo "  doctor         Check required and optional local dependencies"
	@echo "  check          Run config, tests, type checks, and Studio build"
	@echo "  smoke          Run the lightweight TEST_MODE render smoke test"
	@echo "  smoke-parallel Render two TEST_MODE episodes concurrently"

$(PYTHON):
	python3 -m venv $(VENV)

setup: $(PYTHON)
	$(PYTHON) -m pip install -r requirements.txt
	npm --prefix compositor/remotion_renderer install
	npm --prefix web install

$(DOTS_TTS_PYTHON):
	$(PYTHON) -m venv $(DOTS_TTS_VENV)

$(DOTS_TTS_READY): $(DOTS_TTS_PYTHON)
	$(DOTS_TTS_PYTHON) -m pip install "git+https://github.com/sb1992/dots-tts-mlx.git@v0.7.0" "huggingface-hub>=0.34"
	HF_HUB_DISABLE_XET=1 $(DOTS_TTS_VENV)/bin/hf download shraey/dots-tts-mlx --include "$(DOTS_TTS_MODEL_VARIANT)/*" --local-dir .cache/dots-tts
	test -f $(DOTS_TTS_MODEL_DIR)/core.safetensors
	test -f $(DOTS_TTS_MODEL_DIR)/vocoder.safetensors
	touch $(DOTS_TTS_READY)

setup-tts: $(DOTS_TTS_READY)
	@echo "dots.tts ready at $(DOTS_TTS_MODEL_DIR)"

backend:
	$(PYTHON) -m pipeline.api.main

worker:
	$(PYTHON) -m pipeline.jobs.worker --lane $(LANE) $(if $(SLOT),--slot $(SLOT),)

workers:
	$(PYTHON) -m pipeline.jobs.supervisor

web:
	npm --prefix web run dev -- --host 127.0.0.1 --port 5173

searxng-up:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml up -d

searxng-down:
	$(DOCKER) $(DOCKER_CONTEXT_ARG) compose -f docker-compose.searxng.yml down

dev:
	$(PYTHON) -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765 --reload --reload-dir pipeline --timeout-graceful-shutdown 3 & \
	$(PYTHON) -m pipeline.jobs.supervisor & \
	npm --prefix web run dev -- --host 127.0.0.1 --port 5173

remote:
	./tools/run_remote_studio.sh

remote-status:
	@tailscale serve status 2>/dev/null || tailscale --socket="$$HOME/.synthpost/tailscaled.sock" serve status

remote-off:
	@tailscale serve --https=443 off 2>/dev/null || tailscale --socket="$$HOME/.synthpost/tailscaled.sock" serve --https=443 off

test: test-unit

test-unit:
	$(PYTHON) -m unittest discover -s tests

test-avatar:
	PYTHONPATH=avatar-engine $(PYTHON) -m unittest discover -s avatar-engine/tests

typecheck:
	$(PYTHON) -m compileall -q pipeline assembly tools tests
	npm --prefix compositor/remotion_renderer run typecheck
	npm --prefix web run typecheck

build:
	npm --prefix web run build

config-check:
	$(PYTHON) -m tools.doctor --config-only

doctor:
	$(PYTHON) -m tools.doctor

check: config-check test typecheck build

smoke:
	SYNTHPOST_LLM_PROVIDER=mock $(PYTHON) -m pipeline.run_episode --smoke --render-profile preview

smoke-parallel:
	$(PYTHON) -m tools.parallel_smoke --episodes 2 --render-profile preview

render-demo:
	SYNTHPOST_LLM_PROVIDER=mock $(PYTHON) -m pipeline.run_episode --create-demo --render-profile preview

clean-dev:
	find pipeline assembly tests tools -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf web/dist compositor/remotion_renderer/out
