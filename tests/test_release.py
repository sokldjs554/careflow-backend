from fastapi.testclient import TestClient


def test_release_exposes_only_deploy_commit(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")

    response = client.get("/v1/release")

    assert response.status_code == 200
    assert response.json() == {"commit": "abc123"}
