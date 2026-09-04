import asyncio
import json
import time

import httpx

from app.config import Settings
from app.services.note_generator import AnthropicClaudeNoteGenerator, DraftGenerationError
from app.services.transcript_store import TranscriptChunk


def _failure_summary(exc: DraftGenerationError) -> dict[str, object]:
    cause = exc.__cause__
    summary: dict[str, object] = {
        "status": "failed",
        "error_type": type(cause).__name__ if cause is not None else type(exc).__name__,
    }
    if isinstance(cause, httpx.HTTPStatusError):
        summary["http_status"] = cause.response.status_code
        try:
            payload = cause.response.json()
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    summary["api_error_type"] = str(error.get("type", ""))
                    summary["api_error_message"] = str(error.get("message", ""))[:500]
        except (ValueError, TypeError):
            pass
    elif isinstance(cause, httpx.TimeoutException):
        summary["hint"] = (
            "request timed out; structured-output cold start can need a longer timeout"
        )
    return summary


async def main() -> None:
    settings = Settings()
    api_key = (
        settings.anthropic_api_key.get_secret_value()
        if settings.anthropic_api_key is not None
        else ""
    )
    if not api_key.strip():
        raise SystemExit("ANTHROPIC_API_KEY를 .env 또는 셸 환경변수에 설정하세요.")

    generator = AnthropicClaudeNoteGenerator(
        base_url=settings.anthropic_base_url,
        api_key=api_key,
        model=settings.anthropic_model,
        anthropic_version=settings.anthropic_version,
        max_tokens=settings.anthropic_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    started = time.perf_counter()
    try:
        draft = await generator.generate(
            [
                TranscriptChunk(1, "patient", "최근 일주일 동안 잠드는 데 한 시간쯤 걸렸습니다."),
                TranscriptChunk(2, "patient", "아침에 피곤해서 업무에 집중하기 어려웠습니다."),
                TranscriptChunk(
                    3,
                    "clinician",
                    "대화 중 환자의 말투와 호흡은 차분하게 관찰되었습니다.",
                ),
                TranscriptChunk(4, "clinician", "다음 주에 수면 기록을 함께 확인할 계획입니다."),
            ]
        )
    except DraftGenerationError as exc:
        payload = _failure_summary(exc)
        payload["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None

    latency_ms = (time.perf_counter() - started) * 1000
    print(
        json.dumps(
            {
                "status": "success",
                "generator_version": generator.version,
                "latency_ms": round(latency_ms, 3),
                **draft.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
