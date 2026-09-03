import json
import statistics
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.note_generator import DeterministicDemoGenerator
from app.services.transcript_store import InMemoryTranscriptStore


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * p))
    return ordered[index]


def main(iterations: int = 300) -> None:
    app = create_app(
        settings=Settings(
            environment="benchmark",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url=None,
            transcript_ttl_seconds=300,
        ),
        transcript_store=InMemoryTranscriptStore(),
        note_generator=DeterministicDemoGenerator(),
    )
    create_ms: list[float] = []
    chunk_ms: list[float] = []
    finalize_ms: list[float] = []
    failures = 0
    with TestClient(app) as client:
        for index in range(iterations):
            started = time.perf_counter()
            created = client.post(
                "/v1/sessions",
                json={"language": "ko"},
                headers={"Idempotency-Key": f"benchmark-{index}"},
            )
            create_ms.append((time.perf_counter() - started) * 1000)
            if created.status_code != 201:
                failures += 1
                continue
            session_id = created.json()["session_id"]
            chunks = [
                {"sequence": 1, "speaker": "patient", "text": "최근 잠들기 어렵습니다."},
                {"sequence": 2, "speaker": "clinician", "text": "말투가 차분함을 관찰했습니다."},
                {"sequence": 3, "speaker": "clinician", "text": "다음 주 추적할 계획입니다."},
            ]
            for chunk in chunks:
                started = time.perf_counter()
                response = client.post(f"/v1/sessions/{session_id}/chunks", json=chunk)
                chunk_ms.append((time.perf_counter() - started) * 1000)
                failures += int(response.status_code != 200)
            started = time.perf_counter()
            finalized = client.post(f"/v1/sessions/{session_id}/finalize")
            finalize_ms.append((time.perf_counter() - started) * 1000)
            failures += int(finalized.status_code != 200)

    result = {
        "environment": "in-process ASGI, SQLite memory, in-memory transcript store",
        "iterations": iterations,
        "requests": iterations * 5,
        "failures": failures,
        "create_ms": {
            "median": round(statistics.median(create_ms), 3),
            "p95": round(percentile(create_ms, 0.95), 3),
        },
        "chunk_ms": {
            "median": round(statistics.median(chunk_ms), 3),
            "p95": round(percentile(chunk_ms, 0.95), 3),
        },
        "finalize_ms": {
            "median": round(statistics.median(finalize_ms), 3),
            "p95": round(percentile(finalize_ms, 0.95), 3),
        },
    }
    path = Path("benchmark-result.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
