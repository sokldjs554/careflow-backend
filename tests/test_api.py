from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.note_generator import DeterministicDemoGenerator
from app.services.transcript_store import InMemoryTranscriptStore


def test_health_and_security_headers(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


def test_demo_page_is_available(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "CareFlow" in response.text
    assert "합성·비식별 데이터" in response.text


def test_capabilities_do_not_expose_secrets(client: TestClient) -> None:
    response = client.get("/v1/capabilities")
    assert response.status_code == 200
    assert response.json() == {
        "note_generator_version": "deterministic-demo-v1",
        "speech_enabled": False,
        "speech_recognizer_version": None,
    }
    assert "api_key" not in response.text.lower()


def test_capabilities_report_lazy_faster_whisper_without_loading_model() -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            speech_recognition_mode="faster_whisper",
            whisper_model="small",
        ),
        transcript_store=InMemoryTranscriptStore(),
        note_generator=DeterministicDemoGenerator(),
    )
    with TestClient(app) as test_client:
        response = test_client.get("/v1/capabilities")

    assert response.json() == {
        "note_generator_version": "deterministic-demo-v1",
        "speech_enabled": True,
        "speech_recognizer_version": "faster-whisper-small-v1",
    }


def test_idempotent_session_creation(client: TestClient) -> None:
    headers = {"Idempotency-Key": "same-request"}
    first = client.post("/v1/sessions", json={"language": "ko"}, headers=headers)
    second = client.post("/v1/sessions", json={"language": "ko"}, headers=headers)
    conflict = client.post("/v1/sessions", json={"language": "en"}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["session_id"] == second.json()["session_id"]
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"


def test_chunk_is_idempotent_by_sequence(client: TestClient, session_id: str) -> None:
    payload = {"sequence": 1, "speaker": "patient", "text": "최근 잠을 잘 이루지 못했습니다."}
    first = client.post(f"/v1/sessions/{session_id}/chunks", json=payload)
    duplicate = client.post(f"/v1/sessions/{session_id}/chunks", json=payload)

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert duplicate.json()["duplicate"] is True


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    response = client.post("/v1/sessions", json={"language": "ko", "patient_name": "홍길동"})
    assert response.status_code == 422


def test_missing_session_is_404(client: TestClient) -> None:
    response = client.get("/v1/sessions/not-found")
    assert response.status_code == 404
    assert response.json()["code"] == "session_not_found"
