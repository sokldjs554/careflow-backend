import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_product_shell_allows_intended_human_review_copy() -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "deployment_smoke.py"))
    diagnostics = namespace["product_shell_diagnostics"]
    _, exposed = diagnostics("정확한 전사 · 근거 기반 요약 · 사람의 검토")
    assert exposed == []


def test_product_shell_still_rejects_provider_and_legacy_copy() -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "deployment_smoke.py"))
    diagnostics = namespace["product_shell_diagnostics"]
    _, exposed = diagnostics("Claude Anthropic 데모 체험하기")
    assert "claude" in exposed
    assert "anthropic" in exposed
    assert "데모 체험하기" in exposed


def test_live_scripts_expect_truthful_public_runtime() -> None:
    smoke = (ROOT / "scripts" / "deployment_smoke.py").read_text(encoding="utf-8")
    capture = (ROOT / "scripts" / "capture_live_demo.py").read_text(encoding="utf-8")
    for source in (smoke, capture):
        assert 'EXPECTED_DATABASE_BACKEND", "sqlite"' in source
        assert 'EXPECTED_TRANSCRIPT_STORE_BACKEND", "memory"' in source
    assert "Live demo is not using PostgreSQL" not in capture
    assert "Live demo is not using Redis" not in capture


def test_live_workflows_declare_public_runtime_contract() -> None:
    for path in (
        ROOT / ".github" / "workflows" / "deployment-smoke.yml",
        ROOT / ".github" / "workflows" / "demo-capture.yml",
    ):
        workflow = path.read_text(encoding="utf-8")
        assert "EXPECTED_DATABASE_BACKEND: sqlite" in workflow
        assert "EXPECTED_TRANSCRIPT_STORE_BACKEND: memory" in workflow
        assert "EXPECTED_ENVIRONMENT: render-demo" in workflow
        assert "EXPECTED_GIT_COMMIT: ${{ github.sha }}" in workflow
