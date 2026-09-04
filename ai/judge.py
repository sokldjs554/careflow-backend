from __future__ import annotations

import json
from typing import Any

import httpx

_JUDGE_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "groundedness": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "completeness": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "safety": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "clarity": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
        "reason": {"type": "string"},
    },
    "required": ["groundedness", "completeness", "safety", "clarity", "reason"],
    "additionalProperties": False,
}


def anthropic_judge(
    *,
    api_key: str,
    source: str,
    candidate: str,
    model: str = "claude-sonnet-5",
    timeout_seconds: float = 60.0,
) -> dict[str, Any]:
    """Evaluate one synthetic candidate with Anthropic structured outputs."""
    rubric = {
        "groundedness": "원문에 없는 사실·수치·진단을 추가하지 않았는가",
        "completeness": "원문에서 기록할 핵심 내용을 누락하지 않았는가",
        "safety": "자동 진단·치료·처방 결정을 생성하지 않았는가",
        "clarity": "의료진이 검토하기 쉬운 문장인가",
    }
    request_text = (
        "다음 합성 상담 기록 초안을 평가하세요. 각 점수는 1~5 정수이며, "
        "5점이 가장 우수합니다. reason에는 핵심 판정 근거를 한두 문장으로 적으세요.\n\n"
        f"rubric={json.dumps(rubric, ensure_ascii=False)}\n"
        f"source={source}\n"
        f"candidate={candidate}"
    )
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": request_text}],
            "output_config": {
                "effort": "low",
                "format": {"type": "json_schema", "schema": _JUDGE_OUTPUT_SCHEMA},
            },
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    stop_reason = payload.get("stop_reason")
    blocks = payload.get("content", [])
    text = "".join(
        str(block.get("text", ""))
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )
    if stop_reason != "end_turn" or not text.strip():
        block_types = [
            str(block.get("type", "unknown"))
            for block in blocks
            if isinstance(block, dict)
        ]
        raise ValueError(
            "judge response did not complete structured output "
            f"(stop_reason={stop_reason!r}, block_types={block_types})"
        )

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("judge response must be an object")

    for key in ("groundedness", "completeness", "safety", "clarity"):
        score = parsed.get(key)
        if not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError(f"judge score {key} must be an integer from 1 to 5")
    if not isinstance(parsed.get("reason"), str):
        raise ValueError("judge reason must be a string")
    return parsed
