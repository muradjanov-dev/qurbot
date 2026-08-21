"""Turn a dropped map pin into a human-readable address.

Why a real geocoder and not the LLM: a language model does not know what
stands at a given latitude and longitude. Asked to name the place it will
produce a fluent, confident, wrong street -- and a wrong delivery address fails
silently, at the door, after the customer has already paid. So this calls a
geocoding service, and whatever comes back is still shown to the customer to
confirm or correct before it is saved.

Two providers, chosen by whether a key is configured:

* Yandex, when `yandex_geocoder_api_key` is set. Materially better coverage of
  Uzbek street naming and micro-districts, and it answers in Uzbek/Russian.
* Nominatim (OpenStreetMap) otherwise. Free and keyless so the feature works
  out of the box, but coarser -- often only the street, sometimes only the
  district. Fine as a starting suggestion the customer edits.

A failure here is never fatal: the customer is asked to type the address
instead, and the pin (which is what the courier actually navigates to) is saved
either way.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_YANDEX_URL = "https://geocode-maps.yandex.ru/1.x/"

# Nominatim's usage policy requires an identifying User-Agent naming the app.
_USER_AGENT = "QurBot/1.0 (construction materials delivery; Tashkent)"

_LANG_TO_LOCALE = {
    "uz_latn": "uz_UZ",
    "uz_cyrl": "uz_UZ",
    "ru": "ru_RU",
}


class GeocodingService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def reverse_geocode(self, lat: float, lng: float, lang: str = "uz_latn") -> str | None:
        """Best-effort address for a pin. None when nothing usable came back."""
        try:
            if settings.yandex_geocoder_api_key:
                return await self._yandex(lat, lng, lang)
            return await self._nominatim(lat, lng, lang)
        except Exception:
            # Never let a third-party outage block someone placing an order.
            logger.warning("reverse_geocode_failed", lat=lat, lng=lng, exc_info=True)
            return None

    async def _request(self, url: str, params: dict[str, str]) -> dict[str, Any] | None:
        timeout = settings.geocoding_timeout_seconds
        if self._client is not None:
            response = await self._client.get(url, params=params, timeout=timeout)
        else:
            async with httpx.AsyncClient(
                timeout=timeout, headers={"User-Agent": _USER_AGENT}
            ) as client:
                response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else None

    async def _nominatim(self, lat: float, lng: float, lang: str) -> str | None:
        data = await self._request(
            _NOMINATIM_URL,
            {
                "lat": str(lat),
                "lon": str(lng),
                "format": "jsonv2",
                "zoom": "18",
                "accept-language": "ru" if lang == "ru" else "uz",
            },
        )
        if not data:
            return None
        display = data.get("display_name")
        if not isinstance(display, str) or not display.strip():
            return None
        # Nominatim appends country and postcode, which nobody dictating an
        # address to a courier says out loud.
        parts = [p.strip() for p in display.split(",") if p.strip()]
        trimmed = [p for p in parts if not p.isdigit() or len(p) < 5]
        return ", ".join(trimmed[:4]) or None

    async def _yandex(self, lat: float, lng: float, lang: str) -> str | None:
        data = await self._request(
            _YANDEX_URL,
            {
                "apikey": settings.yandex_geocoder_api_key or "",
                "geocode": f"{lng},{lat}",
                "format": "json",
                "results": "1",
                "lang": _LANG_TO_LOCALE.get(lang, "uz_UZ"),
            },
        )
        if not data:
            return None
        try:
            response = data["response"]
            members = response["GeoObjectCollection"]["featureMember"]
            if not members:
                return None
            geo_object = members[0]["GeoObject"]
            meta = geo_object["metaDataProperty"]["GeocoderMetaData"]
            text = meta.get("text") or geo_object.get("name")
        except (KeyError, IndexError, TypeError):
            logger.warning("yandex_geocode_unexpected_shape", lat=lat, lng=lng)
            return None
        if not isinstance(text, str) or not text.strip():
            return None
        # Yandex prefixes the country; the customer already knows what country
        # they are in.
        cleaned = text.replace("Ўзбекистон, ", "").replace("Узбекистан, ", "")
        return cleaned.strip() or None
