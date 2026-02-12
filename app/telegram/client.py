from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class TelegramClient:
    bot_token: str
    http: httpx.AsyncClient

    @property
    def _base_url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: Optional[int] = None,
        disable_web_page_preview: bool = True,
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        resp = await self.http.post(f"{self._base_url}/sendMessage", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        disable_web_page_preview: bool = True,
        reply_markup: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        resp = await self.http.post(f"{self._base_url}/editMessageText", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def answer_callback_query(
        self,
        *,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text
        resp = await self.http.post(f"{self._base_url}/answerCallbackQuery", json=payload)
        resp.raise_for_status()
        return resp.json()
