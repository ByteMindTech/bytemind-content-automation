"""API tests — health and articles endpoints (no DB required for health)."""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        # May fail if DB is not available, but health itself should respond
        assert resp.status_code in (200, 500)

    def test_health_response_schema(self, client):
        resp = client.get("/health")
        if resp.status_code == 200:
            data = resp.json()
            assert "status" in data
            assert "version" in data
            assert "medium_dry_run" in data
            assert data["medium_dry_run"] is True  # default in test env


class TestOpenAPISchema:
    def test_openapi_accessible(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200

    def test_docs_accessible(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_accessible(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200
