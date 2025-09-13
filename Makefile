PY_BIN := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)
UV_BIN := $(shell command -v uv 2>/dev/null)

ifeq ($(strip $(PY_BIN)),)
$(error Neither python3 nor python found in PATH)
endif

ifeq ($(strip $(UV_BIN)),)
RUN := $(PY_BIN)
else
RUN := uv run $(PY_BIN)
endif

# Ensure package imports resolve when running tests directly
PYTHONPATH ?= src

.PHONY: tests tests-unit tests-e2e build distribute

tests: tests-unit tests-e2e

tests-unit:
	@echo "Running unit tests (discovery under tests/unit)..."
	PYTHONPATH=$(PYTHONPATH) $(RUN) -m unittest discover -s tests/unit -p 'test_*.py' -v

tests-e2e:
	@echo "Running e2e tests (discovery under tests/e2e)..."
	PYTHONPATH=$(PYTHONPATH) $(RUN) -m unittest discover -s tests/e2e -p 'test_*.py' -v || true

build:
	@if [ -z "$(UV_BIN)" ]; then echo "uv not found; install uv from https://docs.astral.sh/uv/"; exit 1; fi
	$(UV_BIN) sync --extra dev
	$(UV_BIN) build

distribute:
	@if [ -z "$(UV_BIN)" ]; then echo "uv not found; install uv from https://docs.astral.sh/uv/"; exit 1; fi
	$(UV_BIN) run -m twine check dist/*
	$(UV_BIN) run -m twine upload dist/*
