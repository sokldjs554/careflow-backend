from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AuditEvent
from app.schemas import GeneratedDraft
from app.services.note_generator import DeterministicDemoGenerator, DraftGenerationError
from app.services.transcript_store import InMemoryTranscriptStore, TranscriptChunk


def _append_complete_transcript(client: TestClient, session_id: str) -> None:
    chunks = [
        {"sequence": 1, "speaker": "patient", "text": "최근 일주일 동안 잠들기 어려웠습니다."},
        {"sequence": 2, "speaker": "clinician", "text": "표정과 말투가 차분한 것을 관찰했습니다."},
        {"sequence": 3, "speaker": "clinician", "text": "다음 주에 수면 상태를 추적할 계획입니다."},
    ]
    for chunk in chunks:
        response = client.post(f"/v1/sessions/{session_id}/chunks", json=chunk)
        assert response.status_code == 200


def test_finalize_creates_sop_only_and_purges_transcript(
    client: TestClient, session_id: str, transcript_store: InMemoryTranscriptStore
) -> None:
    _append_complete_transcript(client, session_id)

    finalized = client.post(f"/v1/sessions/{session_id}/finalize")
    draft = client.get(f"/v1/sessions/{session_id}/draft")

    assert finalized.status_code == 200
    assert finalized.json()["status"] == "ready"
    assert finalized.json()["transcript_purged"] is True
    assert draft.status_code == 200
    body = draft.json()
    assert set(body) >= {"subjective", "objective", "plan", "evidence"}
    assert "assessment" not in body
    assert body["review_required"] is False
    assert client.portal is not None
    assert client.portal.call(transcript_store.list_chunks, session_id) == []


def test_safety_signal_forces_human_review(client: TestClient, session_id: str) -> None:
    chunks = [
        {"sequence": 1, "speaker": "patient", "text": "요즘 죽고 싶다는 생각이 들 때가 있습니다."},
        {"sequence": 2, "speaker": "clinician", "text": "말투가 느린 것을 관찰했습니다."},
        {
            "sequence": 3,
            "speaker": "clinician",
            "text": "즉시 담당자가 검토하고 다음 계획을 정합니다.",
        },
    ]
    for chunk in chunks:
        client.post(f"/v1/sessions/{session_id}/chunks", json=chunk)

    finalized = client.post(f"/v1/sessions/{session_id}/finalize").json()
    assert finalized["status"] == "review_required"
    assert finalized["review_required"] is True
    assert "potential_safety_signal" in finalized["review_reasons"]


def test_evidence_gap_forces_review(client: TestClient, session_id: str) -> None:
    client.post(
        f"/v1/sessions/{session_id}/chunks",
        json={"sequence": 1, "speaker": "patient", "text": "최근 잠이 줄었습니다."},
    )
    finalized = client.post(f"/v1/sessions/{session_id}/finalize").json()
    assert finalized["status"] == "review_required"
    assert "evidence_gap" in finalized["review_reasons"]


def test_sequence_gap_forces_review(client: TestClient, session_id: str) -> None:
    chunks = [
        {"sequence": 1, "speaker": "patient", "text": "최근 잠들기 어렵습니다."},
        {"sequence": 3, "speaker": "clinician", "text": "표정을 관찰했습니다."},
        {"sequence": 4, "speaker": "clinician", "text": "다음 주 추적할 계획입니다."},
    ]
    for chunk in chunks:
        client.post(f"/v1/sessions/{session_id}/chunks", json=chunk)
    finalized = client.post(f"/v1/sessions/{session_id}/finalize").json()
    assert finalized["status"] == "review_required"
    assert "sequence_gap" in finalized["review_reasons"]


def test_explicit_purge_removes_draft(client: TestClient, session_id: str) -> None:
    _append_complete_transcript(client, session_id)
    client.post(f"/v1/sessions/{session_id}/finalize")
    response = client.delete(f"/v1/sessions/{session_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "purged"
    assert response.json()["draft_purged"] is True
    assert client.get(f"/v1/sessions/{session_id}/draft").status_code == 409


def test_cannot_append_after_finalize(client: TestClient, session_id: str) -> None:
    _append_complete_transcript(client, session_id)
    client.post(f"/v1/sessions/{session_id}/finalize")
    response = client.post(
        f"/v1/sessions/{session_id}/chunks",
        json={"sequence": 4, "speaker": "patient", "text": "추가 발화"},
    )
    assert response.status_code == 409


class FailingGenerator:
    version = "failing-test-v1"

    async def generate(self, _: object) -> object:
        raise DraftGenerationError("simulated provider failure")


@pytest.fixture
def failure_client() -> Iterator[TestClient]:
    store = InMemoryTranscriptStore()
    app = create_app(
        settings=Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url=None,
            transcript_ttl_seconds=300,
        ),
        transcript_store=store,
        note_generator=FailingGenerator(),  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client


def test_generation_failure_routes_to_review_and_keeps_ttl_source(
    failure_client: TestClient,
) -> None:
    created = failure_client.post("/v1/sessions", json={"language": "ko"}).json()
    session_id = created["session_id"]
    failure_client.post(
        f"/v1/sessions/{session_id}/chunks",
        json={"sequence": 1, "speaker": "patient", "text": "합성 발화"},
    )
    finalized = failure_client.post(f"/v1/sessions/{session_id}/finalize").json()
    assert finalized["status"] == "review_required"
    assert finalized["transcript_purged"] is False
    assert finalized["review_reasons"] == ["generation_failure"]
    assert failure_client.portal is not None
    chunks = failure_client.portal.call(
        failure_client.app.state.transcript_store.list_chunks, session_id
    )
    assert [chunk.text for chunk in chunks] == ["합성 발화"]


class RecoveringGenerator:
    version = "recovering-test-v1"

    def __init__(self) -> None:
        self.calls = 0
        self.delegate = DeterministicDemoGenerator()

    async def generate(self, chunks: list[TranscriptChunk]) -> GeneratedDraft:
        self.calls += 1
        if self.calls == 1:
            raise DraftGenerationError("simulated transient provider failure")
        return await self.delegate.generate(chunks)


def test_generation_failure_can_retry_from_retained_source() -> None:
    store = InMemoryTranscriptStore()
    generator = RecoveringGenerator()
    app = create_app(
        settings=Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url=None,
            transcript_ttl_seconds=300,
        ),
        transcript_store=store,
        note_generator=generator,
    )
    with TestClient(app) as test_client:
        session_id = test_client.post("/v1/sessions", json={"language": "ko"}).json()[
            "session_id"
        ]
        _append_complete_transcript(test_client, session_id)

        failed = test_client.post(f"/v1/sessions/{session_id}/finalize").json()
        recovered = test_client.post(f"/v1/sessions/{session_id}/finalize").json()
        repeated = test_client.post(f"/v1/sessions/{session_id}/finalize").json()

        assert failed["review_reasons"] == ["generation_failure"]
        assert failed["transcript_purged"] is False
        assert recovered["status"] == "ready"
        assert recovered["review_required"] is False
        assert recovered["transcript_purged"] is True
        assert repeated["status"] == "ready"
        assert repeated["transcript_purged"] is True
        assert generator.calls == 2


def test_audit_log_stores_hash_not_transcript(client: TestClient, session_id: str) -> None:
    raw_text = "감사 로그에 남으면 안 되는 합성 발화"
    client.post(
        f"/v1/sessions/{session_id}/chunks",
        json={"sequence": 1, "speaker": "patient", "text": raw_text},
    )

    async def read_audits() -> list[AuditEvent]:
        async with client.app.state.database.session() as db:
            return list((await db.scalars(select(AuditEvent))).all())

    assert client.portal is not None
    events = client.portal.call(read_audits)
    assert events
    assert all(len(event.payload_hash) == 64 for event in events)
    assert all(raw_text not in event.payload_hash for event in events)
