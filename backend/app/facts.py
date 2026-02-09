"""Simple in-memory, async-safe store for user facts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class FactStatus(str, Enum):
    """Lifecycle states for collected facts."""

    PENDING = "pending"
    SAVED = "saved"
    DISCARDED = "discarded"


@dataclass(slots=True)
class Fact:
    """Represents a single fact gathered from a conversation."""

    text: str
    status: FactStatus = FactStatus.PENDING
    id: str = field(default_factory=lambda: f"fact_{uuid4().hex[:8]}")
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def as_dict(self) -> dict[str, str]:
        """Serialize the fact for API / JSON responses."""
        return {
            "id": self.id,
            "text": self.text,
            "status": self.status.value,
            "createdAt": self.created_at.isoformat(),
        }


class FactStore:
    """Async-safe in-memory store for facts.

    Notes:
    - Preserves insertion order
    - Uses a single asyncio lock for consistency
    - Intended for lightweight runtime storage (not persistence)
    """

    def __init__(self) -> None:
        self._facts: Dict[str, Fact] = {}
        self._order: List[str] = []
        self._lock = asyncio.Lock()

    async def create(self, *, text: str) -> Fact:
        """Create and store a new pending fact."""
        async with self._lock:
            fact = Fact(text=text)
            self._facts[fact.id] = fact
            self._order.append(fact.id)
            return fact

    async def mark_saved(self, fact_id: str) -> Optional[Fact]:
        """Mark a fact as saved."""
        async with self._lock:
            fact = self._facts.get(fact_id)
            if not fact:
                return None
            fact.status = FactStatus.SAVED
            return fact

    async def discard(self, fact_id: str) -> Optional[Fact]:
        """Mark a fact as discarded."""
        async with self._lock:
            fact = self._facts.get(fact_id)
            if not fact:
                return None
            fact.status = FactStatus.DISCARDED
            return fact

    async def get(self, fact_id: str) -> Optional[Fact]:
        """Retrieve a fact by ID."""
        async with self._lock:
            return self._facts.get(fact_id)

    async def list_saved(self) -> List[Fact]:
        """Return saved facts in insertion order."""
        async with self._lock:
            return [
                self._facts[fact_id]
                for fact_id in self._order
                if self._facts[fact_id].status == FactStatus.SAVED
            ]

    async def list_pending(self) -> List[Fact]:
        """Return all pending facts."""
        async with self._lock:
            return [
                fact
                for fact in self._facts.values()
                if fact.status == FactStatus.PENDING
            ]

    async def clear_discarded(self) -> int:
        """Remove discarded facts from memory.

        Returns:
            Number of facts removed.
        """
        async with self._lock:
            discarded_ids = [
                fid for fid, fact in self._facts.items()
                if fact.status == FactStatus.DISCARDED
            ]

            for fid in discarded_ids:
                self._facts.pop(fid, None)
                if fid in self._order:
                    self._order.remove(fid)

            return len(discarded_ids)


# Global singleton instance
fact_store = FactStore()
"""Global FactStore instance used by the API and workflow."""
