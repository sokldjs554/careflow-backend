from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.note_generator import DeterministicDemoGenerator
from app.services.transcript_store import InMemoryTranscriptStore


@pytest.fixture
def transcript_store() -> InMemoryTranscriptStore:
    return InMemoryTranscriptStore()


@pytest.fixture
def client(transcript_store: InMemoryTranscriptStore) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url=None,
            transcript_ttl_seconds=300,
        ),
        transcript_store=transcript_store,
        note_generator=DeterministicDemoGenerator(),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_id(client: TestClient) -> str:
    response = client.post(
        "/v1/sessions", json={"language": "ko"}, headers={"Idempotency-Key": "test-session"}
    )
    assert response.status_code == 201
    return response.json()["session_id"]
