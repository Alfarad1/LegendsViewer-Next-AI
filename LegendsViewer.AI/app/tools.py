from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.api_client import (
    OBJECT_TYPES,
    ROUTE_BY_TYPE,
    LegendsApiClient,
    prune_events,
    prune_object_for_summary,
    strip_html,
)
from app.schemas import EntityLink

_client = LegendsApiClient()


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


class CheckWorldInput(BaseModel):
    reason: str = Field(
        default="startup",
        description="Optional short reason for the check (ignored by the tool).",
    )


class SearchObjectsInput(BaseModel):
    object_type: str = Field(
        description="One of: Site, HistoricalFigure, Entity",
    )
    name: str = Field(description="Name or partial name to search for")


class SearchCreaturesInput(BaseModel):
    name: str = Field(
        description="Creature name or partial name (singular or plural), e.g. dwarf, goblin, dragon",
    )


class GetObjectSummaryInput(BaseModel):
    object_type: str = Field(description="One of: Site, HistoricalFigure, Entity")
    object_id: int = Field(description="Numeric id of the object")


async def check_world_loaded(reason: str = "startup") -> str:
    _ = reason
    try:
        world = await _client.get_world()
    except Exception as exc:  # noqa: BLE001
        return _dump(
            {
                "ok": False,
                "message": f"Failed to reach LegendsViewer API: {exc}",
                "data": None,
                "links": [],
            }
        )

    name = (world.get("name") or "").strip()
    width = world.get("width") or 0
    height = world.get("height") or 0
    loaded = bool(name) and (width > 0 or height > 0)

    if not loaded:
        return _dump(
            {
                "ok": False,
                "message": (
                    "No world is currently loaded in LegendsViewer. "
                    "Ask the user to open a legends export on the Explore Worlds page, then retry."
                ),
                "data": None,
                "links": [],
            }
        )

    return _dump(
        {
            "ok": True,
            "message": f"World loaded: {name}",
            "data": {
                "name": name,
                "alternativeName": world.get("alternativeName"),
                "currentYear": world.get("currentYear"),
                "width": width,
                "height": height,
            },
            "links": [],
        }
    )


async def search_objects(object_type: str, name: str) -> str:
    if object_type not in OBJECT_TYPES:
        return _dump(
            {
                "ok": False,
                "message": f"Unsupported object_type '{object_type}'. Use Site, HistoricalFigure, or Entity.",
                "data": None,
                "links": [],
            }
        )

    try:
        result = await _client.search_objects(object_type, name)
    except Exception as exc:  # noqa: BLE001
        return _dump(
            {
                "ok": False,
                "message": f"Search failed: {exc}",
                "data": None,
                "links": [],
            }
        )

    items = result.get("items") or []
    candidates = []
    links: list[dict[str, Any]] = []
    for item in items:
        clean_name = strip_html(str(item.get("name") or ""))
        obj_id = item.get("id")
        candidates.append(
            {
                "id": obj_id,
                "name": clean_name,
                "type": item.get("type"),
                "subtype": item.get("subtype"),
                "eventCount": item.get("eventCount"),
                "object_type": object_type,
            }
        )
        if obj_id is not None:
            links.append(
                EntityLink(
                    type=object_type,  # type: ignore[arg-type]
                    id=int(obj_id),
                    name=clean_name,
                    route=f"/{ROUTE_BY_TYPE[object_type]}/{obj_id}",
                ).model_dump()
            )

    if not candidates:
        return _dump(
            {
                "ok": False,
                "message": f"No {object_type} found matching '{name}'.",
                "data": {"candidates": []},
                "links": [],
            }
        )

    if len(candidates) > 1:
        return _dump(
            {
                "ok": True,
                "message": (
                    f"Found {len(candidates)} matches for '{name}'. "
                    "Ask the user which one they mean (by id or clarifying details), "
                    "or call get_object_summary_data with the chosen id."
                ),
                "data": {"candidates": candidates, "ambiguous": True},
                "links": links,
            }
        )

    return _dump(
        {
            "ok": True,
            "message": f"Found exactly one match for '{name}'. Fetch summary data with get_object_summary_data.",
            "data": {"candidates": candidates, "ambiguous": False},
            "links": links,
        }
    )


async def search_creatures(name: str) -> str:
    try:
        result = await _client.search_creatures(name)
    except Exception as exc:  # noqa: BLE001
        return _dump(
            {
                "ok": False,
                "message": f"Creature search failed: {exc}",
                "data": None,
                "links": [],
            }
        )

    items = result.get("items") or []
    candidates = []
    for item in items:
        name_singular = strip_html(str(item.get("nameSingular") or ""))
        name_plural = strip_html(str(item.get("namePlural") or ""))
        candidates.append(
            {
                "id": item.get("id"),
                "nameSingular": name_singular,
                "namePlural": name_plural,
                "name": name_singular or name_plural,
            }
        )

    if not candidates:
        return _dump(
            {
                "ok": False,
                "message": f"No creature found matching '{name}'.",
                "data": {"candidates": []},
                "links": [],
            }
        )

    if len(candidates) > 1:
        return _dump(
            {
                "ok": True,
                "message": (
                    f"Found {len(candidates)} creatures matching '{name}'. "
                    "List them and ask which one if needed. "
                    "CreatureInfo has no further detail endpoint — answer from these fields only."
                ),
                "data": {"candidates": candidates, "ambiguous": True},
                "links": [],
            }
        )

    return _dump(
        {
            "ok": True,
            "message": (
                f"Found creature '{candidates[0]['name']}'. "
                "CreatureInfo has no further detail endpoint — answer from these fields only."
            ),
            "data": {"candidates": candidates, "ambiguous": False},
            "links": [],
        }
    )


async def get_object_summary_data(object_type: str, object_id: int) -> str:
    if object_type not in OBJECT_TYPES:
        return _dump(
            {
                "ok": False,
                "message": f"Unsupported object_type '{object_type}'. Use Site, HistoricalFigure, or Entity.",
                "data": None,
                "links": [],
            }
        )

    try:
        raw = await _client.get_object(object_type, object_id)
        events_payload = await _client.get_object_events(object_type, object_id)
    except Exception as exc:  # noqa: BLE001
        return _dump(
            {
                "ok": False,
                "message": f"Failed to load object data: {exc}",
                "data": None,
                "links": [],
            }
        )

    pruned = prune_object_for_summary(object_type, raw)
    events = prune_events(events_payload)
    link = EntityLink(
        type=object_type,  # type: ignore[arg-type]
        id=object_id,
        name=pruned.get("name") or str(object_id),
        route=f"/{ROUTE_BY_TYPE[object_type]}/{object_id}",
    )

    return _dump(
        {
            "ok": True,
            "message": "Object data loaded.",
            "data": {
                "object": pruned,
                "events": events,
                "eventsTotalFiltered": events_payload.get("totalFilteredCount"),
            },
            "links": [link.model_dump()],
        }
    )


def build_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            coroutine=check_world_loaded,
            name="check_world_loaded",
            description=(
                "Check whether a Dwarf Fortress legends world is currently loaded in LegendsViewer. "
                "Call this first before searching."
            ),
            args_schema=CheckWorldInput,
        ),
        StructuredTool.from_function(
            coroutine=search_objects,
            name="search_objects",
            description=(
                "Search for Sites, HistoricalFigures, or Entities by name. "
                "Use object_type Site for settlements/cities/fortresses, "
                "HistoricalFigure for people/gods, Entity for civilizations and organizations."
            ),
            args_schema=SearchObjectsInput,
        ),
        StructuredTool.from_function(
            coroutine=search_creatures,
            name="search_creatures",
            description=(
                "Search for creature races/species (CreatureInfo) by name, "
                "e.g. dwarf, elf, goblin, dragon. Returns id, singular and plural names. "
                "Use this for questions about races/creatures, not individual historical figures."
            ),
            args_schema=SearchCreaturesInput,
        ),
        StructuredTool.from_function(
            coroutine=get_object_summary_data,
            name="get_object_summary_data",
            description=(
                "Fetch detailed summary data and key historical events for a specific object by id. "
                "Call after search_objects when you have a single clear match or the user picked one."
            ),
            args_schema=GetObjectSummaryInput,
        ),
    ]
