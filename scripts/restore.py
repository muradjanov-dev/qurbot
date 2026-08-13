"""Restore the QurBot database from a backup file (Phase 9 hardening).

DESTRUCTIVE: drops and recreates data in the target database. Requires
`pg_restore` on PATH and an explicit --yes flag -- refuses to run otherwise.

Usage: python -m scripts.restore <dump_file> --yes
"""

import argparse
import subprocess
import sys

from app.core.config import settings
from scripts.backup import to_pg_dump_url


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump_file", help="Path to a .dump file produced by scripts/backup.py")
    parser.add_argument(
        "--yes", action="store_true", help="Required: confirms you want to overwrite the DB"
    )
    args = parser.parse_args()

    if not args.yes:
        print(
            "Refusing to restore without --yes -- this overwrites the target database "
            f"({settings.database_url.split('@')[-1]}).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    pg_url = to_pg_dump_url(settings.database_url)
    subprocess.run(
        ["pg_restore", "--clean", "--if-exists", f"--dbname={pg_url}", args.dump_file],
        check=True,
    )
    print("Restore complete.")


if __name__ == "__main__":
    main()
