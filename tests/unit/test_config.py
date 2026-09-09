"""Production settings must fail closed when secrets are placeholders."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "bot_token": "123456:real-looking-token",
        "webhook_secret": "a-real-webhook-secret-value",
        "webhook_base_url": "https://qurbot.example",
        "admin_basic_auth_password": "a-strong-admin-password",
        "web_dev_login_enabled": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bot_token", "placeholder_token"),
        ("bot_token", "changeme"),
        ("webhook_secret", "placeholder_secret"),
        ("webhook_secret", "changeme"),
        ("admin_basic_auth_password", "placeholder_admin_password"),
        ("admin_basic_auth_password", "changeme"),
        ("webhook_base_url", "http://qurbot.example"),
        ("web_dev_login_enabled", True),
    ],
)
def test_production_rejects_unsafe_settings(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _production_settings(**{field: value})


def test_production_accepts_explicit_safe_settings() -> None:
    settings = _production_settings()
    assert settings.app_env == "production"


def test_support_contacts_have_all_three_phone_numbers() -> None:
    settings = Settings(_env_file=None)
    assert settings.support_phones == [
        "+998993416994",
        "+998935394994",
        "+998983038909",
    ]
    assert settings.support_phone_text == "+998993416994\n+998935394994\n+998983038909"
