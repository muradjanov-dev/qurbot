"""Compare models on the jargon our customers actually wrote.

Not a leaderboard: the only question here is which model reads Uzbek
construction slang against *our* catalogue. Every query below was typed by a
real customer and failed to match -- pulled from the unmatched queue -- so the
set is exactly the work the model is hired for.

Half the cases expect no answer at all. A model that resolves "tosh" to some
plywood sheet is worse than one that says it does not know, and a benchmark
that only counts hits would rank the guesser first.

Usage:
    python -m scripts.eval_models                      # default candidates
    python -m scripts.eval_models gpt-5.6-luna gpt-5.6-sol
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401  -- registers the mappers
from app.db.base import Base
from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.llm.client import LLMClient
from app.services.catalog_service import CatalogService
from scripts.seed import seed_database

DEFAULT_CANDIDATES = ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.6-terra")


@dataclass(frozen=True)
class Case:
    """One real query and what a correct answer looks like.

    `expect` is a substring of the product name, because a catalogue name
    carries grade and size the query may not pin down: "03m" is right on any
    3 mm sheet. `expect=None` means the honest answer is no match at all.
    """

    query: str
    expect: str | None
    note: str = ""


CASES: tuple[Case, ...] = (
    # Misspellings of the one product we sell most of.
    Case("10 dona faner", "Fanera", "dropped vowel"),
    Case("20 dona paner", "Fanera", "p for f"),
    # "m" where the trade means "mm" -- six of these in the unmatched queue.
    Case("03m 10ta fanera", "3 mm", "m means mm"),
    Case("04m 50ta fanera", "4 mm", "m means mm"),
    Case("fanera 3m 2/4 10ta", "2x4", "slashed grade"),
    # Sizes written in metres, at every precision a customer uses.
    Case("Fanera 1.50x1.50 3mm 10 ta", "1525x1525", "rounded metres"),
    Case("Fanera 1.525x1.525 03mm 10ta", "1525x1525", "exact metres"),
    Case("Faner 15mm 1.22x2.44 - 20 ta", "2440x1220", "reversed metres"),
    Case("Faner 12mm 1.5x1.5 - 15 ta", "12 mm", "size and dash"),
    # A thickness that does not exist: 0.3 mm is a typo for 3 mm.
    Case("fanera berezovaya 2x4 0.3mm 20 ta", "3 mm", "decimal typo"),
    # Other sheet goods, abbreviated the way they are spoken.
    Case("Osb 15mm 25 ta", "OSB", "abbreviation"),
    Case("5 dona osb", "OSB", "no thickness"),
    Case("Dvp 3mm - 10 ta", "DVP", "abbreviation"),
    # Nothing in the catalogue answers these. Saying so is the right answer.
    Case("2 dona tosh", None, "not carried"),
    Case("Samarez 70 1kg", None, "not carried"),
    Case("Gipsokarton 15 mm oq 6 ta", None, "not carried"),
    Case("Emdef 16m 3 dona", None, "MDF, not carried"),
    Case("10 dona oboy", None, "not carried"),
)


async def _score(session: AsyncSession, model: str) -> tuple[int, int, list[str]]:
    """Run every case through one model. Returns (correct, wrong, notes)."""
    service = CatalogService(
        CatalogRepository(session),
        OpsRepository(session),
        # No session on the client: this must not write llm_calls rows or read
        # a cached answer from an earlier candidate.
        llm_client=LLMClient(model=model),
    )

    correct = 0
    wrong = 0
    misses: list[str] = []
    for case in CASES:
        results = await service.parse_and_match_basket(case.query, require_offers=True)
        decision = results[0][1] if results else None
        # Scored on what the customer is shown, not on how decisive the bot
        # was. "5 dona osb" names no thickness, so offering the OSB sheets and
        # asking is the right answer -- counting only resolved lines would mark
        # that a failure and reward a model that guesses a thickness instead.
        name = ""
        if decision is not None and decision.candidates:
            name = next(
                (c.name_uz for c in decision.candidates if c.canonical_id == decision.canonical_id),
                decision.candidates[0].name_uz,
            )

        ok = not name if case.expect is None else case.expect.lower() in name.lower()

        if ok:
            correct += 1
        else:
            wrong += 1
            misses.append(f"{case.query!r} -> {name or 'topilmadi'} (kutilgan: {case.expect})")
    return correct, wrong, misses


async def main(models: tuple[str, ...]) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        await seed_database(session, catalog_only=True)
        await session.commit()

        print(f"{len(CASES)} ta haqiqiy so'rov, {len(models)} ta model\n")
        for model in models:
            correct, wrong, misses = await _score(session, model)
            pct = correct / len(CASES) * 100
            print(f"{model:<18} {correct}/{len(CASES)}  ({pct:.0f}%)")
            for miss in misses:
                print(f"    x {miss}")
            print()

    await engine.dispose()


if __name__ == "__main__":
    chosen = tuple(sys.argv[1:]) or DEFAULT_CANDIDATES
    asyncio.run(main(chosen))
