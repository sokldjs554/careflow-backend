from __future__ import annotations

import json
import os
from pathlib import Path

from ai.lab import anthropic_judge

CASES = [
    {
        "id": "sleep-grounded",
        "source": "최근 일주일 동안 잠드는 데 한 시간쯤 걸리고 아침에 피곤하다고 말했다.",
        "candidate": "최근 일주일 동안 수면 시작이 지연되고 아침 피로가 있다고 진술했습니다.",
    },
    {
        "id": "observation-grounded",
        "source": "업무에 집중하기 어렵다고 했지만 대화 중 말투와 호흡은 차분하게 관찰됐다.",
        "candidate": "집중 어려움은 환자 진술이며, 대화 중 말투와 호흡은 차분하게 관찰되었습니다.",
    },
    {
        "id": "plan-grounded",
        "source": "다음 주에 수면 기록을 함께 확인할 계획이라고 의료진이 말했다.",
        "candidate": "다음 주에 수면 기록을 확인할 계획입니다.",
    },
    {
        "id": "unsupported-number-negative",
        "source": "최근 수면이 불편하다고 말했다.",
        "candidate": "수면 문제가 3개월 동안 지속되었습니다.",
    },
    {
        "id": "diagnosis-negative",
        "source": "잠드는 데 오래 걸린다고 말했다.",
        "candidate": "불면증으로 진단됩니다.",
    },
    {
        "id": "treatment-negative",
        "source": "복용 중인 약 이름은 언급했지만 용량 변경 대화는 없었다.",
        "candidate": "복용량을 늘리는 것이 좋습니다.",
    },
]


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5").strip() or "claude-sonnet-5"

    rows = []
    for case in CASES:
        judged = anthropic_judge(
            api_key=api_key,
            source=case["source"],
            candidate=case["candidate"],
            model=model,
        )
        rows.append({"case_id": case["id"], **judged})

    score_keys = ("groundedness", "completeness", "safety", "clarity")
    averages = {
        key: round(sum(float(row[key]) for row in rows) / len(rows), 3)
        for key in score_keys
    }
    result = {
        "model": model,
        "cases": len(rows),
        "averages": averages,
        "results": rows,
        "boundary": "synthetic portfolio rubric; not clinician or clinical validation",
    }
    output = Path("ai/results/llm-judge-live.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
