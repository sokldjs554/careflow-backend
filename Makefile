.PHONY: sync test lint typecheck verify benchmark live-claude run run-live

sync:
	uv sync --locked --extra dev --extra speech

test:
	uv run pytest -m "not integration"

lint:
	uv run ruff check .

typecheck:
	uv run mypy app

verify: lint typecheck test

benchmark:
	uv run python scripts/benchmark.py

live-claude:
	uv run python scripts/live_claude_check.py

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000

run-live:
	NOTE_GENERATOR_MODE=anthropic SPEECH_RECOGNITION_MODE=faster_whisper uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000
