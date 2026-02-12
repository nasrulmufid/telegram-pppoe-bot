from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict


@dataclass
class RateLimiter:
    max_requests: int
    window_sec: int
    _buckets: Dict[str, Deque[float]]

    @classmethod
    def create(cls, *, max_requests: int, window_sec: int) -> "RateLimiter":
        return cls(max_requests=max_requests, window_sec=window_sec, _buckets={})

    def allow(self, key: str) -> bool:
        now = time.time()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = deque()
            self._buckets[key] = bucket

        cutoff = now - self.window_sec
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return False

        bucket.append(now)
        return True
