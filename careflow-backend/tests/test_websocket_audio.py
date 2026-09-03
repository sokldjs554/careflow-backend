from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.note_generator import DeterministicDemoGenerator
from app.services.speech_recognizer import (
    SpeechRecognitionError,
    SpeechRecognitionResult,
)
from app.services.transcript_store import InMemoryTranscriptStore


class FakeSpeechRecognizer:
    version = "fake-whisper-v1"

    def __init__(self, duration_seconds: float = 2.4) -> None:
        self.duration_seconds = duration_seconds
        self.calls: list[tuple[bytes, str, str]] = []

    async def transcribe(
        self, audio: bytes, content_type: str, language: str
    ) -> SpeechRecognitionResult:
        self.calls.append((audio, content_type, language))
        return SpeechRecognitionResult(
            text="최근 일주일 동안 잠들기 어려웠습니다.",
            language="ko",
            duration_seconds=self.duration_seconds,
        )


class FailingSpeechRecognizer:
    version = "failing-whisper-v1"

    async def transcribe(
        self, audio: bytes, content_type: str, language: str
    ) -> SpeechRecognitionResult:
        raise SpeechRecognitionError("simulated decoder failure")


def _client(
    recognizer: object,
    store: InMemoryTranscriptStore,
    *,
    max_audio_bytes: int = 10_000_000,
    max_duration_seconds: float = 45,
) -> Iterator[TestClient]:
    app = create_app(
        settings=Settings(
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url=None,
            transcript_ttl_seconds=300,
            speech_max_audio_bytes=max_audio_bytes,
            speech_max_duration_seconds=max_duration_seconds,
        ),
        transcript_store=store,
        note_generator=DeterministicDemoGenerator(),
        speech_recognizer=recognizer,  # type: ignore[arg-type]
    )
    with TestClient(app) as test_client:
        yield test_client


def _session(test_client: TestClient) -> str:
    return test_client.post("/v1/sessions", json={"language": "ko"}).json()["session_id"]


def test_websocket_audio_is_transcribed_and_only_text_enters_store() -> None:
    store = InMemoryTranscriptStore()
    recognizer = FakeSpeechRecognizer()
    raw_audio = b"synthetic-webm-bytes"

    for test_client in _client(recognizer, store):
        session_id = _session(test_client)
        with test_client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
            websocket.send_json(
                {
                    "type": "audio.start",
                    "sequence": 1,
                    "speaker": "patient",
                    "content_type": "audio/webm",
                }
            )
            assert websocket.receive_json() == {"type": "audio.ready", "sequence": 1}
            websocket.send_bytes(raw_audio)
            recognized = websocket.receive_json()

        assert recognized["type"] == "transcript.recognized"
        assert recognized["text"] == "최근 일주일 동안 잠들기 어려웠습니다."
        assert recognized["raw_audio_persisted"] is False
        assert recognized["recognizer_version"] == "fake-whisper-v1"
        assert recognizer.calls == [(raw_audio, "audio/webm", "ko")]
        assert test_client.portal is not None
        chunks = test_client.portal.call(store.list_chunks, session_id)
        assert [chunk.text for chunk in chunks] == [recognized["text"]]
        assert all(raw_audio.decode() not in chunk.text for chunk in chunks)


def test_websocket_audio_requires_configured_recognizer(
    client: TestClient, session_id: str
) -> None:
    with client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json(
            {
                "type": "audio.start",
                "sequence": 1,
                "speaker": "patient",
                "content_type": "audio/webm",
            }
        )
        response = websocket.receive_json()
    assert response == {"type": "error", "code": "speech_not_configured"}


def test_websocket_rejects_oversized_audio_before_recognition() -> None:
    store = InMemoryTranscriptStore()
    recognizer = FakeSpeechRecognizer()
    for test_client in _client(recognizer, store, max_audio_bytes=1024):
        session_id = _session(test_client)
        with test_client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
            websocket.send_json(
                {
                    "type": "audio.start",
                    "sequence": 1,
                    "speaker": "patient",
                    "content_type": "audio/webm",
                }
            )
            websocket.receive_json()
            websocket.send_bytes(b"x" * 1025)
            response = websocket.receive_json()
        assert response == {"type": "error", "code": "audio_payload_too_large"}
        assert recognizer.calls == []


def test_websocket_rejects_audio_over_duration_limit_without_storing_text() -> None:
    store = InMemoryTranscriptStore()
    recognizer = FakeSpeechRecognizer(duration_seconds=46)
    for test_client in _client(recognizer, store, max_duration_seconds=45):
        session_id = _session(test_client)
        with test_client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
            websocket.send_json(
                {
                    "type": "audio.start",
                    "sequence": 1,
                    "speaker": "patient",
                    "content_type": "audio/webm",
                }
            )
            websocket.receive_json()
            websocket.send_bytes(b"audio")
            response = websocket.receive_json()
        assert response == {"type": "error", "code": "audio_duration_too_long"}
        assert test_client.portal is not None
        assert test_client.portal.call(store.list_chunks, session_id) == []


def test_websocket_maps_decoder_failure_without_exposing_detail() -> None:
    store = InMemoryTranscriptStore()
    for test_client in _client(FailingSpeechRecognizer(), store):
        session_id = _session(test_client)
        with test_client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
            websocket.send_json(
                {
                    "type": "audio.start",
                    "sequence": 1,
                    "speaker": "patient",
                    "content_type": "audio/webm",
                }
            )
            websocket.receive_json()
            websocket.send_bytes(b"invalid-audio")
            response = websocket.receive_json()
        assert response == {"type": "error", "code": "speech_recognition_failed"}
