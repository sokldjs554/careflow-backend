"""Final live verifier aligned with the current CareFlow product shell."""

from __future__ import annotations

import json
from pathlib import Path

import deployment_smoke as smoke


def verify_current_product_shell() -> None:
    html = smoke.fetch_product_shell()
    Path("live-demo.html").write_text(html, encoding="utf-8")
    required = [
        "상담의 중요한 순간을,",
        "놓치지 않는 기록으로.",
        "상담 시작하기",
        "서비스 소개 보기",
        "service-intro-section",
        "상담 기록",
        "검토 대기",
        "검증 결과",
        "시스템 상태",
        "근거 연결 상태",
        "정확도 지표 아님",
        "데이터 보존 상태",
        "새 상담 시작",
        "발화 수집",
        "근거 연결",
        "기록 초안",
        "검토 / 삭제",
        "모델 선택 기록",
    ]
    missing = [token for token in required if token not in html]
    lowered = html.lower()
    exposed = [token for token in ("claude", "anthropic") if token in lowered]
    diagnostics = {
        "missing": missing,
        "forbidden_or_provider_copy": exposed,
        "html_length": len(html),
    }
    Path("deployment-smoke-diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if exposed:
        raise AssertionError(f"forbidden/provider-specific copy leaked into demo: {exposed}")
    if missing:
        raise AssertionError(f"missing product landmarks: {missing}")
    print("current product shell verified")


if __name__ == "__main__":
    smoke.verify_product_shell = verify_current_product_shell
    smoke.main()
