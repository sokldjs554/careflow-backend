from fastapi.testclient import TestClient


def test_product_demo_exposes_visible_workflow_controls(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    html = response.text.lower()
    assert "상담 화면 열기" in response.text
    assert "서비스 소개 보기" in response.text
    assert 'data-intro="features"' in response.text
    assert 'data-scenario="normal"' in response.text
    assert 'data-scenario="safety_signal"' in response.text
    assert 'data-scenario="duplicate"' in response.text
    assert "데이터 보존 상태" in response.text
    assert "근거 연결 상태" in response.text
    assert "검토 대기" in response.text
    assert "검증 결과" in response.text
    assert "assessment — 생성 차단" in html
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
    assert "02 · 근거 연결" in html
    assert "03 · 기록 초안" in html
    assert "04 · 검토 / 삭제" in html
    assert 'required=["subjective","objective","plan"]' in html
    assert "required.filter(section=>covered.has(section)).length}" in html
    assert "정확도 지표 아님" in html
    assert "`${state.lastCoverage}/3`" in html


def test_product_demo_shows_decision_focused_model_validation(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "검증 결과" in response.text
    assert "모델 선택 기록" in response.text
    assert "기준 모델" in response.text
    assert "개선안 · 채택" in response.text
    assert "추가 후보 · 미채택" in response.text
    assert "0.0648" in response.text
    assert "0.1244" in response.text
    assert "0.1093" in response.text
    assert "검색 품질 비교" in response.text
    assert "요약 품질 개선안" in response.text


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
