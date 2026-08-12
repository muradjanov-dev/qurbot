import importlib
import inspect
from pathlib import Path

FORBIDDEN_MODULES = [
    "sqlalchemy",
    "aiogram",
    "httpx",
    "fastapi",
    "asyncpg",
    "alembic",
    "redis",
    "arq",
]


def test_domain_layer_is_pure() -> None:
    domain_path = Path(__file__).parent.parent.parent / "app" / "domain"
    assert domain_path.exists(), "app/domain directory must exist"

    python_files = list(domain_path.glob("**/*.py"))
    assert len(python_files) > 0, "app/domain must contain python source files"

    for file_path in python_files:
        if file_path.name == "__init__.py" and file_path.stat().st_size == 0:
            continue

        relative_module = "app.domain." + ".".join(
            file_path.relative_to(domain_path).with_suffix("").parts
        )
        if relative_module.endswith(".__init__"):
            relative_module = relative_module[:-9]

        module = importlib.import_module(relative_module)
        source = inspect.getsource(module)

        for forbidden in FORBIDDEN_MODULES:
            assert (
                f"import {forbidden}" not in source
            ), f"Purity violation in {relative_module}: forbidden import '{forbidden}'"
            assert (
                f"from {forbidden}" not in source
            ), f"Purity violation in {relative_module}: forbidden from-import '{forbidden}'"

        # datetime.now() check without clock injection
        assert "datetime.now()" not in source, (
            f"Purity violation in {relative_module}: calls datetime.now() directly "
            "instead of accepting a clock/timestamp"
        )
