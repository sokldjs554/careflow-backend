"""Live public-demo contract for the Render deployment.

This intentionally uses only the Python standard library so the deployment gate can run
without installing the application. All payloads are synthetic and non-identifying.
"""

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("BASE_URL", "https://careflow-demo.onrender.com").rstrip("/")
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
            payload = request_json("GET", "/health/ready")
            if payload == {"status": "ready"}:
                print(f"readiness verified on attempt {attempt}")
                return
            last_error = RuntimeError(f"unexpected readiness payload: {payload}")
        except Exception as exc:  # external deployment may be warming up
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
        "Live Session",
        "Review Queue",
        "Engineering",
        "System",
        "근거 연결 상태",
        "정확도 지표 아님",
        "Data lifecycle",
        "Model Evaluation",
        "Post-training selection path",
        "데모 체험하기",
        "발화 수집",
        "Evidence map",
        "Review / Purge",
    ]
    missing = [token for token in required if token not in html]
    lowered = html.lower()
    exposed = [token for token in ("claude", "anthropic") if token in lowered]
    return missing, exposed


def verify_product_shell_after_deploy_converges() -> None:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            html = fetch_product_shell()
            Path("live-demo.html").write_text(html, encoding="utf-8")
            missing, exposed = product_shell_diagnostics(html)
            diagnostics = {
                "missing": missing,
                "provider_names_exposed": exposed,
                "html_length": len(html),
                "attempt": attempt,
            }
            Path("deployment-smoke-diagnostics.json").write_text(
                json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if exposed:
                raise AssertionError(
                    f"provider-specific names leaked into rendered demo: {exposed}"
                )
            if not missing:
                print(f"product shell verified on attempt {attempt}")
                return
            last_error = AssertionError(f"missing rendered product landmarks: {missing}")
        except Exception as exc:  # main push and Render auto-deploy can race
            last_error = exc
        if attempt < ATTEMPTS:
            print(
                f"product shell not converged yet ({attempt}/{ATTEMPTS}): {last_error}"
            )
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"product shell never converged to expected main UI: {last_error}")


def verify_operations_and_quality() -> None:
    operations = request_json("GET", "/v1/operations")
    expected_operations = {
        "database_ready": True,
        "database_backend": "sqlite",
        "transcript_store_ready": True,
        "transcript_store_backend": "memory",
        "note_generator_mode": "deterministic",
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
    print("operations and model-evaluation contracts verified")


def exercise_synthetic_session_once() -> str:
    session = request_json("POST", "/v1/sessions", {"language": "ko"})
    session_id = session["session_id"]
    chunks = [
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
    ]
    for chunk in chunks:
        ack = request_json("POST", f"/v1/sessions/{session_id}/chunks", chunk)
        if ack.get("duplicate") is not False:
            raise AssertionError(f"unexpected duplicate ack: {ack}")

    finalized = request_json("POST", f"/v1/sessions/{session_id}/finalize")
    if finalized.get("status") != "ready":
        raise AssertionError(f"normal synthetic session did not become READY: {finalized}")
    if finalized.get("review_required") is not False:
        raise AssertionError(f"normal synthetic session unexpectedly requires review: {finalized}")
    if finalized.get("transcript_purged") is not True:
        raise AssertionError(f"transcript was not purged after READY: {finalized}")

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


def verify_live_e2e_after_deploy_converges() -> None:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            session_id = exercise_synthetic_session_once()
            print(f"live E2E verified for synthetic session {session_id} on attempt {attempt}")
            return
        except Exception as exc:  # main push and Render auto-deploy race by design
            last_error = exc
        if attempt < ATTEMPTS:
            print(f"live E2E not converged yet ({attempt}/{ATTEMPTS}): {last_error}")
            time.sleep(RETRY_SECONDS)
    raise RuntimeError(f"live E2E never converged to expected main deployment: {last_error}")


def main() -> None:
    wait_for_ready()
    verify_product_shell_after_deploy_converges()
    verify_operations_and_quality()
    verify_live_e2e_after_deploy_converges()


if __name__ == "__main__":
    main()
