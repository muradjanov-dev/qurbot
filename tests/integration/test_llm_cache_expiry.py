from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import LLMCall
from app.db.repositories.ops_repo import OpsRepository
from app.llm.client import LLMClient


async def test_cache_hits_do_not_extend_original_expiry(test_session: AsyncSession) -> None:
    client = LLMClient(session=test_session, model="gpt-5.6-luna")
    call = await OpsRepository(test_session).record_llm_call(
        "batch_disambiguation",
        "matching-v2",
        "expiry-test",
        1,
        1,
        Decimal(0),
        1,
        raw_response='{"lines":[]}',
        model=client.model,
        outcome="success",
        attempt_count=1,
    )
    assert await client._get_cached_call("expiry-test") is not None
    await test_session.execute(
        update(LLMCall)
        .where(LLMCall.id == call.id)
        .values(created_at=datetime.now(UTC) - timedelta(hours=25))
    )
    assert await client._get_cached_call("expiry-test") is None
    assert (
        await LLMClient(session=test_session, model="gpt-5.6-terra")._get_cached_call("expiry-test")
        is None
    )
