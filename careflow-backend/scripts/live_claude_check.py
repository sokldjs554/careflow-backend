import asyncio
import json

from app.config import Settings
from app.services.note_generator import AnthropicClaudeNoteGenerator
from app.services.transcript_store import TranscriptChunk


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
    draft = await generator.generate(
        [
            TranscriptChunk(1, "patient", "최근 일주일 동안 잠드는 데 한 시간쯤 걸렸습니다."),
            TranscriptChunk(2, "patient", "아침에 피곤해서 업무에 집중하기 어려웠습니다."),
            TranscriptChunk(3, "clinician", "대화 중 말투와 호흡은 차분하게 관찰되었습니다."),
            TranscriptChunk(4, "clinician", "다음 주에 수면 기록을 함께 확인할 계획입니다."),
        ]
    )
    print(
        json.dumps(
            {"generator_version": generator.version, **draft.model_dump()},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
