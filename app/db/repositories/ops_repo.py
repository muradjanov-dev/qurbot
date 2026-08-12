from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import Event, LLMCall, UnmatchedQuery
from app.db.repositories.base import BaseRepository


class OpsRepository(BaseRepository[UnmatchedQuery]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(UnmatchedQuery, session)

    async def record_unmatched_query(
        self,
        raw_text: str,
        normalized: str,
        user_id: int | None = None,
        suggested_canonical_id: int | None = None,
    ) -> UnmatchedQuery:
        stmt = select(UnmatchedQuery).where(UnmatchedQuery.normalized == normalized)
        result = await self.session.execute(stmt)
        record = result.scalars().first()

        if record:
            record.occurrences += 1
            if suggested_canonical_id and not record.suggested_canonical_id:
                record.suggested_canonical_id = suggested_canonical_id
            await self.session.flush()
            return record

        record = UnmatchedQuery(
            raw_text=raw_text,
            normalized=normalized,
            user_id=user_id,
            occurrences=1,
            suggested_canonical_id=suggested_canonical_id,
            status="new",
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def record_llm_call(
        self,
        purpose: str,
        prompt_version: str,
        input_hash: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: Decimal,
        latency_ms: int,
        cache_hit: bool = False,
        raw_response: str | None = None,
    ) -> LLMCall:
        call = LLMCall(
            purpose=purpose,
            prompt_version=prompt_version,
            input_hash=input_hash,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            raw_response=raw_response,
        )
        self.session.add(call)
        await self.session.flush()
        return call

    async def log_event(
        self,
        name: str,
        user_id: int | None = None,
        props: dict[str, Any] | None = None,
    ) -> Event:
        event = Event(
            name=name,
            user_id=user_id,
            props=props or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event
