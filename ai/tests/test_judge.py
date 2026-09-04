from __future__ import annotations

from typing import Any

from ai.judge import anthropic_judge


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "stop_reason": "end_turn",
            "content": [
                {
                    "type": "text",
                    "text": (
                        '{"groundedness":5,"completeness":4,"safety":5,'
                        '"clarity":5,"reason":"합성 원문에 근거한 안전한 초안입니다."}'
                    ),
                }
            ],
        }


def test_anthropic_judge_uses_structured_output(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr("ai.judge.httpx.post", fake_post)

    result = anthropic_judge(
        api_key="test-key",
        source="잠드는 데 오래 걸렸다고 말했다.",
        candidate="잠드는 데 오래 걸린다고 진술했습니다.",
    )

    payload = captured["json"]
    assert "temperature" not in payload
    assert payload["output_config"]["effort"] == "low"
    assert payload["output_config"]["format"]["type"] == "json_schema"
    assert result["groundedness"] == 5
    assert result["safety"] == 5
