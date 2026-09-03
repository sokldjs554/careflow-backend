from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import SessionStatus


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Speaker(StrEnum):
    CLINICIAN = "clinician"
    PATIENT = "patient"
    UNKNOWN = "unknown"


class ReviewReason(StrEnum):
    POTENTIAL_SAFETY_SIGNAL = "potential_safety_signal"
    EVIDENCE_GAP = "evidence_gap"
    SEQUENCE_GAP = "sequence_gap"
    GENERATION_FAILURE = "generation_failure"
    SCHEMA_VIOLATION = "schema_violation"


class CreateSessionRequest(StrictModel):
    language: str = Field(default="ko", pattern=r"^[a-z]{2}$")


class SessionResponse(StrictModel):
    session_id: str
    status: SessionStatus
    language: str
    expires_at: datetime
    websocket_path: str


class TranscriptChunkInput(StrictModel):
    sequence: int = Field(ge=1)
    speaker: Speaker = Speaker.UNKNOWN
    text: str = Field(min_length=1, max_length=2000)


class ChunkAck(StrictModel):
    session_id: str
    sequence: int
    duplicate: bool
    status: SessionStatus


class EvidenceSpan(StrictModel):
    section: Literal["subjective", "objective", "plan"]
    source_sequences: list[int] = Field(min_length=1)


class GeneratedDraft(StrictModel):
    subjective: str = Field(min_length=1, max_length=4000)
    objective: str = Field(min_length=1, max_length=4000)
    plan: str = Field(min_length=1, max_length=4000)
    evidence: list[EvidenceSpan]


class FinalizeResponse(StrictModel):
    session_id: str
    status: SessionStatus
    review_required: bool
    review_reasons: list[ReviewReason]
    transcript_purged: bool


class NoteDraftResponse(StrictModel):
    session_id: str
    status: SessionStatus
    subjective: str
    objective: str
    plan: str
    evidence: list[EvidenceSpan]
    review_required: bool
    review_reasons: list[ReviewReason]
    generator_version: str
    generated_at: datetime


class PurgeResponse(StrictModel):
    session_id: str
    status: SessionStatus
    transcript_purged: bool
    draft_purged: bool


class CapabilitiesResponse(StrictModel):
    note_generator_version: str
    speech_enabled: bool
    speech_recognizer_version: str | None


class WebSocketEnvelope(StrictModel):
    type: str
    sequence: int | None = None
    speaker: Speaker = Speaker.UNKNOWN
    text: str | None = None
    content_type: Literal[
        "audio/webm",
        "audio/mp4",
        "audio/ogg",
        "audio/wav",
        "audio/mpeg",
    ] | None = None
