# Convenience wrappers. Each target runs inside training/ with the locked uv environment.

UV_RUN = cd training && uv run

.PHONY: all sync test lint format

all: sync
	$(UV_RUN) python -m glyphsketch.pipeline all

sync:
	cd training && uv sync --locked

test:
	$(UV_RUN) pytest

lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	$(UV_RUN) mypy

format:
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .
