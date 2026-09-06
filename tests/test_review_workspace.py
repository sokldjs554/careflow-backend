from fastapi.testclient import TestClient


def _append_review_transcript(client: TestClient, session_id: str) -> None:
    chunks = [
        {
            "sequence": 1,
            "speaker": "patient",
            "text": "요즘 죽고 싶다는 생각이 들 때가 있습니다.",
        },
        {
            "sequence": 2,
            "speaker": "clinician",
            "text": "대화 중 말투가 느린 것을 관찰했습니다.",
        },
        {
            "sequence": 3,
            "speaker": "clinician",
            "text": "즉시 담당자가 검토하고 다음 계획을 정합니다.",
        },
    ]
    for chunk in chunks:
        response = client.post(f"/v1/sessions/{session_id}/chunks", json=chunk)
        assert response.status_code == 200


def test_review_required_retains_transcript_until_human_approval(
    client: TestClient, session_id: str
) -> None:
    _append_review_transcript(client, session_id)

    finalized = client.post(f"/v1/sessions/{session_id}/finalize")
    transcript = client.get(f"/v1/sessions/{session_id}/transcript")
    draft = client.get(f"/v1/sessions/{session_id}/draft").json()

    assert finalized.status_code == 200
    assert finalized.json()["status"] == "review_required"
    assert finalized.json()["transcript_purged"] is False
    assert transcript.status_code == 200
    assert transcript.json()["transcript_available"] is True
    assert [item["sequence"] for item in transcript.json()["chunks"]] == [1, 2, 3]

    reviewed = client.patch(
        f"/v1/sessions/{session_id}/draft",
        json={
            "subjective": draft["subjective"],
            "objective": draft["objective"],
            "plan": draft["plan"],
            "action": "approve",
        },
    )

    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "ready"
    assert reviewed.json()["review_required"] is False
    assert reviewed.json()["transcript_purged"] is True
    assert client.get(f"/v1/sessions/{session_id}/transcript").json()["chunks"] == []


def test_review_save_keeps_queue_and_records_audit(
    client: TestClient, session_id: str
) -> None:
    _append_review_transcript(client, session_id)
    client.post(f"/v1/sessions/{session_id}/finalize")
    draft = client.get(f"/v1/sessions/{session_id}/draft").json()

    saved = client.patch(
        f"/v1/sessions/{session_id}/draft",
        json={
            "subjective": draft["subjective"] + " 검토자가 문구를 정리했습니다.",
            "objective": draft["objective"],
            "plan": draft["plan"],
            "action": "save",
        },
    )
    audit = client.get(f"/v1/sessions/{session_id}/audit").json()

    assert saved.status_code == 200
    assert saved.json()["status"] == "review_required"
    assert saved.json()["review_required"] is True
    assert saved.json()["transcript_purged"] is False
    assert any(item["event_type"] == "note.review_saved" for item in audit)


def test_session_dashboard_and_operations_endpoints(
    client: TestClient, session_id: str
) -> None:
    sessions = client.get("/v1/sessions")
    operations = client.get("/v1/operations")

    assert sessions.status_code == 200
    assert sessions.json()[0]["session_id"] == session_id
    assert sessions.json()[0]["status"] == "created"
    assert sessions.json()[0]["has_draft"] is False

    assert operations.status_code == 200
    body = operations.json()
    assert body["database_ready"] is True
    assert body["transcript_store_ready"] is True
    assert body["total_sessions"] == 1
    assert body["session_counts"]["created"] == 1
    assert body["review_queue"] == 0
    assert body["transcript_ttl_seconds"] == 300


def test_demo_clears_browser_transcript_after_server_purge(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert (
        "if(result.transcript_purged){state.transcript=[];renderTranscript()}"
        in response.text
    )


def test_demo_uses_product_copy_and_non_accuracy_evidence_status(
    client: TestClient,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "상담의 중요한 순간을,<br>놓치지 않는 기록으로." in response.text
    assert "근거 연결 상태" in response.text
    assert "S/O/P 필수 섹션 · 정확도 지표 아님" in response.text
    assert "`${state.lastCoverage}/3`" in response.text
    assert "`${state.lastCoverage}%`" not in response.text


def test_demo_polishes_entry_navigation_and_workspace_details(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert '<body data-view="overview">' in response.text
    assert 'data-intro="features"' in response.text
    assert 'id="service-intro-section"' in response.text
    assert 'id="workspace-new-session"' in response.text
    assert "화면을 여는 것만으로는 세션이나 기록이 생성되지 않습니다." in response.text
    assert (
        '$("guided-demo").addEventListener("click",()=>{switchView("console")'
        in response.text
    )
    assert (
        '$("guided-demo").addEventListener("click",()=>runScenario("normal",true))'
        not in response.text
    )
    assert "workspace-detail-polish-v3" in response.text
    assert "background:#f4f6f3!important" in response.text


def test_service_intro_is_a_real_product_story_not_an_anchor(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    for copy in (
        "상담에 집중하세요. 기록은 CareFlow가 연결합니다.",
        "상담 중 기록 때문에 대화의 흐름을 끊지 않도록",
        "상담 시작부터 검토·삭제까지 하나의 흐름으로",
        "상담을 시작합니다",
        "대화를 흐름대로 기록합니다",
        "기록과 원문을 연결합니다",
        "확인이 필요하면 사람이 검토합니다",
        "원문 발화 ↔ 근거 번호 ↔ S/O/P 기록 초안",
    ):
        assert copy in response.text
    assert "#service-intro-section{display:block!important" in response.text
    assert "#service-intro-section p{display:block!important" in response.text
    assert "#service-intro-section p { display: none" not in response.text


def test_demo_uses_product_facing_feature_and_validation_copy(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "상담을 시작합니다" in response.text
    assert "대화를 흐름대로 기록합니다" in response.text
    assert "기록과 원문을 연결합니다" in response.text
    assert "확인이 필요하면 사람이 검토합니다" in response.text
    assert ">검증 결과</button>" in response.text
    assert ">AI Quality</button>" not in response.text
    assert "기술 이름을 나열하기보다 실제 선택과 회귀 판단만 보여줍니다." in response.text
    assert "검색 품질 비교" in response.text
    assert "요약 품질 개선안" in response.text
    assert "selected D storytelling home" in response.text
    assert "누군가의 마음이 조금 더 가벼워집니다." in response.text
    assert "data:image/webp;base64" in response.text
