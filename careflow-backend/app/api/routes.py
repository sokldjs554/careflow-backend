from typing import cast

from fastapi import APIRouter, Header, Request

from app.schemas import (
    CapabilitiesResponse,
    ChunkAck,
    CreateSessionRequest,
    FinalizeResponse,
    NoteDraftResponse,
    PurgeResponse,
    SessionResponse,
    TranscriptChunkInput,
)
from app.services.session_service import SessionService
from app.services.speech_recognizer import SpeechRecognizer

router = APIRouter(prefix="/v1")


def _service(request: Request) -> SessionService:
    return cast(SessionService, request.app.state.session_service)


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(request: Request) -> CapabilitiesResponse:
    service = _service(request)
    recognizer = cast(SpeechRecognizer | None, request.app.state.speech_recognizer)
    return CapabilitiesResponse(
        note_generator_version=service.note_generator.version,
        speech_enabled=recognizer is not None,
        speech_recognizer_version=recognizer.version if recognizer else None,
    )


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
) -> SessionResponse:
    return await _service(request).create_session(payload, idempotency_key)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    return await _service(request).get_session(session_id)


@router.post("/sessions/{session_id}/chunks", response_model=ChunkAck)
async def append_chunk(
    session_id: str, payload: TranscriptChunkInput, request: Request
) -> ChunkAck:
    return await _service(request).append_chunk(session_id, payload)


@router.post("/sessions/{session_id}/finalize", response_model=FinalizeResponse)
async def finalize_session(session_id: str, request: Request) -> FinalizeResponse:
    return await _service(request).finalize(session_id)


@router.get("/sessions/{session_id}/draft", response_model=NoteDraftResponse)
async def get_draft(session_id: str, request: Request) -> NoteDraftResponse:
    return await _service(request).get_draft(session_id)


@router.delete("/sessions/{session_id}", response_model=PurgeResponse)
async def purge_session(session_id: str, request: Request) -> PurgeResponse:
    return await _service(request).purge(session_id)
