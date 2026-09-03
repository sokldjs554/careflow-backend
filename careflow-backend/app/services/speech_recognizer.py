import asyncio
import tempfile
import threading
from dataclasses import dataclass
from typing import Any, Protocol

AUDIO_SUFFIXES = {
    "audio/webm": ".webm",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
}


class SpeechRecognitionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SpeechRecognitionResult:
    text: str
    language: str
    duration_seconds: float


class SpeechRecognizer(Protocol):
    version: str

    async def transcribe(
        self, audio: bytes, content_type: str, language: str
    ) -> SpeechRecognitionResult: ...


class FasterWhisperRecognizer:
    """Lazy-loaded local Whisper adapter. Audio exists only in a temporary file."""

    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        beam_size: int,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model: Any | None = None
        self._model_lock = threading.Lock()
        self.version = f"faster-whisper-{model_name}-v1"

    async def transcribe(
        self, audio: bytes, content_type: str, language: str
    ) -> SpeechRecognitionResult:
        if not audio:
            raise SpeechRecognitionError("Audio payload is empty")
        suffix = AUDIO_SUFFIXES.get(content_type)
        if suffix is None:
            raise SpeechRecognitionError("Unsupported audio content type")
        try:
            return await asyncio.to_thread(self._transcribe_sync, audio, suffix, language)
        except SpeechRecognitionError:
            raise
        except Exception as exc:
            raise SpeechRecognitionError("Speech recognition failed") from exc

    def _transcribe_sync(
        self, audio: bytes, suffix: str, language: str
    ) -> SpeechRecognitionResult:
        model = self._get_model()
        with tempfile.NamedTemporaryFile(suffix=suffix) as audio_file:
            audio_file.write(audio)
            audio_file.flush()
            segments, info = model.transcribe(
                audio_file.name,
                language=language,
                task="transcribe",
                beam_size=self._beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip())

        if not text:
            raise SpeechRecognitionError("No speech was recognized")
        recognized_language = str(getattr(info, "language", language) or language)
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        return SpeechRecognitionResult(
            text=text[:4000],
            language=recognized_language,
            duration_seconds=duration,
        )

    def _get_model(self) -> Any:
        with self._model_lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise SpeechRecognitionError(
                        "Install the speech extra before enabling faster-whisper"
                    ) from exc
                self._model = WhisperModel(
                    self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )
        return self._model
