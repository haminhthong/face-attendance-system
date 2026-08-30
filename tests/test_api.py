from fastapi.testclient import TestClient

from face_attendance import api

app = api.app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_attendance_write_is_disabled_without_api_key() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/attendance",
            json={"session_id": 1, "student_id": 1, "recognition_distance": 0.4},
        )
    assert response.status_code == 503


def test_sessions_requires_valid_api_key(monkeypatch) -> None:
    monkeypatch.setattr(api, "API_KEY", "secret-key")
    with TestClient(app) as client:
        unauthorized = client.get("/sessions")
        authorized = client.get(
            "/sessions", headers={"X-API-Key": "secret-key"}
        )
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
