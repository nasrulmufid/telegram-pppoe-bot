from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cachetools import TTLCache


@dataclass
class PendingAction:
    kind: str
    customer_id: int
    status: str
    page: int
    device_id: str
    value: str = ""
    stage: str = "await_value"


class PendingStore:
    def __init__(self) -> None:
        self._by_id: TTLCache = TTLCache(maxsize=2000, ttl=300)
        self._by_chat: TTLCache = TTLCache(maxsize=2000, ttl=300)

    @staticmethod
    def key(chat_id: int, user_id: Optional[int]) -> str:
        return f"{chat_id}:{user_id}"

    @staticmethod
    def _new_id() -> str:
        import secrets

        return secrets.token_urlsafe(8)

    def start(self, *, chat_key: str, action: PendingAction) -> str:
        action_id = self._new_id()
        self._by_id[action_id] = action
        self._by_chat[chat_key] = action_id
        return action_id

    def get_by_chat(self, chat_key: str) -> Optional[tuple[str, PendingAction]]:
        action_id = self._by_chat.get(chat_key)
        if not isinstance(action_id, str) or not action_id:
            return None
        action = self.get_by_id(action_id)
        if action is None:
            return None
        return action_id, action

    def get_by_id(self, action_id: str) -> Optional[PendingAction]:
        v = self._by_id.get(action_id)
        if isinstance(v, PendingAction):
            return v
        return None

    def set_by_id(self, action_id: str, action: PendingAction) -> None:
        self._by_id[action_id] = action

    def delete_by_id(self, action_id: str) -> None:
        if action_id in self._by_id:
            del self._by_id[action_id]

    def clear_chat(self, chat_key: str) -> None:
        existing = self._by_chat.get(chat_key)
        if isinstance(existing, str) and existing:
            self.delete_by_id(existing)
        if chat_key in self._by_chat:
            del self._by_chat[chat_key]
