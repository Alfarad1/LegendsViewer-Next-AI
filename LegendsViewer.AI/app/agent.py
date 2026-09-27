from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings
from app.schemas import ChatMessage, EntityLink
from app.tools import build_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Urist the Bookkeeper — an old, stubborn, bearded dwarf historian from the world of Dwarf Fortress.
You sit in a dusty corner of the mountainhomes among stacks of stone tablets and yellowed parchment, muttering over the chronicles of this world.
You have seen too many forts fall, too many kings go mad, and too little good ale poured for honest bookkeepers.

Voice and manner:
- Speak as a living dwarf, not as a machine. Grumble, digress briefly, praise fine craftsmanship, gold, and ale when it fits.
- Use dwarven flavor: "by Armok", "strike the earth", "a proper dwarf would...", "bah", "hmpf", muttering about elves, goblins, or foolish surface-folk when the tale invites it.
- Prefer vivid chronicle storytelling over dry lists. Open with a short in-character beat ("Let me leaf through these tablets..."), then tell the tale.
- Never break character. Never say you are an AI, chatbot, language model, or assistant.
- Never use modern or technical wording in your spoken replies. Instead of AI, database, API, search, query, tool, server, or file — say "my ancient archives", "the chronicles", "the stone tablets", "the ledgers", "I leafed through the records", "the scribes wrote".

Your task:
1. Consult the project's maps and legends (via your archive tools) and answer the player's questions about the world.
2. Tell stories of battles, forgotten beasts, heroes, cursed artifacts, and the rise and fall of civilizations — as if you yourself turned every page.

You know the chronicles of: Sites (settlements), Historical Figures (people/gods/beasts/etc.), Entities (civilizations/organizations), and Creatures/races (species like dwarf, goblin, dragon).

How you consult the archives (silent ritual — do this, but describe it in character to the player, never name tools):
1. Call check_world_loaded.
2. Infer the best target from the user question:
   - A named individual (e.g. "Canyoncertain the Hale", "Urist McBeard") → search_objects with HistoricalFigure (not search_creatures), even if they are a hydra/dragon/beast.
   - Creature/race/species in general (e.g. "what are hydras?", "dwarves") → search_creatures only.
   - Site / Entity → search_objects, then get_object_summary_data when you have a clear match.
   If unclear, try HistoricalFigure first when a proper name is present.
3. If multiple matches: list them briefly in character and ask which chronicle the listener wants. Do not invent a choice.
4. For Site/HistoricalFigure/Entity with exactly one match (or the user clarified an id): call get_object_summary_data, then write a narrative summary from that data only — as a tale from the ledgers, not a report.

Rules:
- Reply in the user's language. Do not translate proper names.
- Use only facts from tool results. Never invent lore, dates, names, or events.
- If data is missing: stay in character ("Bah — the chronicles are silent on that", "these tablets are incomplete", "I find no such name in the ledgers").
- If no world is loaded: complain that the archives have not been opened / no world-chronicle sits upon your desk.
- Keep the meat of the answer focused: who/what it is, place or affiliations, and the notable deeds or doom that matter.
- Do not append machine-readable link payloads; the UI receives links separately.
"""

MAX_TOOL_ROUNDS = 8
_SEARCH_TOOLS = frozenset(
    {"search_objects", "search_creatures", "get_object_summary_data"}
)
_OBJECT_TYPES = frozenset({"Site", "HistoricalFigure", "Entity"})
_TOOL_NUDGE = (
    "Stop. You have not consulted the archives yet. "
    "You must call tools first: check_world_loaded, then search_objects "
    "or search_creatures (and get_object_summary_data when needed). "
    "Do not write a story until tool results are available. Call a tool now."
)
_SEARCH_NUDGE = (
    "Stop. Checking that the world is loaded is not enough. "
    "You must search now: for a named individual (even a hydra/beast) call "
    "search_objects with object_type HistoricalFigure and their name; "
    "for a race/species call search_creatures; for a place call search_objects "
    "with Site. Then call get_object_summary_data when you have an id. "
    "Do not narrate searching — call a search tool now."
)
_FINAL_NUDGE = (
    "The archive tools above have spoken. Now answer the listener as Urist the Bookkeeper: "
    "grumbling dwarf chronicler, vivid tale, dwarven flavor (by Armok, tablets, ledgers). "
    "Use ONLY facts from the tool results — no invented names, dates, or events. "
    "Do not call tools. Do not write a dry report or encyclopedia entry. "
    "If a match was found, open with a short in-character beat, then tell the tale. "
    "Only say the chronicles are silent when a search explicitly found no match."
)


def _format_for_log(value: Any, max_chars: int = 0) -> str:
    """Pretty-print for logs. max_chars=0 means no truncation."""
    if isinstance(value, str):
        text = value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            text = json.dumps(parsed, ensure_ascii=False, indent=2, default=str)
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    text = text.strip()
    if max_chars > 0 and len(text) > max_chars:
        return f"{text[:max_chars]}…\n[truncated chars={len(text)} max={max_chars}]"
    return text


def _history_to_messages(history: list[ChatMessage]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history[-12:]:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        else:
            messages.append(AIMessage(content=item.content))
    return messages


def _resolve_provider(settings: Settings) -> str:
    provider = (settings.llm_provider or "auto").strip().lower()
    if provider != "auto":
        return provider
    key = settings.openai_api_key or ""
    base = (settings.openai_base_url or "").lower()
    if key.startswith("sk-ant-") or "anthropic.com" in base:
        return "anthropic"
    return "openai"


def _should_use_responses_api(settings: Settings) -> bool:
    """GPT/o-series on OpenAI cloud need /v1/responses for tools + reasoning."""
    base = (settings.openai_base_url or "").lower()
    if any(
        marker in base
        for marker in ("127.0.0.1", "localhost", "ollama", "host.docker.internal")
    ):
        return False
    model = (settings.openai_model or "").lower()
    return model.startswith(("gpt-", "o1", "o3", "o4"))


def _build_llm(settings: Settings, *, tools: bool) -> BaseChatModel | Runnable:
    provider = _resolve_provider(settings)
    if provider == "anthropic":
        # Anthropic Messages API — not OpenAI-compatible; ignore OPENAI_BASE_URL.
        # Newer Claude models reject `temperature` (deprecated).
        # Default max_tokens is ~1024 and truncates long chronicle replies mid-sentence.
        llm: BaseChatModel = ChatAnthropic(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            max_tokens=8192,
            streaming=True,
        )
    else:
        use_responses = _should_use_responses_api(settings)
        openai_kwargs: dict[str, Any] = {
            "model": settings.openai_model,
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
            "max_tokens": 8192,
            "streaming": True,
        }
        if use_responses:
            # Required for gpt-5.x tools+reasoning; chat completions rejects that combo.
            openai_kwargs["use_responses_api"] = True
        else:
            # Local Ollama / older OpenAI-compatible servers.
            openai_kwargs["temperature"] = 0.2
        llm = ChatOpenAI(**openai_kwargs)
    if tools:
        return llm.bind_tools(build_tools())
    return llm


def _extract_links_from_tool_content(content: str, bucket: list[EntityLink]) -> None:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return
    for raw in payload.get("links") or []:
        try:
            link = EntityLink.model_validate(raw)
        except Exception:  # noqa: BLE001
            continue
        if not any(existing.type == link.type and existing.id == link.id for existing in bucket):
            bucket.append(link)


def _single_match_from_search(content: str) -> tuple[str, int] | None:
    """If search_objects found exactly one Site/HF/Entity, return (type, id)."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    data = payload.get("data") or {}
    if data.get("ambiguous"):
        return None
    candidates = data.get("candidates") or []
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    object_type = candidate.get("object_type")
    object_id = candidate.get("id")
    if object_type not in _OBJECT_TYPES or object_id is None:
        return None
    try:
        return str(object_type), int(object_id)
    except (TypeError, ValueError):
        return None


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content or "")


async def _auto_fetch_summaries(
    pending: set[tuple[str, int]],
    *,
    tools_by_name: dict[str, Any],
    messages: list[BaseMessage],
    collected_links: list[EntityLink],
    log_max_chars: int = 0,
) -> AsyncIterator[dict[str, Any]]:
    """Fetch get_object_summary_data for unambiguous search hits the model skipped."""
    summary_tool = tools_by_name.get("get_object_summary_data")
    if summary_tool is None or not pending:
        return

    for object_type, object_id in sorted(pending):
        args = {"object_type": object_type, "object_id": object_id}
        logger.info("Auto-fetch summary type=%s id=%s", object_type, object_id)
        yield {
            "event": "status",
            "data": {"tool": "get_object_summary_data", "args": args},
        }
        tool_result = await summary_tool.ainvoke(args)
        if not isinstance(tool_result, str):
            tool_result = json.dumps(tool_result, ensure_ascii=False, default=str)
        _extract_links_from_tool_content(tool_result, collected_links)
        logger.info(
            "Auto-fetch result type=%s id=%s chars=%d\n%s",
            object_type,
            object_id,
            len(tool_result),
            _format_for_log(tool_result, log_max_chars),
        )
        messages.append(
            HumanMessage(
                content=(
                    f"[Archive tool result — get_object_summary_data "
                    f"object_type={object_type} object_id={object_id}]\n{tool_result}"
                )
            )
        )
    pending.clear()


async def stream_chat(
    message: str,
    history: list[ChatMessage] | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE-ready events: token / error / done."""
    settings = settings or get_settings()
    if not (settings.openai_api_key or "").strip():
        logger.error("Chat rejected: OPENAI_API_KEY is not set")
        yield {
            "event": "error",
            "data": {
                "message": (
                    "OPENAI_API_KEY is not set. Configure an OpenAI/Ollama key, "
                    "or an Anthropic key (sk-ant-...) with LLM_PROVIDER=anthropic."
                ),
            },
        }
        return

    history = history or []
    log_max = settings.ai_log_max_chars
    provider = _resolve_provider(settings)
    logger.info(
        "Chat start provider=%s model=%s responses_api=%s history=%d message=\n%s",
        provider,
        settings.openai_model,
        provider == "openai" and _should_use_responses_api(settings),
        len(history),
        _format_for_log(message, log_max),
    )

    tools = build_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    llm_with_tools = _build_llm(settings, tools=True)
    llm_final = _build_llm(settings, tools=False)

    messages: list[BaseMessage] = [SystemMessage(content=SYSTEM_PROMPT)]
    messages.extend(_history_to_messages(history))
    messages.append(HumanMessage(content=message))

    collected_links: list[EntityLink] = []
    tools_used = False
    searched = False
    pending_summaries: set[tuple[str, int]] = set()

    try:
        for round_idx in range(1, MAX_TOOL_ROUNDS + 1):
            logger.info("LLM round %d/%d (tools)", round_idx, MAX_TOOL_ROUNDS)
            ai_message: AIMessage = await llm_with_tools.ainvoke(messages)  # type: ignore[assignment]
            messages.append(ai_message)

            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                content = _message_text(ai_message.content)
                messages.pop()
                if not tools_used:
                    logger.warning(
                        "Rejected text-only reply before any tool use (round %d)\n%s",
                        round_idx,
                        _format_for_log(content or "", log_max),
                    )
                    yield {
                        "event": "status",
                        "data": {
                            "tool": "force_archives",
                            "args": {"reason": "model_skipped_tools", "round": round_idx},
                        },
                    }
                    messages.append(HumanMessage(content=_TOOL_NUDGE))
                    continue
                if not searched:
                    # e.g. only check_world_loaded — do not answer "not found" yet
                    logger.warning(
                        "Rejected early stop before search (round %d)\n%s",
                        round_idx,
                        _format_for_log(content or "", log_max),
                    )
                    yield {
                        "event": "status",
                        "data": {
                            "tool": "force_search",
                            "args": {"reason": "no_search_yet", "round": round_idx},
                        },
                    }
                    messages.append(HumanMessage(content=_SEARCH_NUDGE))
                    continue
                if pending_summaries:
                    logger.info(
                        "Model skipped summary fetch; auto-loading %s",
                        sorted(pending_summaries),
                    )
                    async for event in _auto_fetch_summaries(
                        pending_summaries,
                        tools_by_name=tools_by_name,
                        messages=messages,
                        collected_links=collected_links,
                        log_max_chars=log_max,
                    ):
                        yield event
                    # Summary just arrived — ask for a fresh in-character answer below.
                    logger.info(
                        "Tool loop finished after auto-summary; discarding draft\n%s",
                        _format_for_log(content or "", log_max),
                    )
                    break
                if content:
                    # Archives consulted; keep the model's in-character draft.
                    logger.info(
                        "Using tool-loop reply chars=%d links=%d\n%s",
                        len(content),
                        len(collected_links),
                        _format_for_log(content, log_max),
                    )
                    yield {"event": "token", "data": {"text": content}}
                    yield {
                        "event": "done",
                        "data": {"links": [link.model_dump() for link in collected_links]},
                    }
                    return
                logger.info("Tool loop finished with empty draft; falling through to final stream")
                break

            tools_used = True
            logger.info("Tool calls: %s", [call.get("name") for call in tool_calls])
            for call in tool_calls:
                name = call.get("name") or ""
                args = call.get("args") or {}
                call_id = call.get("id") or name
                if name in _SEARCH_TOOLS:
                    searched = True
                tool = tools_by_name.get(name)
                logger.info(
                    "Tool invoke name=%s args=\n%s",
                    name,
                    _format_for_log(args, log_max),
                )
                if tool is None:
                    tool_result = json.dumps({"ok": False, "message": f"Unknown tool: {name}"})
                    logger.warning("Unknown tool: %s", name)
                else:
                    tool_result = await tool.ainvoke(args)
                    if isinstance(tool_result, str):
                        _extract_links_from_tool_content(tool_result, collected_links)
                    else:
                        tool_result = json.dumps(tool_result, ensure_ascii=False, default=str)

                result_text = str(tool_result)
                if name == "search_objects":
                    match = _single_match_from_search(result_text)
                    if match:
                        pending_summaries.add(match)
                elif name == "get_object_summary_data":
                    object_type = args.get("object_type")
                    object_id = args.get("object_id")
                    if object_type in _OBJECT_TYPES and object_id is not None:
                        try:
                            pending_summaries.discard((str(object_type), int(object_id)))
                        except (TypeError, ValueError):
                            pass

                logger.info(
                    "Tool result name=%s chars=%d\n%s",
                    name,
                    len(result_text),
                    _format_for_log(result_text, log_max),
                )
                yield {
                    "event": "status",
                    "data": {"tool": name, "args": args},
                }
                messages.append(ToolMessage(content=result_text, tool_call_id=call_id))

        if not tools_used or not searched:
            logger.error(
                "Model never completed archive search (tools_used=%s searched=%s)",
                tools_used,
                searched,
            )
            yield {
                "event": "error",
                "data": {
                    "message": (
                        "The model did not search the archives. "
                        "Try a stronger model (e.g. qwen2.5:14b) or rephrase the question."
                    ),
                },
            }
            return

        if pending_summaries:
            logger.info(
                "Rounds exhausted with pending summaries; auto-loading %s",
                sorted(pending_summaries),
            )
            async for event in _auto_fetch_summaries(
                pending_summaries,
                tools_by_name=tools_by_name,
                messages=messages,
                collected_links=collected_links,
                log_max_chars=log_max,
            ):
                yield event

        # Fallback when the model finished tools without a text reply
        logger.info("Final answer stream (no more tools)")
        messages.append(HumanMessage(content=_FINAL_NUDGE))

        produced = False
        reply_chars = 0
        reply_parts: list[str] = []
        async for chunk in llm_final.astream(messages):
            piece = _message_text(chunk.content)
            if not piece:
                continue
            produced = True
            reply_chars += len(piece)
            reply_parts.append(piece)
            yield {"event": "token", "data": {"text": piece}}

        if not produced:
            logger.info("Stream empty; trying non-streaming fallback")
            fallback = await llm_final.ainvoke(messages)
            text = _message_text(fallback.content)
            if text:
                reply_chars = len(text)
                reply_parts.append(text)
                yield {"event": "token", "data": {"text": text}}
            else:
                logger.error("Model returned an empty reply")
                yield {
                    "event": "error",
                    "data": {
                        "message": (
                            "The model returned an empty reply. "
                            "Check OPENAI_BASE_URL / OPENAI_MODEL and that Ollama is reachable."
                        ),
                    },
                }
                return

        logger.info(
            "Chat done chars=%d links=%d\n%s",
            reply_chars,
            len(collected_links),
            _format_for_log("".join(reply_parts), log_max),
        )
        yield {
            "event": "done",
            "data": {"links": [link.model_dump() for link in collected_links]},
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat failed: %s", exc)
        yield {
            "event": "error",
            "data": {"message": str(exc)},
        }
