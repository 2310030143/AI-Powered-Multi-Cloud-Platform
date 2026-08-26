from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)


def test_health_check_db_ok():
    mock_db = MagicMock()
    with patch("app.api.v1.endpoints.health.get_db", return_value=iter([mock_db])):
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "database" in data
