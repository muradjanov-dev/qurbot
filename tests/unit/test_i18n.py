from app.core.i18n import MESSAGES, t


def test_i18n_all_keys_have_three_languages() -> None:
    required_langs = {"uz_latn", "uz_cyrl", "ru"}
    for key, lang_map in MESSAGES.items():
        missing = required_langs - set(lang_map.keys())
        assert not missing, f"Key '{key}' is missing translations for: {missing}"
        for lang, text in lang_map.items():
            assert text.strip(), f"Key '{key}' in lang '{lang}' has empty text"


def test_i18n_translation_formatting() -> None:
    # Test formatting with variables
    res_latn = t("quote_savings", lang="uz_latn", amount="50,000", pct="15.0")
    assert "50,000 so'm" in res_latn
    assert "15.0%" in res_latn

    res_ru = t("quote_savings", lang="ru", amount="50 000", pct="15.0")
    assert "50 000 сум" in res_ru
    assert "15.0%" in res_ru


def test_i18n_fallback_for_unknown_lang() -> None:
    res = t("btn_cancel", lang="unknown_lang")
    assert res == "❌ Bekor qilish"


def test_i18n_fallback_for_missing_key() -> None:
    assert t("non_existent_key_12345") == "non_existent_key_12345"
