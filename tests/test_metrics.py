from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import app


@pytest.fixture
def client_with_schema(test_session: AsyncSession) -> Iterator[TestClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        yield test_session

    app.dependency_overrides[get_db_session] = _override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_metrics_exposes_prometheus_text_format(client_with_schema: TestClient) -> None:
    response = client_with_schema.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "qurbot_quote_latency_seconds" in response.text
    assert "qurbot_match_method_total" in response.text
    assert "qurbot_llm_cost_usd_total" in response.text
    assert "qurbot_stale_price_offers" in response.text
