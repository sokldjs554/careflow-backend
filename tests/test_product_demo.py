from fastapi.testclient import TestClient


def test_product_demo_exposes_visible_workflow_controls(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text.lower()
    assert "데모 체험하기" in response.text
    assert "data-scenario=\"normal\"" in response.text
    assert "data-scenario=\"safety_signal\"" in response.text
    assert "data-scenario=\"duplicate\"" in response.text
    assert "data lifecycle" in html
    assert "근거 연결 상태" in response.text
    assert "review queue" in html
    assert "engineering" in html
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


def test_product_demo_shows_evidence_flow_and_section_coverage(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "01 · 발화 수집" in html
    assert "02 · Evidence map" in html
    assert "03 · S / O / P" in html
    assert "04 · Review / Purge" in html
    assert 'required=["subjective","objective","plan"]' in html
    assert "required.filter(section=>covered.has(section)).length}" in html
    assert "정확도 지표 아님" in html
    assert "`${state.lastCoverage}/3`" in html


def test_product_demo_shows_post_training_selection_path(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Model Evaluation" in response.text
    assert "Post-training selection path" in response.text
    assert "BASE" in response.text
    assert "SFT · ADOPTED" in response.text
    assert "DPO · REJECTED" in response.text
    assert "0.0648" in response.text
    assert "0.1244" in response.text
    assert "0.1093" in response.text


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
