import json

import httpx
import pytest

from app.config import Settings
from app.main import _generator
from app.services.note_generator import (
    AnthropicClaudeNoteGenerator,
    DraftGenerationError,
)
from app.services.transcript_store import TranscriptChunk

API_KEY = "test-secret-key"


def _generator_with_transport(
    transport: httpx.AsyncBaseTransport,
) -> AnthropicClaudeNoteGenerator:
    return AnthropicClaudeNoteGenerator(
        base_url="https://api.anthropic.test",
        api_key=API_KEY,
        model="claude-sonnet-5",
        anthropic_version="2023-06-01",
        max_tokens=1600,
        timeout_seconds=3,
        transport=transport,
    )


def _success_body(draft: dict[str, object], stop_reason: str = "end_turn") -> dict[str, object]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "stop_reason": stop_reason,
        "content": [{"type": "text", "text": json.dumps(draft, ensure_ascii=False)}],
        "usage": {"input_tokens": 100, "output_tokens": 80},
    }


@pytest.mark.asyncio
async def test_claude_uses_native_messages_api_and_structured_output() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=_success_body(
                {
                    "subjective": "환자는 최근 일주일 동안 잠들기 어려웠다고 말함.",
                    "objective": "의료진은 표정과 말투가 차분하다고 관찰함.",
                    "plan": "의료진은 다음 주 수면 상태를 추적하기로 함.",
                    "evidence": [
                        {"section": "subjective", "source_sequences": [1]},
                        {"section": "objective", "source_sequences": [2]},
                        {"section": "plan", "source_sequences": [3]},
                    ],
                }
            ),
        )

    generator = _generator_with_transport(httpx.MockTransport(handler))
    draft = await generator.generate(
        [
            TranscriptChunk(1, "patient", "최근 일주일 동안 잠들기 어려웠습니다."),
            TranscriptChunk(2, "clinician", "표정과 말투가 차분한 것을 관찰했습니다."),
            TranscriptChunk(3, "clinician", "다음 주 수면 상태를 추적할 계획입니다."),
        ]
    )

    assert captured["url"] == "https://api.anthropic.test/v1/messages"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["x-api-key"] == API_KEY
    assert headers["anthropic-version"] == "2023-06-01"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "claude-sonnet-5"
    assert payload["max_tokens"] == 1600
    assert payload["output_config"]["format"]["type"] == "json_schema"  # type: ignore[index]
    assert payload["output_config"]["format"]["schema"]["additionalProperties"] is False  # type: ignore[index]
    assert "진단" in payload["system"]  # type: ignore[operator]
    assert draft.evidence[2].source_sequences == [3]
    assert generator.version == "anthropic-claude-sonnet-5-sop-v1"


@pytest.mark.asyncio
async def test_claude_schema_violation_is_rejected_without_leaking_key() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(
                {
                    "subjective": "환자 진술",
                    "objective": "관찰 내용",
                    "assessment": "금지된 자동 판단",
                    "plan": "명시된 계획",
                    "evidence": [
                        {"section": "subjective", "source_sequences": [1]},
                        {"section": "objective", "source_sequences": [2]},
                        {"section": "plan", "source_sequences": [3]},
                    ],
                }
            ),
        )

    generator = _generator_with_transport(httpx.MockTransport(handler))
    with pytest.raises(DraftGenerationError) as exc_info:
        await generator.generate([TranscriptChunk(1, "patient", "합성 발화")])

    assert API_KEY not in str(exc_info.value)
    assert "S/O/P contract" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_claude_incomplete_or_refused_output_is_rejected(stop_reason: str) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body({}, stop_reason=stop_reason))

    generator = _generator_with_transport(httpx.MockTransport(handler))
    with pytest.raises(DraftGenerationError):
        await generator.generate([TranscriptChunk(1, "patient", "합성 발화")])


@pytest.mark.asyncio
async def test_claude_http_failure_is_mapped_to_generation_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "temporary unavailable"}})

    generator = _generator_with_transport(httpx.MockTransport(handler))
    with pytest.raises(DraftGenerationError):
        await generator.generate([TranscriptChunk(1, "patient", "합성 발화")])


def test_anthropic_mode_requires_api_key() -> None:
    settings = Settings(note_generator_mode="anthropic", anthropic_api_key=None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _generator(settings)


def test_anthropic_mode_rejects_empty_api_key() -> None:
    settings = Settings(note_generator_mode="anthropic", anthropic_api_key="")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _generator(settings)


def test_anthropic_mode_builds_claude_generator() -> None:
    settings = Settings(note_generator_mode="anthropic", anthropic_api_key=API_KEY)
    generator = _generator(settings)
    assert isinstance(generator, AnthropicClaudeNoteGenerator)
    assert API_KEY not in repr(generator.__dict__)
