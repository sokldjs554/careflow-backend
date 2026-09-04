from app.services.note_generator import DeterministicDemoGenerator
from app.services.transcript_store import TranscriptChunk


async def test_plan_confirmation_phrase_is_not_reused_as_objective_evidence() -> None:
    generator = DeterministicDemoGenerator()
    chunks = [
        TranscriptChunk(
            sequence=1,
            speaker="patient",
            text="최근 일주일 동안 잠드는 데 한 시간쯤 걸렸습니다.",
        ),
        TranscriptChunk(
            sequence=2,
            speaker="patient",
            text="아침에 피곤해서 업무에 집중하기 어려웠습니다.",
        ),
        TranscriptChunk(
            sequence=3,
            speaker="clinician",
            text="대화 중 말투와 호흡은 차분하게 관찰되었습니다.",
        ),
        TranscriptChunk(
            sequence=4,
            speaker="clinician",
            text="다음 주에 수면 기록을 함께 확인할 계획입니다.",
        ),
    ]

    draft = await generator.generate(chunks)
    evidence = {item.section: item.source_sequences for item in draft.evidence}

    assert evidence == {
        "subjective": [1, 2],
        "objective": [3],
        "plan": [4],
    }
    assert "다음 주" not in draft.objective
    assert "다음 주" in draft.plan
