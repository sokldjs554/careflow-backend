from dataclasses import dataclass

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.schemas import Speaker, TranscriptChunkInput, WebSocketEnvelope
from app.services.session_service import SessionService
from app.services.speech_recognizer import SpeechRecognitionError, SpeechRecognizer

router = APIRouter(prefix="/v1")


@dataclass(frozen=True, slots=True)
class _PendingAudio:
    sequence: int
    speaker: Speaker
    content_type: str


@router.websocket("/ws/sessions/{session_id}")
async def session_stream(websocket: WebSocket, session_id: str) -> None:
    service: SessionService = websocket.app.state.session_service
    recognizer: SpeechRecognizer | None = websocket.app.state.speech_recognizer
    pending_audio: _PendingAudio | None = None
    await websocket.accept()
    try:
        await service.get_session(session_id)
    except LookupError:
        await websocket.send_json({"type": "error", "code": "session_not_found"})
        await websocket.close(code=4404)
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return

            audio = message.get("bytes")
            if isinstance(audio, bytes):
                if pending_audio is None:
                    await websocket.send_json(
                        {"type": "error", "code": "audio_start_required"}
                    )
                    continue
                current = pending_audio
                pending_audio = None
                if len(audio) > service.settings.speech_max_audio_bytes:
                    await websocket.send_json(
                        {"type": "error", "code": "audio_payload_too_large"}
                    )
                    continue
                if recognizer is None:
                    await websocket.send_json(
                        {"type": "error", "code": "speech_not_configured"}
                    )
                    continue
                try:
                    result = await recognizer.transcribe(
                        audio,
                        content_type=current.content_type,
                        language="ko",
                    )
                    if result.duration_seconds > service.settings.speech_max_duration_seconds:
                        await websocket.send_json(
                            {"type": "error", "code": "audio_duration_too_long"}
                        )
                        continue
                    chunk_result = await service.append_chunk(
                        session_id,
                        TranscriptChunkInput(
                            sequence=current.sequence,
                            speaker=current.speaker,
                            text=result.text,
                        ),
                    )
                    await websocket.send_json(
                        {
                            "type": "transcript.recognized",
                            "sequence": chunk_result.sequence,
                            "speaker": current.speaker.value,
                            "text": result.text,
                            "duplicate": chunk_result.duplicate,
                            "language": result.language,
                            "duration_seconds": result.duration_seconds,
                            "recognizer_version": recognizer.version,
                            "raw_audio_persisted": False,
                        }
                    )
                except SpeechRecognitionError:
                    await websocket.send_json(
                        {"type": "error", "code": "speech_recognition_failed"}
                    )
                except RuntimeError as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "code": "invalid_session_state",
                            "detail": str(exc),
                        }
                    )
                continue

            raw_text = message.get("text")
            if not isinstance(raw_text, str):
                await websocket.send_json({"type": "error", "code": "invalid_message"})
                continue

            try:
                envelope = WebSocketEnvelope.model_validate_json(raw_text)
                if envelope.type == "transcript.chunk":
                    if envelope.sequence is None or envelope.text is None:
                        raise ValueError("sequence and text are required")
                    chunk_result = await service.append_chunk(
                        session_id,
                        TranscriptChunkInput(
                            sequence=envelope.sequence,
                            speaker=envelope.speaker,
                            text=envelope.text,
                        ),
                    )
                    await websocket.send_json(
                        {
                            "type": "transcript.ack",
                            "sequence": chunk_result.sequence,
                            "duplicate": chunk_result.duplicate,
                        }
                    )
                elif envelope.type == "audio.start":
                    if recognizer is None:
                        await websocket.send_json(
                            {"type": "error", "code": "speech_not_configured"}
                        )
                        continue
                    if pending_audio is not None:
                        await websocket.send_json(
                            {"type": "error", "code": "audio_already_started"}
                        )
                        continue
                    if envelope.sequence is None or envelope.sequence < 1:
                        raise ValueError("a positive sequence is required")
                    if envelope.speaker == Speaker.UNKNOWN:
                        raise ValueError("patient or clinician speaker is required")
                    if envelope.content_type is None:
                        raise ValueError("content_type is required")
                    pending_audio = _PendingAudio(
                        sequence=envelope.sequence,
                        speaker=envelope.speaker,
                        content_type=envelope.content_type,
                    )
                    await websocket.send_json(
                        {"type": "audio.ready", "sequence": envelope.sequence}
                    )
                elif envelope.type == "audio.cancel":
                    pending_audio = None
                    await websocket.send_json({"type": "audio.cancelled"})
                elif envelope.type == "session.finalize":
                    if pending_audio is not None:
                        await websocket.send_json(
                            {"type": "error", "code": "audio_payload_pending"}
                        )
                        continue
                    finalize_result = await service.finalize(session_id)
                    await websocket.send_json(
                        {
                            "type": "session.finalized",
                            "status": finalize_result.status.value,
                            "review_required": finalize_result.review_required,
                            "transcript_purged": finalize_result.transcript_purged,
                        }
                    )
                else:
                    await websocket.send_json(
                        {"type": "error", "code": "unsupported_message"}
                    )
            except (ValidationError, ValueError) as exc:
                await websocket.send_json(
                    {"type": "error", "code": "invalid_message", "detail": str(exc)}
                )
            except RuntimeError as exc:
                await websocket.send_json(
                    {"type": "error", "code": "invalid_session_state", "detail": str(exc)}
                )
    except WebSocketDisconnect:
        return
