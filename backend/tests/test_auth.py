"""Tests for the JWT authentication endpoints."""


class TestRegister:
    def test_register_success(self, client, user_payload):
        response = client.post("/api/v1/auth/register", json=user_payload)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert "id" in data
        assert "password" not in data and "hashed_password" not in data

    def test_register_duplicate_email(self, client, user_payload):
        client.post("/api/v1/auth/register", json=user_payload)
        response = client.post("/api/v1/auth/register", json=user_payload)
        assert response.status_code == 409

    def test_register_short_password(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"name": "X", "email": "x@example.com", "password": "short"},
        )
        assert response.status_code == 422

    def test_register_invalid_email(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"name": "X", "email": "not-an-email", "password": "longenough1"},
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_success(self, client, user_payload):
        client.post("/api/v1/auth/register", json=user_payload)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user_payload["email"], "password": user_payload["password"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "bearer"
        assert data["access_token"]
        assert data["expires_in"] > 0

    def test_login_wrong_password(self, client, user_payload):
        client.post("/api/v1/auth/register", json=user_payload)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user_payload["email"], "password": "wrong-password"},
        )
        assert response.status_code == 401

    def test_login_unknown_email(self, client):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "whatever123"},
        )
        assert response.status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client, auth_headers, user_payload):
        response = client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["email"] == user_payload["email"]

    def test_me_without_token(self, client):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_with_garbage_token(self, client):
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert response.status_code == 401


class TestProtectedEndpoints:
    """Cloud and file endpoints must require authentication."""

    @staticmethod
    def assert_requires_auth(client, method, url, **kwargs):
        response = getattr(client, method)(url, **kwargs)
        assert response.status_code == 401, f"{url} did not require auth"

    def test_cloud_endpoints_require_auth(self, client):
        self.assert_requires_auth(client, "get", "/api/v1/cloud/google/connect")
        self.assert_requires_auth(client, "get", "/api/v1/cloud/google/status")
        self.assert_requires_auth(client, "post", "/api/v1/cloud/s3/connect")
        self.assert_requires_auth(client, "get", "/api/v1/cloud/s3/status")

    def test_files_endpoints_require_auth(self, client):
        self.assert_requires_auth(client, "get", "/api/v1/files")
        self.assert_requires_auth(client, "get", "/api/v1/documents")
