from i18n import DEFAULT_LOCALE, normalize_locale, strings_for_locale, translate


def test_normalize_locale_java_style():
    assert normalize_locale("en_US") == "en_us"
    assert normalize_locale("fr_FR") == "fr_fr"
    assert normalize_locale("") == DEFAULT_LOCALE
    assert normalize_locale(None) == DEFAULT_LOCALE
    assert normalize_locale("de_DE") == DEFAULT_LOCALE


def test_translate_fallback():
    assert translate("composer.send", "fr_fr") == "Envoyer"
    assert translate("composer.send", "en_us") == "Send"
    assert translate("composer.stop", "fr_fr") == "Arrêter"
    assert translate("composer.stop", "en_us") == "Stop"
    assert translate("missing.key", "fr_fr") == "missing.key"


def test_strings_merge_default():
    table = strings_for_locale("fr_fr")
    assert table["composer.send"] == "Envoyer"
    assert "sidebar.history" in table


def test_disclaimer_fr_legal() -> None:
    body = translate("disclaimer.body", "fr_fr")
    assert "intelligence artificielle" in body
    assert "Diapason décline toute responsabilité" in body
    assert translate("disclaimer.link", "fr_fr") == "Avertissement — IA"
