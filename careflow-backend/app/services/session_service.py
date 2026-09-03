import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.config import Settings
from app.database import Database
from app.models import AuditEvent, IdempotencyRecord, NoteDraft, SessionRecord, SessionStatus
from app.schemas import (
    ChunkAck,
    CreateSessionRequest,
    EvidenceSpan,
    FinalizeResponse,
    NoteDraftResponse,
    PurgeResponse,
    ReviewReason,
    SessionResponse,
    TranscriptChunkInput,
)
from app.services.note_generator import DraftGenerationError, NoteGenerator
from app.services.safety import evaluate_for_review
from app.services.transcript_store import TranscriptChunk, TranscriptStore


class SessionNotFoundError(LookupError):
    pass


class SessionStateError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


@dataclass(slots=True)
class SessionService:
    settings: Settings
    database: Database
    transcript_store: TranscriptStore
    note_generator: NoteGenerator

    async def create_session(
        self, request: CreateSessionRequest, idempotency_key: str | None
    ) -> SessionResponse:
        now = datetime.now(UTC)
        request_hash = self._hash_json(request.model_dump())
        async with self.database.session() as db:
            if idempotency_key:
                existing = await db.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.idempotency_key == idempotency_key
                    )
                )
                if existing:
                    if existing.request_hash != request_hash:
                        raise IdempotencyConflictError(
                            "Idempotency-Key was already used with a different request"
                        )
                    record = await db.get(SessionRecord, existing.session_id)
                    if record is None:
                        raise SessionNotFoundError(existing.session_id)
                    return self._session_response(record)

            record = SessionRecord(
                id=str(uuid4()),
                status=SessionStatus.CREATED.value,
                language=request.language,
                created_at=now,
                updated_at=now,
                expires_at=now + timedelta(seconds=self.settings.transcript_ttl_seconds),
            )
            db.add(record)
            if idempotency_key:
                db.add(
                    IdempotencyRecord(
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        session_id=record.id,
                        created_at=now,
                    )
                )
            self._audit(db, record.id, "session.created", request_hash)
            await db.commit()
            return self._session_response(record)

    async def get_session(self, session_id: str) -> SessionResponse:
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            return self._session_response(record)

    async def append_chunk(self, session_id: str, item: TranscriptChunkInput) -> ChunkAck:
        if len(item.text) > self.settings.max_chunk_chars:
            raise SessionStateError("Transcript chunk exceeds configured limit")
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            if record.status in {
                SessionStatus.PROCESSING.value,
                SessionStatus.READY.value,
                SessionStatus.REVIEW_REQUIRED.value,
                SessionStatus.PURGED.value,
            }:
                raise SessionStateError(f"Cannot append transcript in state: {record.status}")

            now = datetime.now(UTC)
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                raise SessionStateError("Session transcript window has expired")

            duplicate = await self.transcript_store.append(
                session_id,
                TranscriptChunk(
                    sequence=item.sequence, speaker=item.speaker.value, text=item.text.strip()
                ),
                self.settings.transcript_ttl_seconds,
            )
            record.status = SessionStatus.STREAMING.value
            record.updated_at = now
            record.expires_at = now + timedelta(seconds=self.settings.transcript_ttl_seconds)
            self._audit(
                db,
                session_id,
                "transcript.duplicate" if duplicate else "transcript.accepted",
                hashlib.sha256(item.text.encode("utf-8")).hexdigest(),
            )
            await db.commit()
            return ChunkAck(
                session_id=session_id,
                sequence=item.sequence,
                duplicate=duplicate,
                status=SessionStatus.STREAMING,
            )

    async def finalize(self, session_id: str) -> FinalizeResponse:
        chunks: list[TranscriptChunk]
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            if record.status == SessionStatus.PURGED.value:
                raise SessionStateError("Session has been purged")
            if record.status == SessionStatus.PROCESSING.value:
                raise SessionStateError("Session finalization is already in progress")
            if record.status in {
                SessionStatus.READY.value,
                SessionStatus.REVIEW_REQUIRED.value,
            }:
                note = await db.scalar(select(NoteDraft).where(NoteDraft.session_id == session_id))
                existing_reasons = self._decode_reasons(note.review_reasons_json if note else "[]")
                chunks = await self.transcript_store.list_chunks(session_id)
                retryable_failure = ReviewReason.GENERATION_FAILURE in existing_reasons and chunks
                if not retryable_failure:
                    return FinalizeResponse(
                        session_id=session_id,
                        status=SessionStatus(record.status),
                        review_required=bool(existing_reasons),
                        review_reasons=existing_reasons,
                        transcript_purged=not chunks,
                    )
                if note is not None:
                    await db.delete(note)
                record.status = SessionStatus.PROCESSING.value
                record.updated_at = datetime.now(UTC)
                self._audit(
                    db,
                    session_id,
                    "session.retry_started",
                    self._hash_json({"reason": ReviewReason.GENERATION_FAILURE}),
                )
                await db.commit()
            else:
                chunks = await self.transcript_store.list_chunks(session_id)
                if not chunks:
                    raise SessionStateError("No transcript chunks are available")
                record.status = SessionStatus.PROCESSING.value
                record.updated_at = datetime.now(UTC)
                await db.commit()

        reasons: list[ReviewReason]
        try:
            draft = await self.note_generator.generate(chunks)
            reasons = evaluate_for_review(chunks, draft)
        except DraftGenerationError:
            from app.schemas import GeneratedDraft

            draft = GeneratedDraft(
                subjective="자동 초안 생성에 실패했습니다.",
                objective="담당자 검토가 필요합니다.",
                plan="원문 보존기간 내 재처리 여부를 결정해야 합니다.",
                evidence=[],
            )
            reasons = [ReviewReason.GENERATION_FAILURE]

        purge_after_finalize = ReviewReason.GENERATION_FAILURE not in reasons
        purged = await self.transcript_store.purge(session_id) if purge_after_finalize else False
        now = datetime.now(UTC)
        status = SessionStatus.REVIEW_REQUIRED if reasons else SessionStatus.READY
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            existing = await db.scalar(select(NoteDraft).where(NoteDraft.session_id == session_id))
            if existing is None:
                db.add(
                    NoteDraft(
                        session_id=session_id,
                        subjective=draft.subjective,
                        objective=draft.objective,
                        plan=draft.plan,
                        evidence_json=json.dumps(
                            [item.model_dump() for item in draft.evidence], ensure_ascii=False
                        ),
                        review_reasons_json=json.dumps([reason.value for reason in reasons]),
                        generator_version=self.note_generator.version,
                        generated_at=now,
                    )
                )
            record.status = status.value
            record.updated_at = now
            self._audit(db, session_id, "session.finalized", self._hash_json({"status": status}))
            if purged:
                self._audit(db, session_id, "transcript.purged", self._hash_json({"ok": True}))
            await db.commit()

        return FinalizeResponse(
            session_id=session_id,
            status=status,
            review_required=bool(reasons),
            review_reasons=reasons,
            transcript_purged=purged,
        )

    async def get_draft(self, session_id: str) -> NoteDraftResponse:
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            note = await db.scalar(select(NoteDraft).where(NoteDraft.session_id == session_id))
            if note is None:
                raise SessionStateError("Draft is not available")
            reasons = self._decode_reasons(note.review_reasons_json)
            return NoteDraftResponse(
                session_id=session_id,
                status=SessionStatus(record.status),
                subjective=note.subjective,
                objective=note.objective,
                plan=note.plan,
                evidence=[
                    EvidenceSpan.model_validate(item) for item in json.loads(note.evidence_json)
                ],
                review_required=bool(reasons),
                review_reasons=reasons,
                generator_version=note.generator_version,
                generated_at=note.generated_at,
            )

    async def purge(self, session_id: str) -> PurgeResponse:
        transcript_purged = await self.transcript_store.purge(session_id)
        async with self.database.session() as db:
            record = await db.get(SessionRecord, session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            existing_note = await db.scalar(
                select(NoteDraft).where(NoteDraft.session_id == session_id)
            )
            if existing_note is not None:
                await db.delete(existing_note)
            record.status = SessionStatus.PURGED.value
            record.updated_at = datetime.now(UTC)
            self._audit(db, session_id, "session.purged", self._hash_json({"ok": True}))
            await db.commit()
            return PurgeResponse(
                session_id=session_id,
                status=SessionStatus.PURGED,
                transcript_purged=transcript_purged,
                draft_purged=existing_note is not None,
            )

    @staticmethod
    def _session_response(record: SessionRecord) -> SessionResponse:
        return SessionResponse(
            session_id=record.id,
            status=SessionStatus(record.status),
            language=record.language,
            expires_at=record.expires_at,
            websocket_path=f"/v1/ws/sessions/{record.id}",
        )

    @staticmethod
    def _decode_reasons(value: str) -> list[ReviewReason]:
        return [ReviewReason(item) for item in json.loads(value)]

    @staticmethod
    def _hash_json(value: object) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _audit(db: object, session_id: str, event_type: str, payload_hash: str) -> None:
        db.add(  # type: ignore[attr-defined]
            AuditEvent(
                session_id=session_id,
                event_type=event_type,
                payload_hash=payload_hash,
                created_at=datetime.now(UTC),
            )
        )
