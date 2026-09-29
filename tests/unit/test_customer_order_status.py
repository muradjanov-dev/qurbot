"""Bot order history follows the current customer's language."""

import pytest

from app.bot.handlers.customer import _customer_order_status_label


@pytest.mark.parametrize(
    ("status", "lang", "expected"),
    [
        ("new", "uz_latn", "Admin tasdig‘ini kutmoqda"),
        ("collecting", "ru", "Товары собираются"),
        ("in_transit", "uz_cyrl", "Етказиш учун йўлга чиқди"),
        ("fulfilled", "ru", "Доставлен"),
    ],
)
def test_customer_order_status_is_localized(status, lang, expected):
    assert _customer_order_status_label(status, lang) == expected
