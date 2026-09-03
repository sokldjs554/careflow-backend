from app.schemas import GeneratedDraft, ReviewReason
from app.services.transcript_store import TranscriptChunk

SAFETY_TOKENS = (
    "죽고 싶",
    "자살",
    "자해",
    "해치고 싶",
    "살고 싶지",
)


def evaluate_for_review(chunks: list[TranscriptChunk], draft: GeneratedDraft) -> list[ReviewReason]:
    reasons: list[ReviewReason] = []
    combined = " ".join(chunk.text for chunk in chunks)
    if any(token in combined for token in SAFETY_TOKENS):
        reasons.append(ReviewReason.POTENTIAL_SAFETY_SIGNAL)

    sequences = sorted(chunk.sequence for chunk in chunks)
    if sequences and sequences != list(range(sequences[0], sequences[-1] + 1)):
        reasons.append(ReviewReason.SEQUENCE_GAP)

    covered_sections = {item.section for item in draft.evidence}
    if {"subjective", "objective", "plan"} - covered_sections:
        reasons.append(ReviewReason.EVIDENCE_GAP)

    source_sequences = {chunk.sequence for chunk in chunks}
    if any(not set(item.source_sequences) <= source_sequences for item in draft.evidence):
        reasons.append(ReviewReason.SCHEMA_VIOLATION)
    return list(dict.fromkeys(reasons))
