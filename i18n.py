import json
import os
import re


DEFAULT_LOCALE = "en"
LOCALE_COOKIE = "ydlnas_locale"
SUPPORTED_LOCALES = {
    "en": "English",
    "ko-KR": "한국어",
    "zh-CN": "简体中文",
    "pl-PL": "Polski",
}
I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "i18n")


def load_catalog(locale):
    path = os.path.join(I18N_DIR, f"{locale}.json")
    with open(path, encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    if not isinstance(catalog, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in catalog.items()
    ):
        raise ValueError(f"Invalid translation catalog: {path}")
    return catalog


CATALOGS = {locale: load_catalog(locale) for locale in SUPPORTED_LOCALES}


def normalize_locale(value):
    candidate = str(value or "").strip().replace("_", "-").lower()
    if not candidate:
        return None
    if candidate == "en" or candidate.startswith("en-"):
        return "en"
    if candidate == "ko" or candidate.startswith("ko-"):
        return "ko-KR"
    if candidate in {"zh", "zh-cn", "zh-sg", "zh-hans"} or candidate.startswith("zh-hans-"):
        return "zh-CN"
    if candidate == "pl" or candidate.startswith("pl-"):
        return "pl-PL"
    return None


def locale_from_accept_language(header):
    weighted = []
    for order, item in enumerate(str(header or "").split(",")):
        parts = [part.strip() for part in item.split(";")]
        locale = normalize_locale(parts[0])
        if not locale:
            continue
        quality = 1.0
        for part in parts[1:]:
            match = re.fullmatch(r"q=([01](?:\.\d+)?)", part, re.IGNORECASE)
            if match:
                quality = float(match.group(1))
                break
        if quality > 0:
            weighted.append((quality, -order, locale))
    return max(weighted, default=(0, 0, DEFAULT_LOCALE))[2]


def select_locale(cookie_value=None, accept_language=None):
    return normalize_locale(cookie_value) or locale_from_accept_language(accept_language)


def get_catalog(locale):
    selected = normalize_locale(locale) or DEFAULT_LOCALE
    catalog = dict(CATALOGS[DEFAULT_LOCALE])
    if selected != DEFAULT_LOCALE:
        catalog.update(CATALOGS[selected])
    return catalog


def get_translator(locale):
    catalog = get_catalog(locale)

    def translate(key, **values):
        text = catalog.get(key, CATALOGS[DEFAULT_LOCALE].get(key, key))
        if values:
            try:
                return text.format(**values)
            except (KeyError, ValueError):
                return text
        return text

    return translate


def catalog_json(locale):
    return json.dumps(get_catalog(locale), ensure_ascii=False).replace("</", "<\\/")


def locale_options():
    return list(SUPPORTED_LOCALES.items())
