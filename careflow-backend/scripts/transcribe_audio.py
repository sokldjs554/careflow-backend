import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.config import Settings
from app.services.speech_recognizer import AUDIO_SUFFIXES, FasterWhisperRecognizer

CONTENT_TYPES_BY_SUFFIX = {suffix: content_type for content_type, suffix in AUDIO_SUFFIXES.items()}


async def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 faster-whisper 단일 파일 검증")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--content-type")
    args = parser.parse_args()

    settings = Settings()
    content_type = args.content_type or CONTENT_TYPES_BY_SUFFIX.get(args.audio.suffix.lower())
    if content_type not in AUDIO_SUFFIXES:
        raise SystemExit("지원 형식: webm, mp4/m4a, ogg, wav, mp3")

    recognizer = FasterWhisperRecognizer(
        model_name=settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        beam_size=settings.whisper_beam_size,
    )
    result = await recognizer.transcribe(
        args.audio.read_bytes(),
        content_type=content_type,
        language="ko",
    )
    print(
        json.dumps(
            {"recognizer_version": recognizer.version, **asdict(result)},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
