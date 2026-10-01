"""Public welcome copy has no delivery-time or free-threshold promise."""

import pytest

from app.core.i18n import t


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_welcome_can_render_without_eta_arguments(lang):
    text = t("welcome_done", lang=lang)
    assert "{eta_" not in text
    assert "24" not in text and "48" not in text
    assert not any(word in text.lower() for word in ("soat", "соат", "час"))


@pytest.mark.parametrize("lang", ["uz_latn", "uz_cyrl", "ru"])
def test_delivery_admin_copy_does_not_advertise_free_or_minimum_order(lang):
    text = t("delivery_rules_title", lang=lang)
    assert "free:" not in text
    assert "min:" not in text
    assert "50 000" in text
