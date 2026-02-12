from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    id: int
    is_bot: Optional[bool] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class Chat(BaseModel):
    id: int
    type: Optional[str] = None
    title: Optional[str] = None
    username: Optional[str] = None


class Message(BaseModel):
    message_id: int
    date: Optional[int] = None
    chat: Chat
    from_user: Optional[TelegramUser] = Field(default=None, alias="from")
    text: Optional[str] = None


class Update(BaseModel):
    update_id: int
    message: Optional[Message] = None
    edited_message: Optional[Message] = None
    callback_query: Optional[dict[str, Any]] = None

    def get_message(self) -> Optional[Message]:
        return self.message or self.edited_message
