from scripts.ci_changed import docs_only


def test_docs_only_skips_application_checks_only_for_markdown() -> None:
    assert docs_only(["README.md", "docs/README.md"])
    assert not docs_only([])
    assert not docs_only(["docs/README.md", "app/services/orders.py"])
    assert not docs_only(["docs/README.md", ".github/workflows/ci.yml"])
    assert not docs_only(["docs/README.md", "AGENTS.md"])
    assert not docs_only(["docs/screenshot.png"])
