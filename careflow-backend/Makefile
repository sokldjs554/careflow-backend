.PHONY: install test lint typecheck benchmark run

install:
	python -m pip install -e ".[dev,speech]"

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy app

benchmark:
	python scripts/benchmark.py

run:
	uvicorn app.main:app --reload --port 8000
