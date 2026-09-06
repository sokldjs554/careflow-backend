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


def test_demo_separates_product_and_engineering_navigation(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert '<body data-view="overview">' in response.text
    assert ">Engineering</button>" in response.text
    assert ">AI Quality</button>" not in response.text
    assert "Model Evaluation" in response.text
    assert "selected D storytelling home" in response.text
    assert "누군가의 마음이 조금 더 가벼워집니다." in response.text
    assert "data:image/webp;base64" in response.text
