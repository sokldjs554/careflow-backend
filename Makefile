.PHONY: sync test lint typecheck verify benchmark live-claude anthropic-auth judge-live run run-live ai-sync ai-test ai-verify rag-bench multimodal-bench eval-bench training-data sft dpo

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
	LLM_TIMEOUT_SECONDS=60 uv run python scripts/live_claude_check.py

anthropic-auth:
	uv run python scripts/check_anthropic_auth.py

judge-live: anthropic-auth
	uv run python scripts/live_ai_judge.py

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000

run-live:
	NOTE_GENERATOR_MODE=anthropic SPEECH_RECOGNITION_MODE=faster_whisper LLM_TIMEOUT_SECONDS=60 uv run uvicorn app.main:app --host 0.0.0.0 --reload --port 8000

ai-sync:
	uv pip install -r ai/requirements-smoke.txt

ai-test:
	uv run pytest -q ai/tests

rag-bench:
	uv run python -m ai.lab rag

multimodal-bench:
	uv run python -m ai.lab multimodal

eval-bench:
	uv run python -m ai.lab evaluation

training-data:
	uv run python -m ai.posttrain generate --count 120

sft:
	uv run python -m ai.posttrain sft

dpo:
	uv run python -m ai.posttrain dpo

ai-verify: ai-test rag-bench multimodal-bench eval-bench training-data
