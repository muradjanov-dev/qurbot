import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.catalog_repo import CatalogRepository
from app.db.repositories.ops_repo import OpsRepository
from app.services.catalog_service import CatalogService
from scripts.seed import seed_database

# Sheet goods written the way customers actually type them: mixed Latin and
# Cyrillic, thickness with and without a space, grades, plant names, and the
# product named either by material or by the price list's own wording.
SPEC_FIXTURES_BASKET = """
10 dona fanera 12mm
fanera 3x3 15mm 5 dona
osb 9mm 20 dona
osb-3 12мм 15 dona
двп 3.2 30 dona
фанера березовая 18 мм 4 dona
dsp kronospan 2 dona
laminat fanera segezha 18 5 dona
hdf 3.2 10 dona
фанера 2x4 4мм 6 dona
osb 18mm 8 dona
fanera 21mm 3 dona
дсп пермь 1 dona
"""


@pytest.mark.asyncio
async def test_matching_pipeline_against_seeded_catalog(test_session: AsyncSession) -> None:
    # 1. Seed database with catalog, aliases, and units
    await seed_database(test_session)

    # 2. Setup service layer
    catalog_repo = CatalogRepository(test_session)
    ops_repo = OpsRepository(test_session)
    catalog_service = CatalogService(catalog_repo, ops_repo)

    # 3. Parse and match all fixtures
    results = await catalog_service.parse_and_match_basket(SPEC_FIXTURES_BASKET)
    total_lines = len(results)
    assert total_lines > 0, "Fixtures must produce parsed lines"

    auto_matched = 0
    table_rows = []

    for parsed_line, decision in results:
        is_auto = decision.status == "auto_accept" and decision.canonical_id is not None
        if is_auto:
            auto_matched += 1

        cand_name = decision.candidates[0].name_uz if decision.candidates else "None"
        row_str = (
            f"| {parsed_line.line_no:<2} "
            f"| {parsed_line.raw_text[:24]:<24} "
            f"| {str(parsed_line.qty):<5} "
            f"| {str(parsed_line.unit_code):<5} "
            f"| {decision.status:<11} "
            f"| {decision.confidence:<4.2f} "
            f"| {decision.method:<5} "
            f"| {cand_name[:28]:<28} |"
        )
        table_rows.append(row_str)

    match_rate = (auto_matched / total_lines) * 100.0

    # Print ASCII match-rate table report
    sep = "-" * 100
    header = (
        f"\n{sep}\n"
        "| #  | Input Raw Line           | Qty   | Unit  | Status      | "
        "Conf | Meth  | Matched SKU                  |\n"
        f"{sep}"
    )
    rows_str = "\n".join(table_rows)
    footer = (
        f"{sep}\n"
        f"TOTAL: {total_lines} | AUTO-ACCEPTED: {auto_matched} | RATE: {match_rate:.1f}%\n"
        f"{sep}\n"
    )
    report = f"{header}\n{rows_str}\n{footer}"
    try:
        print(report)
    except UnicodeEncodeError:
        print(report.encode("ascii", "replace").decode("ascii"))

    # Assert SPEC §15 requirement: ≥ 85% of lines auto-match correctly
    assert match_rate >= 85.0, f"Match rate {match_rate:.1f}% is below target 85.0% threshold"
