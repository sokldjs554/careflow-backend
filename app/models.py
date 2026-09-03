from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionStatus(StrEnum):
    CREATED = "created"
    STREAMING = "streaming"
    PROCESSING = "processing"
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    PURGED = "purged"


class SessionRecord(Base):
    __tablename__ = "clinical_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default=SessionStatus.CREATED.value)
    language: Mapped[str] = mapped_column(String(8), default="ko")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    note: Mapped["NoteDraft | None"] = relationship(
        back_populates="session", cascade="all, delete-orphan", uselist=False
    )


class NoteDraft(Base):
    __tablename__ = "note_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_sessions.id", ondelete="CASCADE"), unique=True
    )
    subjective: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text)
    review_reasons_json: Mapped[str] = mapped_column(Text)
    generator_version: Mapped[str] = mapped_column(String(80))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    session: Mapped[SessionRecord] = relationship(back_populates="note")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
