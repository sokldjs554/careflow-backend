"""CareFlow backend package.

The public demo is part of the portfolio contract, so startup performs a lightweight
source-level guard against accidental regressions in the product story and entry flow.
"""

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def assert_public_demo_source_contract() -> None:
    """Fail fast if the shipped demo loses its selected product-story contract."""
    main_source = (_PACKAGE_DIR / "main.py").read_text(encoding="utf-8")
    theme_css = (_PACKAGE_DIR / "static" / "theme.css").read_text(encoding="utf-8")
    detail_css = (_PACKAGE_DIR / "static" / "detail-polish.css").read_text(
        encoding="utf-8"
    )

    required_main = {
        "service-intro anchor": 'id="service-intro-section"',
        "service-intro navigation": 'document.querySelectorAll("[data-intro]")',
        "service-intro scroll": '"service-intro-section")?.scrollIntoView',
        "empty workspace entry": (
            "화면을 여는 것만으로는 세션이나 기록이 생성되지 않습니다."
        ),
        "explicit new-session control": 'id="workspace-new-session"',
        "non-automatic consultation entry": (
            '$("guided-demo").addEventListener("click",()=>{'
        ),
    }
    required_theme = {
        "selected D home": "selected D storytelling home",
        "D headline": "누군가의 마음이 조금 더 가벼워집니다.",
        "consultation CTA": "상담 시작하기  →",
        "service-intro CTA": "서비스 소개 보기",
    }
    required_detail = {
        "visible service intro": '#service-intro-section{display:block!important',
        "service intro headline": "상담에 집중하세요. 기록은 CareFlow가 연결합니다.",
        "visible workflow grid": (
            "#service-intro-section + .feature-grid{position:relative!important;"
            "z-index:9;display:grid!important"
        ),
        "workflow start": "상담을 시작합니다",
        "workflow capture": "대화를 흐름대로 기록합니다",
        "workflow evidence": "기록과 원문을 연결합니다",
        "workflow review": "확인이 필요하면 사람이 검토합니다",
        "product proof": "원문 발화 ↔ 근거 번호 ↔ S/O/P 기록 초안",
    }

    missing: list[str] = []
    for label, token in required_main.items():
        if token not in main_source:
            missing.append(label)
    for label, token in required_theme.items():
        if token not in theme_css:
            missing.append(label)
    for label, token in required_detail.items():
        if token not in detail_css:
            missing.append(label)

    if missing:
        raise RuntimeError(
            "CareFlow public demo source contract failed: " + ", ".join(missing)
        )


assert_public_demo_source_contract()
print("CareFlow public demo source contract verified", flush=True)
