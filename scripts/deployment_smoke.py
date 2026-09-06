"""Live contract for the public Render demo.

The public demo intentionally runs a low-cost SQLite + in-memory transcript store while
CI separately proves PostgreSQL 16 + Redis 7 integration. This smoke test verifies the
actual public runtime, product shell, model-evaluation evidence, and both normal and
human-review lifecycle paths using only synthetic data.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("BASE_URL", "https://careflow-demo.onrender.com").rstrip("/")
EXPECTED_GIT_COMMIT = os.environ.get("EXPECTED_GIT_COMMIT", "").strip()
EXPECTED_DATABASE_BACKEND = os.environ.get("EXPECTED_DATABASE_BACKEND", "sqlite").strip()
EXPECTED_TRANSCRIPT_STORE_BACKEND = os.environ.get(
    "EXPECTED_TRANSCRIPT_STORE_BACKEND", "memory"
).strip()
EXPECTED_ENVIRONMENT = os.environ.get("EXPECTED_ENVIRONMENT", "render-demo").strip()
ATTEMPTS = 30
RETRY_SECONDS = 10


def request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def wait_for_ready() -> None:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            ready = request_json("GET", "/health/ready")
            if ready != {"status": "ready"}:
                raise RuntimeError(f"unexpected readiness payload: {ready}")
            if EXPECTED_GIT_COMMIT:
                release = request_json("GET", "/v1/release")
                release_commit = release.get("commit") or release.get("git_commit")
                if release_commit != EXPECTED_GIT_COMMIT:
                    raise RuntimeError(
                        "release mismatch: "
                        f"{release_commit!r} != {EXPECTED_GIT_COMMIT!r}"
                    )
            print(f"readiness and release verified on attempt {attempt}")
            return
        except Exception as exc:  # public instance may still be warming up
            last_error = exc
        if attempt < ATTEMPTS:
            print(f"not ready yet ({attempt}/{ATTEMPTS}): {last_error}")
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"deployment never became ready: {last_error}")


def fetch_product_shell() -> str:
    with urllib.request.urlopen(f"{BASE_URL}/", timeout=30) as response:  # noqa: S310
        return response.read().decode("utf-8")


def product_shell_diagnostics(html: str) -> tuple[list[str], list[str]]:
    required = [
        "상담의 중요한 순간을,",
        "놓치지 않는 기록으로.",
        "상담 시작하기",
        "서비스 소개 보기",
        "service-intro-section",
        "상담 기록",
        "검토 대기",
        "검증 결과",
        "시스템 상태",
        "근거 연결 상태",
        "정확도 지표 아님",
        "데이터 보존 상태",
        "transcript",
        "draft-box",
        "signal-row",
        "lifecycle",
        "새 상담 시작",
        "발화 수집",
        "근거 연결",
        "기록 초안",
        "검토 / 삭제",
        "모델 선택 기록",
    ]
    missing = [token for token in required if token not in html]
    lowered = html.lower()
    exposed = [token for token in ("claude", "anthropic") if token in lowered]
    legacy_copy = [
        "데모 체험하기",
        "Engineering</button>",
        "Live Session</button>",
        "AI Quality</button>",
    ]
    exposed.extend(token for token in legacy_copy if token in html)
    return missing, exposed


def verify_product_shell() -> None:
    html = fetch_product_shell()
    Path("live-demo.html").write_text(html, encoding="utf-8")
    missing, exposed = product_shell_diagnostics(html)
    diagnostics = {
        "missing": missing,
        "forbidden_or_provider_copy": exposed,
        "html_length": len(html),
    }
    Path("deployment-smoke-diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if exposed:
        raise AssertionError(f"forbidden/provider-specific copy leaked into demo: {exposed}")
    if missing:
        raise AssertionError(f"missing product landmarks: {missing}")
    print("product shell verified")


def verify_operations_and_quality() -> None:
    operations = request_json("GET", "/v1/operations")
    expected_operations = {
        "environment": EXPECTED_ENVIRONMENT,
        "database_ready": True,
        "database_backend": EXPECTED_DATABASE_BACKEND,
        "transcript_store_ready": True,
        "transcript_store_backend": EXPECTED_TRANSCRIPT_STORE_BACKEND,
        "note_generator_mode": "deterministic",
        "speech_enabled": False,
    }
    for key, expected in expected_operations.items():
        actual = operations.get(key)
        if actual != expected:
            raise AssertionError(f"operations mismatch for {key}: {actual!r} != {expected!r}")

    quality = request_json("GET", "/v1/quality")
    if quality.get("clinical_validation") is not False:
        raise AssertionError("clinical_validation boundary must remain false")
    gates = {gate["key"]: gate for gate in quality.get("gates", [])}
    expected_statuses = {
        "rag": "verified_not_adopted",
        "sft": "adopted",
        "dpo": "rejected",
        "judge": "verified",
        "multimodal": "verified",
    }
    for key, expected in expected_statuses.items():
        if gates.get(key, {}).get("status") != expected:
            raise AssertionError(f"quality status mismatch for {key}")

    sft = gates["sft"]["metrics"]
    dpo = gates["dpo"]["metrics"]
    if sft.get("base_reference_token_f1") != 0.0648:
        raise AssertionError("unexpected SFT base F1")
    if sft.get("candidate_reference_token_f1") != 0.1244:
        raise AssertionError("unexpected SFT candidate F1")
    if dpo.get("dpo_reference_token_f1") != 0.1093:
        raise AssertionError("unexpected DPO candidate F1")
    print(
        "operations verified: "
        f"{EXPECTED_DATABASE_BACKEND} + {EXPECTED_TRANSCRIPT_STORE_BACKEND}; "
        "model-evaluation contracts verified"
    )


def append_chunks(session_id: str, chunks: list[dict[str, Any]]) -> None:
    for chunk in chunks:
        ack = request_json("POST", f"/v1/sessions/{session_id}/chunks", chunk)
        if ack.get("duplicate") is not False:
            raise AssertionError(f"unexpected duplicate ack: {ack}")


def exercise_normal_session() -> str:
    session = request_json("POST", "/v1/sessions", {"language": "ko"})
    session_id = session["session_id"]
    append_chunks(
        session_id,
        [
            {
                "sequence": 1,
                "speaker": "patient",
                "text": "최근 일주일 동안 잠드는 데 한 시간쯤 걸렸습니다.",
            },
            {
                "sequence": 2,
                "speaker": "patient",
                "text": "아침에 피곤해서 업무에 집중하기 어려웠습니다.",
            },
            {
                "sequence": 3,
                "speaker": "clinician",
                "text": "대화 중 말투와 호흡은 차분하게 관찰되었습니다.",
            },
            {
                "sequence": 4,
                "speaker": "clinician",
                "text": "다음 주에 수면 기록을 함께 확인할 계획입니다.",
            },
        ],
    )
    finalized = request_json("POST", f"/v1/sessions/{session_id}/finalize")
    expected_final = {
        "status": "ready",
        "review_required": False,
        "transcript_purged": True,
    }
    for key, expected in expected_final.items():
        if finalized.get(key) != expected:
            raise AssertionError(f"normal session mismatch for {key}: {finalized}")

    draft = request_json("GET", f"/v1/sessions/{session_id}/draft")
    evidence = {item["section"]: item["source_sequences"] for item in draft["evidence"]}
    expected_evidence = {"subjective": [1, 2], "objective": [3], "plan": [4]}
    if evidence != expected_evidence:
        raise AssertionError(f"unexpected evidence map: {evidence}")

    transcript = request_json("GET", f"/v1/sessions/{session_id}/transcript")
    if transcript.get("transcript_available") is not False or transcript.get("chunks") != []:
        raise AssertionError(f"purged transcript is still available: {transcript}")

    audit = request_json("GET", f"/v1/sessions/{session_id}/audit")
    event_types = {event["event_type"] for event in audit}
    required_events = {"session.finalized", "transcript.purged"}
    if not required_events <= event_types:
        raise AssertionError(f"missing lifecycle audit events: {required_events - event_types}")
    return session_id


def exercise_review_session() -> str:
    session = request_json("POST", "/v1/sessions", {"language": "ko"})
    session_id = session["session_id"]
    append_chunks(
        session_id,
        [
            {
                "sequence": 1,
                "speaker": "patient",
                "text": "요즘 죽고 싶다는 생각이 들 때가 있습니다.",
            },
            {
                "sequence": 2,
                "speaker": "clinician",
                "text": "대화 중 말투가 느린 것을 관찰했습니다.",
            },
            {
                "sequence": 3,
                "speaker": "clinician",
                "text": "즉시 담당자가 검토하고 다음 계획을 정합니다.",
            },
        ],
    )
    finalized = request_json("POST", f"/v1/sessions/{session_id}/finalize")
    if finalized.get("status") != "review_required":
        raise AssertionError(f"safety session was not routed to review: {finalized}")
    if finalized.get("review_required") is not True:
        raise AssertionError(f"review flag missing for safety session: {finalized}")
    if "potential_safety_signal" not in finalized.get("review_reasons", []):
        raise AssertionError(f"safety reason missing: {finalized}")
    if finalized.get("transcript_purged") is not False:
        raise AssertionError("review transcript was purged before human approval")

    retained = request_json("GET", f"/v1/sessions/{session_id}/transcript")
    if retained.get("transcript_available") is not True or not retained.get("chunks"):
        raise AssertionError("review transcript was not retained for human review")

    draft = request_json("GET", f"/v1/sessions/{session_id}/draft")
    approved = request_json(
        "PATCH",
        f"/v1/sessions/{session_id}/draft",
        {
            "subjective": draft["subjective"],
            "objective": draft["objective"],
            "plan": draft["plan"],
            "action": "approve",
        },
    )
    if approved.get("review_required") is not False:
        raise AssertionError(f"review remained pending after approval: {approved}")
    if approved.get("transcript_purged") is not True:
        raise AssertionError(f"approval did not purge transcript: {approved}")

    purged = request_json("GET", f"/v1/sessions/{session_id}/transcript")
    if purged.get("transcript_available") is not False or purged.get("chunks") != []:
        raise AssertionError("approved review transcript is still available")
    return session_id


def main() -> None:
    wait_for_ready()
    verify_product_shell()
    verify_operations_and_quality()
    normal_id = exercise_normal_session()
    review_id = exercise_review_session()
    print(f"live E2E verified: normal={normal_id}, review={review_id}")


if __name__ == "__main__":
    main()
