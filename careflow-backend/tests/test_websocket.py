from fastapi.testclient import TestClient


def test_websocket_stream_ack_duplicate_and_finalize(client: TestClient, session_id: str) -> None:
    with client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
        message = {
            "type": "transcript.chunk",
            "sequence": 1,
            "speaker": "patient",
            "text": "최근 수면이 불규칙합니다.",
        }
        websocket.send_json(message)
        first = websocket.receive_json()
        websocket.send_json(message)
        duplicate = websocket.receive_json()

        websocket.send_json(
            {
                "type": "transcript.chunk",
                "sequence": 2,
                "speaker": "clinician",
                "text": "표정이 차분한 것을 관찰했습니다.",
            }
        )
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "transcript.chunk",
                "sequence": 3,
                "speaker": "clinician",
                "text": "다음 주 상태를 추적할 계획입니다.",
            }
        )
        websocket.receive_json()
        websocket.send_json({"type": "session.finalize"})
        finalized = websocket.receive_json()

    assert first == {"type": "transcript.ack", "sequence": 1, "duplicate": False}
    assert duplicate == {"type": "transcript.ack", "sequence": 1, "duplicate": True}
    assert finalized["type"] == "session.finalized"
    assert finalized["status"] == "ready"
    assert finalized["transcript_purged"] is True


def test_websocket_rejects_unknown_message(client: TestClient, session_id: str) -> None:
    with client.websocket_connect(f"/v1/ws/sessions/{session_id}") as websocket:
        websocket.send_json({"type": "unknown"})
        response = websocket.receive_json()
    assert response["code"] == "unsupported_message"
