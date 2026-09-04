from typing import cast

from fastapi import APIRouter, Header, Query, Request

from app.quality_report import QUALITY_REPORT
from app.schemas import (
    AuditEventResponse,
    CapabilitiesResponse,
    ChunkAck,
    CreateSessionRequest,
    FinalizeResponse,
    NoteDraftResponse,
    OperationsResponse,
    PurgeResponse,
    QualityReportResponse,
    ReviewDraftRequest,
    ReviewDraftResponse,
    SessionResponse,
    SessionSummaryResponse,
    TranscriptChunkInput,
    TranscriptResponse,
)
from app.services.session_service import SessionService
from app.services.speech_recognizer import SpeechRecognizer

router = APIRouter(prefix="/v1")


def _service(request: Request) -> SessionService:
    return cast(SessionService, request.app.state.session_service)


def _database_backend(url: str) -> str:
    if url.startswith("postgresql"):
        return "postgresql"
    if url.startswith("sqlite"):
        return "sqlite"
    return "other"


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities(request: Request) -> CapabilitiesResponse:
    service = _service(request)
    recognizer = cast(SpeechRecognizer | None, request.app.state.speech_recognizer)
    return CapabilitiesResponse(
        note_generator_version=service.note_generator.version,
        speech_enabled=recognizer is not None,
        speech_recognizer_version=recognizer.version if recognizer else None,
    )


@router.get("/operations", response_model=OperationsResponse)
async def get_operations(request: Request) -> OperationsResponse:
    service = _service(request)
    recognizer = cast(SpeechRecognizer | None, request.app.state.speech_recognizer)
    base = await service.operations(recognizer.version if recognizer else None)
    return base.model_copy(
        update={
            "environment": service.settings.environment,
            "database_backend": _database_backend(service.settings.database_url),
            "transcript_store_backend": "redis" if service.settings.redis_url else "memory",
            "note_generator_mode": service.settings.note_generator_mode,
            "speech_enabled": recognizer is not None,
        }
    )


@router.get("/quality", response_model=QualityReportResponse)
async def get_quality_report() -> QualityReportResponse:
    return QualityReportResponse.model_validate(QUALITY_REPORT)


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
) -> SessionResponse:
    return await _service(request).create_session(payload, idempotency_key)


@router.get("/sessions", response_model=list[SessionSummaryResponse])
async def list_sessions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[SessionSummaryResponse]:
    return await _service(request).list_sessions(limit)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, request: Request) -> SessionResponse:
    return await _service(request).get_session(session_id)


@router.get("/sessions/{session_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(session_id: str, request: Request) -> TranscriptResponse:
    return await _service(request).get_transcript(session_id)


@router.get("/sessions/{session_id}/audit", response_model=list[AuditEventResponse])
async def get_audit_events(
    session_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
) -> list[AuditEventResponse]:
    return await _service(request).list_audit_events(session_id, limit)


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


@router.patch("/sessions/{session_id}/draft", response_model=ReviewDraftResponse)
async def review_draft(
    session_id: str, payload: ReviewDraftRequest, request: Request
) -> ReviewDraftResponse:
    return await _service(request).review_draft(session_id, payload)


@router.delete("/sessions/{session_id}", response_model=PurgeResponse)
async def purge_session(session_id: str, request: Request) -> PurgeResponse:
    return await _service(request).purge(session_id)
