"""
ChatKit server integration for the boilerplate backend.
Optimized, cleaned up, and hardened version.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime
from typing import Annotated, Any, AsyncIterator, Final, Literal
from uuid import uuid4

from agents import Agent, RunContextWrapper, Runner, function_tool
from chatkit.agents import (
    AgentContext,
    ClientToolCall,
    ThreadItemConverter,
    stream_agent_response,
)
from chatkit.server import ChatKitServer, ThreadItemDoneEvent
from chatkit.types import (
    Attachment,
    ClientToolCallItem,
    HiddenContextItem,
    ThreadItem,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)
from openai.types.responses import ResponseInputContentParam
from pydantic import ConfigDict, Field

from .constants import INSTRUCTIONS, MODEL
from .facts import Fact, fact_store
from .memory_store import MemoryStore
from .sample_widget import render_weather_widget, weather_widget_copy_text
from .weather import WeatherLookupError, retrieve_weather
from .weather import normalize_unit as normalize_temperature_unit


# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
# Constants & helpers
# ------------------------------------------------------------------------------
SUPPORTED_COLOR_SCHEMES: Final[frozenset[str]] = frozenset({"light", "dark"})
CLIENT_THEME_TOOL_NAME: Final[str] = "switch_theme"


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:8]}"


def _is_tool_completion_item(item: Any) -> bool:
    return isinstance(item, ClientToolCallItem)


def _normalize_color_scheme(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in SUPPORTED_COLOR_SCHEMES:
        return normalized
    if "dark" in normalized:
        return "dark"
    if "light" in normalized:
        return "light"
    raise ValueError("Theme must be either 'light' or 'dark'.")


def _user_message_text(item: UserMessageItem) -> str:
    return " ".join(
        part.text for part in item.content if getattr(part, "text", None)
    ).strip()


# ------------------------------------------------------------------------------
# Agent context
# ------------------------------------------------------------------------------
class FactAgentContext(AgentContext):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: Annotated[MemoryStore, Field(exclude=True)]
    request_context: dict[str, Any]


# ------------------------------------------------------------------------------
# Internal streaming helpers
# ------------------------------------------------------------------------------
async def _stream_saved_hidden(
    ctx: RunContextWrapper[FactAgentContext], fact: Fact
) -> None:
    """Stream a hidden FACT_SAVED marker back to the client."""
    await ctx.context.stream(
        ThreadItemDoneEvent(
            item=HiddenContextItem(
                id=_gen_id("msg"),
                thread_id=ctx.context.thread.id,
                created_at=datetime.now(),
                content=(
                    f'<FACT_SAVED id="{fact.id}" '
                    f'threadId="{ctx.context.thread.id}">'
                    f"{fact.text}</FACT_SAVED>"
                ),
            ),
        )
    )


# ------------------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------------------
@function_tool(
    description_override="Record a fact shared by the user so it is saved immediately."
)
async def save_fact(
    ctx: RunContextWrapper[FactAgentContext],
    fact: str,
) -> dict[str, str] | None:
    try:
        saved = await fact_store.create(text=fact)
        confirmed = await fact_store.mark_saved(saved.id)

        if not confirmed:
            raise RuntimeError("Fact confirmation failed")

        await _stream_saved_hidden(ctx, confirmed)

        ctx.context.client_tool_call = ClientToolCall(
            name="record_fact",
            arguments={
                "fact_id": confirmed.id,
                "fact_text": confirmed.text,
            },
        )

        logger.info("Fact saved: %s", confirmed.id)
        return {"fact_id": confirmed.id, "status": "saved"}

    except Exception:
        logger.exception("Failed to save fact")
        return None


@function_tool(
    description_override="Switch the chat interface between light and dark color schemes."
)
async def switch_theme(
    ctx: RunContextWrapper[FactAgentContext],
    theme: str,
) -> dict[str, str] | None:
    try:
        normalized = _normalize_color_scheme(theme)
        ctx.context.client_tool_call = ClientToolCall(
            name=CLIENT_THEME_TOOL_NAME,
            arguments={"theme": normalized},
        )
        logger.debug("Theme switched to %s", normalized)
        return {"theme": normalized}

    except Exception:
        logger.exception("Failed to switch theme")
        return None


@function_tool(
    description_override=(
        "Look up the current weather and upcoming forecast for a location "
        "and render an interactive weather dashboard."
    )
)
async def get_weather(
    ctx: RunContextWrapper[FactAgentContext],
    location: str,
    unit: Literal["celsius", "fahrenheit"] | str | None = None,
) -> dict[str, str | None]:
    logger.info("Weather lookup requested: %s (%s)", location, unit)

    try:
        normalized_unit = normalize_temperature_unit(unit)
        data = await retrieve_weather(location, normalized_unit)
    except WeatherLookupError as exc:
        raise ValueError(str(exc)) from exc

    try:
        widget = render_weather_widget(data)
        copy_text = weather_widget_copy_text(data)
        await ctx.context.stream_widget(widget, copy_text=copy_text)
    except Exception as exc:
        logger.exception("Weather widget rendering failed")
        raise ValueError("Weather data is currently unavailable.") from exc

    return {
        "location": data.location,
        "unit": normalized_unit,
        "observed_at": (
            data.observation_time.isoformat()
            if data.observation_time
            else None
        ),
    }


# ------------------------------------------------------------------------------
# ChatKit server
# ------------------------------------------------------------------------------
class FactAssistantServer(ChatKitServer[dict[str, Any]]):
    """ChatKit server wired up with fact recording, theming, and weather tools."""

    def __init__(self) -> None:
        self.store = MemoryStore()
        super().__init__(self.store)

        self.assistant = Agent[FactAgentContext](
            model=MODEL,
            name="ChatKit Guide",
            instructions=INSTRUCTIONS,
            tools=[save_fact, switch_theme, get_weather],  # type: ignore[arg-type]
        )

        self._thread_item_converter = self._init_thread_item_converter()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def respond(
        self,
        thread: ThreadMetadata,
        item: UserMessageItem | None,
        context: dict[str, Any],
    ) -> AsyncIterator[ThreadStreamEvent]:
        agent_context = FactAgentContext(
            thread=thread,
            store=self.store,
            request_context=context,
        )

        target = item or await self._latest_thread_item(thread, context)
        if not target or _is_tool_completion_item(target):
            return

        agent_input = await self._to_agent_input(thread, target)
        if agent_input is None:
            return

        result = Runner.run_streamed(
            self.assistant,
            agent_input,
            context=agent_context,
        )

        async for event in stream_agent_response(agent_context, result):
            yield event

    async def to_message_content(
        self, _input: Attachment
    ) -> ResponseInputContentParam:
        raise RuntimeError("File attachments are not supported.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _init_thread_item_converter(self) -> Any | None:
        if not callable(ThreadItemConverter):
            return None

        for kwargs in (
            {"to_message_content": self.to_message_content},
            {"message_content_converter": self.to_message_content},
            {},
        ):
            try:
                return ThreadItemConverter(**kwargs)
            except TypeError:
                continue

        return None

    async def _latest_thread_item(
        self,
        thread: ThreadMetadata,
        context: dict[str, Any],
    ) -> ThreadItem | None:
        try:
            items = await self.store.load_thread_items(
                thread.id, None, 1, "desc", context
            )
            return items.data[0] if items.data else None
        except Exception:
            logger.exception("Failed to load latest thread item")
            return None

    async def _to_agent_input(
        self,
        thread: ThreadMetadata,
        item: ThreadItem,
    ) -> Any | None:
        if _is_tool_completion_item(item):
            return None

        converter = self._thread_item_converter
        if converter:
            for method_name in (
                "to_input_item",
                "convert",
                "convert_item",
                "convert_thread_item",
            ):
                method = getattr(converter, method_name, None)
                if not method:
                    continue

                try:
                    sig = inspect.signature(method)
                    args = [item]
                    kwargs: dict[str, Any] = {}

                    params = list(sig.parameters.values())
                    if len(params) > 1:
                        param = params[1]
                        if param.kind in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        ):
                            args.append(thread)
                        else:
                            kwargs[param.name] = thread

                    result = method(*args, **kwargs)
                    return await result if inspect.isawaitable(result) else result

                except Exception:
                    logger.debug(
                        "Converter method failed: %s", method_name, exc_info=True
                    )

        if isinstance(item, UserMessageItem):
            return _user_message_text(item)

        return None


# ------------------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------------------
def create_chatkit_server() -> FactAssistantServer:
    """Create and return a configured ChatKit server."""
    return FactAssistantServer()
