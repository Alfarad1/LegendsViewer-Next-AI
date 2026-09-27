from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings

OBJECT_TYPES = ("Site", "HistoricalFigure", "Entity")

ROUTE_BY_TYPE = {
    "Site": "site",
    "HistoricalFigure": "hf",
    "Entity": "entity",
}

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Noisy event types that rarely help object summaries
DEFAULT_EXCLUDED_EVENT_TYPES = [
    # "hf died",
    # "change hf state",
    # "add hf entity link",
    # "remove hf entity link",
    # "hf relationship",
    # "change hf body state",
    # "add hf hf link",
    # "remove hf hf link",
]


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _HTML_TAG_RE.sub(" ", value)
    return _WHITESPACE_RE.sub(" ", text).strip()


def simplify_value(value: Any) -> Any:
    """Flatten nested API values into LLM-friendly primitives.

    TEMP: list/dict size caps disabled — restore [:N] slices when done experimenting.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return strip_html(value)
    if isinstance(value, list):
        return [simplify_value(item) for item in value]
    if isinstance(value, dict):
        preferred = (
            "name",
            "nameSingular",
            "namePlural",
            "id",
            "title",
            "type",
            "html",
        )
        for key in preferred:
            if key in value and value[key] not in (None, ""):
                return simplify_value(value[key])
        return {k: simplify_value(v) for k, v in value.items()}
    return str(value)


class LegendsApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.lv_api_base_url).rstrip("/")
        self._timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, json=json, params=params)
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

    async def get_world(self) -> dict[str, Any]:
        return await self._request("GET", "/api/World")

    async def search_objects(
        self,
        object_type: str,
        search_term: str,
        *,
        page_size: int = 10_000,  # TEMP: effectively unlimited
    ) -> dict[str, Any]:
        if object_type not in OBJECT_TYPES:
            raise ValueError(f"Unsupported object_type: {object_type}")
        return await self._request(
            "POST",
            f"/api/{object_type}",
            params={"pageNumber": 1, "pageSize": page_size},
            json={"searchTerm": search_term, "filters": []},
        )

    async def search_creatures(
        self,
        search_term: str,
        *,
        page_size: int = 10_000,  # TEMP: effectively unlimited
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/api/CreatureInfo",
            params={
                "pageNumber": 1,
                "pageSize": page_size,
                "search": search_term,
            },
        )

    async def get_object(self, object_type: str, object_id: int) -> dict[str, Any]:
        if object_type not in OBJECT_TYPES:
            raise ValueError(f"Unsupported object_type: {object_type}")
        return await self._request("GET", f"/api/{object_type}/{object_id}")

    async def get_object_events(
        self,
        object_type: str,
        object_id: int,
        *,
        page_size: int = 10_000,  # TEMP: effectively unlimited
        excluded_event_types: list[str] | None = None,
    ) -> dict[str, Any]:
        if object_type not in OBJECT_TYPES:
            raise ValueError(f"Unsupported object_type: {object_type}")
        excluded = excluded_event_types if excluded_event_types is not None else DEFAULT_EXCLUDED_EVENT_TYPES
        return await self._request(
            "POST",
            f"/api/{object_type}/{object_id}/events",
            params={"pageNumber": 1, "pageSize": page_size, "sortKey": "Year", "sortOrder": "asc"},
            json={"excludedEventTypes": excluded},
        )


def prune_object_for_summary(object_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Keep fields useful for an LLM summary; drop huge nested payloads."""
    base = {
        "id": raw.get("id"),
        "name": strip_html(str(raw.get("name") or "")),
        "type": simplify_value(raw.get("type") or raw.get("siteType")),
        "subtype": simplify_value(raw.get("subtype")),
        "eventCount": raw.get("eventCount"),
        "eventCollectionCount": raw.get("eventCollectionCount"),
    }

    if object_type == "Site":
        base.update(
            {
                "untranslatedName": strip_html(str(raw.get("untranslatedName") or "")),
                "region": simplify_value(raw.get("regionToLink")),
                "currentOwner": simplify_value(raw.get("currentOwnerToLink")),
                "hasStructures": raw.get("hasStructures"),
                "coordinates": raw.get("coordinates"),
                "structures": simplify_value(raw.get("structuresLinks")),
                "populations": simplify_value(raw.get("populations")),
                "officials": simplify_value(raw.get("officials")),
                "ownerHistory": simplify_value(raw.get("ownerHistory")),
            }
        )
    elif object_type == "HistoricalFigure":
        interesting_keys = (
            "race",
            "caste",
            "birthYear",
            "deathYear",
            "age",
            "isAlive",
            "isDeity",
            "isVampire",
            "isWerebeast",
            "isNecromancer",
            "associatedType",
            "goal",
            "sphere",
        )
        for key in interesting_keys:
            if key in raw:
                base[key] = simplify_value(raw[key])
        for link_key in (
            "entityLinks",
            "siteLinks",
            "hfLinks",
            "titles",
            "skills",
            "relatedObjects",
        ):
            if link_key in raw and raw[link_key] is not None:
                base[link_key] = simplify_value(raw[link_key])
    elif object_type == "Entity":
        interesting_keys = (
            "entityType",
            "race",
            "isCiv",
            "siteCount",
            "currentSiteCount",
            "warCount",
            "leaderCount",
        )
        for key in interesting_keys:
            if key in raw:
                base[key] = simplify_value(raw[key])
        for link_key in (
            "sitesLinks",
            "currentSitesLinks",
            "warsLinks",
            "leadersLinks",
            "worshippedDeities",
            "parent",
            "children",
        ):
            if link_key in raw and raw[link_key] is not None:
                base[link_key] = simplify_value(raw[link_key])

    return base


def prune_events(events_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = events_payload.get("items") or []
    pruned: list[dict[str, Any]] = []
    for item in items:
        pruned.append(
            {
                "id": item.get("id"),
                "date": item.get("date"),
                "year": item.get("year"),
                "type": item.get("type"),
                "summary": strip_html(str(item.get("html") or "")),
            }
        )
    return pruned
