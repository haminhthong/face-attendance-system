from fastapi.testclient import TestClient

from face_attendance.api import app


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
