from fastapi.testclient import TestClient


def test_product_demo_exposes_visible_workflow_controls(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text.lower()
    assert "전체 흐름 자동 시연" in response.text
    assert "data-scenario=\"normal\"" in response.text
    assert "data-scenario=\"safety_signal\"" in response.text
    assert "data-scenario=\"duplicate\"" in response.text
    assert "data lifecycle" in html
    assert "evidence coverage" in html
    assert "review queue" in html
    assert "ai quality" in html
    assert "assessment — blocked" in html
    assert "합성·비식별 데이터" in response.text
    assert "claude" not in html
    assert "anthropic" not in html


def test_product_demo_lifecycle_indices_match_visible_steps(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'status==="created"?0:status==="streaming"?1:status==="processing"?2:' in html
    assert 'status==="review_required"?3:null;' in html
    assert 'if(order!==null&&i===order)n.classList.add("current")' in html


def test_quality_report_preserves_adopt_and_reject_decisions(client: TestClient) -> None:
    response = client.get("/v1/quality")

    assert response.status_code == 200
    body = response.json()
    gates = {gate["key"]: gate for gate in body["gates"]}
    assert body["clinical_validation"] is False
    assert set(gates) == {"rag", "sft", "dpo", "judge", "multimodal"}
    assert gates["sft"]["status"] == "adopted"
    assert gates["sft"]["metrics"]["delta_reference_token_f1"] == 0.0596
    assert gates["dpo"]["status"] == "rejected"
    assert gates["dpo"]["metrics"]["delta_reference_token_f1"] == -0.0151
    assert gates["rag"]["status"] == "verified_not_adopted"


def test_operations_identifies_actual_test_backends(client: TestClient) -> None:
    response = client.get("/v1/operations")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "test"
    assert body["database_backend"] == "sqlite"
    assert body["transcript_store_backend"] == "memory"
    assert body["database_ready"] is True
    assert body["transcript_store_ready"] is True
    assert body["speech_enabled"] is False
