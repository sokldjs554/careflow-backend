import pytest
from pydantic import ValidationError

from app.schemas import GeneratedDraft


def test_generated_draft_rejects_assessment_field() -> None:
    with pytest.raises(ValidationError):
        GeneratedDraft.model_validate(
            {
                "subjective": "주관적 진술",
                "objective": "객관적 관찰",
                "assessment": "자동 진단은 금지",
                "plan": "담당자 계획",
                "evidence": [],
            }
        )
