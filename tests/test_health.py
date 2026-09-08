from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_health_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_requires_database_and_redis() -> None:
    with (
        patch("app.api.routers.health.check_database", new=AsyncMock(return_value=True)),
        patch("app.api.routers.health.check_redis", new=AsyncMock(return_value=True)),
        TestClient(app) as client,
    ):
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": True, "redis": True},
    }


def test_readiness_fails_when_a_dependency_is_down() -> None:
    with (
        patch("app.api.routers.health.check_database", new=AsyncMock(return_value=True)),
        patch("app.api.routers.health.check_redis", new=AsyncMock(return_value=False)),
        TestClient(app) as client,
    ):
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": True, "redis": False},
    }
