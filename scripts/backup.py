"""Dump the QurBot database to a timestamped local file (Phase 9 hardening).

Requires the `pg_dump` CLI (from the same major version as the target Postgres)
on PATH. Uses DATABASE_URL from settings, converted from the app's
`postgresql+asyncpg://` scheme to the plain `postgresql://` scheme pg_dump expects.

Usage: python -m scripts.backup [output_dir]
"""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings


def to_pg_dump_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backups")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"qurbot_{timestamp}.dump"

    pg_url = to_pg_dump_url(settings.database_url)
    subprocess.run(
        ["pg_dump", "--format=custom", f"--file={output_path}", pg_url],
        check=True,
    )
    print(f"Backup written to {output_path}")


if __name__ == "__main__":
    main()
