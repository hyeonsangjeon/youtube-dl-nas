import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from i18n import CATALOGS, DEFAULT_LOCALE, get_catalog, get_translator, locale_from_accept_language, normalize_locale


PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def test_translation_catalogs_have_matching_keys_and_placeholders():
    english = CATALOGS[DEFAULT_LOCALE]
    english_keys = set(english)

    for locale, catalog in CATALOGS.items():
        assert set(catalog) == english_keys, f"Translation key mismatch for {locale}"
        for key, english_text in english.items():
            assert set(PLACEHOLDER_PATTERN.findall(catalog[key])) == set(
                PLACEHOLDER_PATTERN.findall(english_text)
            ), f"Placeholder mismatch for {locale}:{key}"


def test_locale_normalization_and_accept_language_priority():
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("ko_kr") == "ko-KR"
    assert normalize_locale("zh-Hans") == "zh-CN"
    assert normalize_locale("zh-TW") is None
    assert normalize_locale("pl") == "pl-PL"
    assert normalize_locale("fr-FR") is None
    assert locale_from_accept_language("fr-FR, pl-PL;q=0.8, en;q=0.7") == "pl-PL"
    assert locale_from_accept_language("ko-KR;q=0.6, zh-CN;q=0.9") == "zh-CN"


def test_catalog_falls_back_to_english_and_interpolates_values():
    catalog = get_catalog("fr-FR")
    assert catalog["login.submit"] == "Sign in"
    assert get_translator("pl-PL")("activity.queue_count", count=3) == "Kolejka: 3"


def test_all_translation_keys_used_by_templates_and_javascript_exist():
    root = Path(__file__).resolve().parents[1]
    source_paths = [
        root / "static" / "logical_js" / "logic.js",
        root / "static" / "template" / "index.tpl",
        root / "static" / "template" / "login.tpl",
        root / "static" / "template" / "terms.tpl",
    ]
    key_pattern = re.compile(r"(?<![\w.])(?:translate|t)\(\s*['\"]([^'\"]+)['\"]")
    used_keys = set()
    for source_path in source_paths:
        used_keys.update(key_pattern.findall(source_path.read_text(encoding="utf-8")))

    assert used_keys <= set(CATALOGS[DEFAULT_LOCALE])
