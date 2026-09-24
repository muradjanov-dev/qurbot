"""Select cheap CI only for Markdown-only changes."""

import os
import subprocess
from pathlib import PurePosixPath


def docs_only(paths: list[str]) -> bool:
    return bool(paths) and all(
        path == "README.md" or (path.startswith("docs/") and PurePosixPath(path).suffix == ".md")
        for path in paths
    )


def changed_paths() -> list[str]:
    if os.environ.get("GITHUB_EVENT_NAME") not in {"pull_request", "push", "workflow_call"}:
        return []
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", "-z", "HEAD^", "HEAD"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        return []
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


if __name__ == "__main__":
    print(f"docs_only={str(docs_only(changed_paths())).lower()}")
