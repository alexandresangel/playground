"""Chat UI and assistant locale: X-Diapason-Locale header, JSON bundles under locales/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

LOCALE_HEADER = "X-Diapason-Locale"
DEFAULT_LOCALE = "en_us"
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_SUPPORTED = frozenset(
    p.stem for p in _LOCALES_DIR.glob("*.json") if p.is_file()
)


def normalize_locale(raw: Optional[str]) -> str:
    """Map Java Locale strings (e.g. en_US) to bundle id en_us; default en_us."""
    text = (raw or "").strip().replace("-", "_")
    if not text:
        return DEFAULT_LOCALE
    parts = text.split("_")
    lang = parts[0].lower()
    if len(parts) >= 2 and len(parts[1]) >= 2:
        region = parts[1].lower()[:2]
        candidate = f"{lang}_{region}"
    else:
        candidate = lang
    if candidate in _SUPPORTED:
        return candidate
    if lang in _SUPPORTED:
        return lang
    # fr_FR -> fr_fr already tried; try prefix match (e.g. en_GB -> en_us via en)
    for supported in sorted(_SUPPORTED, key=len, reverse=True):
        if supported.startswith(lang + "_") or supported == lang:
            return supported
    return DEFAULT_LOCALE


def locale_from_header_value(raw: Optional[str]) -> str:
    return normalize_locale(raw)


@lru_cache(maxsize=16)
def _load_bundle(locale: str) -> Dict[str, str]:
    path = _LOCALES_DIR / f"{locale}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, str):
            out[key] = value
    return out


def strings_for_locale(locale: str) -> Dict[str, str]:
    loc = normalize_locale(locale)
    merged = dict(_load_bundle(DEFAULT_LOCALE))
    if loc != DEFAULT_LOCALE:
        merged.update(_load_bundle(loc))
    return merged


def translate(
    key: str,
    locale: str,
    params: Optional[Mapping[str, Any]] = None,
) -> str:
    table = strings_for_locale(locale)
    text = table.get(key) or _load_bundle(DEFAULT_LOCALE).get(key) or key
    if not params:
        return text
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def locale_llm_instruction(locale: str) -> str:
    loc = normalize_locale(locale)
    if loc.startswith("fr"):
        return (
            "\n\n**Language:** The user's Diapason UI locale is French (`"
            + loc
            + "`). Reply in French unless the user clearly writes in another language.\n"
        )
    if loc.startswith("es"):
        return (
            "\n\n**Language:** The user's Diapason UI locale is Spanish (`"
            + loc
            + "`). Reply in Spanish unless the user clearly writes in another language.\n"
        )
    if loc.startswith("it"):
        return (
            "\n\n**Language:** The user's Diapason UI locale is Italian (`"
            + loc
            + "`). Reply in Italian unless the user clearly writes in another language.\n"
        )
    return (
        "\n\n**Language:** The user's Diapason UI locale is English (`"
        + loc
        + "`). Reply in English unless the user clearly writes in another language.\n"
    )
