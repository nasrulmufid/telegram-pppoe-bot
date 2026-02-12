from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Optional, TypeVar

from cachetools import TTLCache

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class TTLCacheBox(Generic[K, V]):
    cache: TTLCache

    def get(self, key: K) -> Optional[V]:
        return self.cache.get(key)

    def set(self, key: K, value: V) -> None:
        self.cache[key] = value

    async def get_or_set(self, key: K, factory: Callable[[], V]) -> V:
        existing = self.get(key)
        if existing is not None:
            return existing
        value = factory()
        self.set(key, value)
        return value
