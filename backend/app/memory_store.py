from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

from chatkit.store import NotFoundError, Store
from chatkit.types import Attachment, Page, Thread, ThreadItem, ThreadMetadata


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class _ThreadState:
    thread: ThreadMetadata
    items: List[ThreadItem] = field(default_factory=list)
    item_index: Dict[str, int] = field(default_factory=dict)


class MemoryStore(Store[dict[str, Any]]):
    """
    Simple in-memory Store compatible with ChatKit.

    ⚠️ Not suitable for production:
    - No persistence
    - No authentication
    - No attachment support
    """

    def __init__(self) -> None:
        self._threads: Dict[str, _ThreadState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_thread_metadata(thread: ThreadMetadata | Thread) -> ThreadMetadata:
        """
        Ensure ThreadMetadata contains no embedded items.
        Compatible with openai-chatkit >= 1.0.
        """
        has_items = isinstance(thread, Thread) or (
            hasattr(thread, "model_fields_set")
            and "items" in thread.model_fields_set
        )

        if not has_items:
            return thread.model_copy(deep=True)

        data = thread.model_dump(exclude={"items"})
        return ThreadMetadata(**data)

    def _get_or_create_state(self, thread_id: str) -> _ThreadState:
        state = self._threads.get(thread_id)
        if state is None:
            state = _ThreadState(
                thread=ThreadMetadata(id=thread_id, created_at=utcnow())
            )
            self._threads[thread_id] = state
        return state

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        async with self._lock:
            state = self._threads.get(thread_id)
            if not state:
                raise NotFoundError(f"Thread {thread_id} not found")
            return self._coerce_thread_metadata(state.thread)

    async def save_thread(self, thread: ThreadMetadata, context: dict[str, Any]) -> None:
        metadata = self._coerce_thread_metadata(thread)

        async with self._lock:
            state = self._threads.get(metadata.id)
            if state:
                state.thread = metadata
            else:
                self._threads[metadata.id] = _ThreadState(thread=metadata)

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadMetadata]:
        async with self._lock:
            threads = [
                self._coerce_thread_metadata(state.thread)
                for state in self._threads.values()
            ]

        threads.sort(
            key=lambda t: t.created_at or utcnow(),
            reverse=(order == "desc"),
        )

        start = 0
        if after:
            for i, thread in enumerate(threads):
                if thread.id == after:
                    start = i + 1
                    break

        page = threads[start : start + limit]
        has_more = len(threads) > start + limit
        next_after = page[-1].id if has_more and page else None

        return Page(data=page, has_more=has_more, after=next_after)

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        async with self._lock:
            self._threads.pop(thread_id, None)

    # ------------------------------------------------------------------
    # Thread Items
    # ------------------------------------------------------------------

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadItem]:
        async with self._lock:
            state = self._get_or_create_state(thread_id)
            items = [item.model_copy(deep=True) for item in state.items]

        items.sort(
            key=lambda i: getattr(i, "created_at", utcnow()),
            reverse=(order == "desc"),
        )

        start = 0
        if after:
            for i, item in enumerate(items):
                if item.id == after:
                    start = i + 1
                    break

        page = items[start : start + limit]
        has_more = len(items) > start + limit
        next_after = page[-1].id if has_more and page else None

        return Page(data=page, has_more=has_more, after=next_after)

    async def add_thread_item(
        self,
        thread_id: str,
        item: ThreadItem,
        context: dict[str, Any],
    ) -> None:
        async with self._lock:
            state = self._get_or_create_state(thread_id)
            state.item_index[item.id] = len(state.items)
            state.items.append(item.model_copy(deep=True))

    async def save_item(
        self,
        thread_id: str,
        item: ThreadItem,
        context: dict[str, Any],
    ) -> None:
        async with self._lock:
            state = self._get_or_create_state(thread_id)
            idx = state.item_index.get(item.id)

            if idx is not None:
                state.items[idx] = item.model_copy(deep=True)
            else:
                state.item_index[item.id] = len(state.items)
                state.items.append(item.model_copy(deep=True))

    async def load_item(
        self,
        thread_id: str,
        item_id: str,
        context: dict[str, Any],
    ) -> ThreadItem:
        async with self._lock:
            state = self._threads.get(thread_id)
            if not state:
                raise NotFoundError(f"Thread {thread_id} not found")

            idx = state.item_index.get(item_id)
            if idx is None:
                raise NotFoundError(f"Item {item_id} not found")

            return state.items[idx].model_copy(deep=True)

    async def delete_thread_item(
        self,
        thread_id: str,
        item_id: str,
        context: dict[str, Any],
    ) -> None:
        async with self._lock:
            state = self._threads.get(thread_id)
            if not state:
                return

            idx = state.item_index.pop(item_id, None)
            if idx is None:
                return

            state.items.pop(idx)
            # Rebuild index (safe + simple)
            state.item_index = {item.id: i for i, item in enumerate(state.items)}

    # ------------------------------------------------------------------
    # Attachments (intentionally unsupported)
    # --------------------------------------------
