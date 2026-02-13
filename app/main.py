from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

from app.commands.handlers import BotContext, BotReply, CallbackResult, handle_callback, handle_command
from app.commands.parser import parse_command
from app.nuxbill.client import NuxBillClient
from app.nuxbill.service import NuxBillService
from app.security.rate_limit import RateLimiter
from app.settings import load_settings
from app.storage.audit import AuditStore, make_event
from app.telegram.client import TelegramClient
from app.telegram.models import Update
from app.util.retry import retry_telegram


def _setup_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


app = FastAPI(title="Telegram PPPoE Bot (NuxBill)")
logger = logging.getLogger("telegram_pppoe_bot")

_DENY_TEXT = "Akses ditolak."


def _is_allowed_user(settings, user_id: Optional[int]) -> bool:
    allowed = settings.allowed_user_ids()
    if not allowed:
        return True
    if user_id is None:
        return False
    return int(user_id) in allowed


@app.on_event("startup")
async def _startup() -> None:
    settings = load_settings()
    _setup_logging(settings.log_level)

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
    timeout = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
    http = httpx.AsyncClient(limits=limits, timeout=timeout)

    nux_http = httpx.AsyncClient(limits=limits, timeout=timeout)

    app.state.settings = settings
    app.state.http = http
    app.state.nux_http = nux_http
    app.state.telegram = TelegramClient(bot_token=settings.telegram_bot_token, http=http)
    app.state.nuxbill = NuxBillService(
        NuxBillClient(
            api_url=settings.nuxbill_api_url,
            username=settings.nuxbill_username,
            password=settings.nuxbill_password,
            http=nux_http,
        )
    )
    app.state.rate_limiter = RateLimiter.create(
        max_requests=settings.bot_rate_limit_max,
        window_sec=settings.bot_rate_limit_window_sec,
    )
    app.state.audit = AuditStore(settings.audit_db_path)
    await app.state.audit.init()


@app.on_event("shutdown")
async def _shutdown() -> None:
    http: httpx.AsyncClient = app.state.http
    nux_http: httpx.AsyncClient = app.state.nux_http
    await http.aclose()
    await nux_http.aclose()


@retry_telegram()
async def _send_telegram(
    chat_id: int,
    reply_to: Optional[int],
    text: str,
    *,
    reply_markup: Optional[dict] = None,
) -> None:
    telegram: TelegramClient = app.state.telegram
    await telegram.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to, reply_markup=reply_markup)


@retry_telegram()
async def _edit_telegram(chat_id: int, message_id: int, text: str, *, reply_markup: Optional[dict] = None) -> None:
    telegram: TelegramClient = app.state.telegram
    await telegram.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup)


@retry_telegram()
async def _answer_callback(callback_query_id: str, text: Optional[str]) -> None:
    telegram: TelegramClient = app.state.telegram
    await telegram.answer_callback_query(callback_query_id=callback_query_id, text=text)


@app.post("/webhook")
async def webhook(
    update: Update,
    background: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(
        default=None, alias="X-Telegram-Bot-Api-Secret-Token"
    ),
) -> dict[str, bool]:
    settings = app.state.settings
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        logger.warning("webhook rejected: invalid secret")
        raise HTTPException(status_code=401, detail="invalid secret")

    ctx = BotContext(
        nuxbill=app.state.nuxbill,
        activate_using=settings.nuxbill_activate_using,
    )

    if update.callback_query and isinstance(update.callback_query, dict):
        cb = update.callback_query
        cb_id = str(cb.get("id") or "")
        cb_from = cb.get("from") or {}
        user_id = cb_from.get("id")
        msg_obj = cb.get("message") or {}
        chat_obj = msg_obj.get("chat") or {}
        chat_id = chat_obj.get("id")
        message_id = msg_obj.get("message_id")
        data = cb.get("data")

        if not cb_id or not isinstance(chat_id, int) or not isinstance(message_id, int) or not isinstance(data, str):
            return {"ok": True}

        if not _is_allowed_user(settings, user_id if isinstance(user_id, int) else None):
            background.add_task(_answer_callback, cb_id, _DENY_TEXT)
            return {"ok": True}

        key = f"{chat_id}:{user_id}"
        limiter: RateLimiter = app.state.rate_limiter
        if not limiter.allow(key):
            background.add_task(_answer_callback, cb_id, "Rate limit. Coba lagi sebentar.")
            return {"ok": True}

        start_ts = time.time()

        async def _process_cb() -> None:
            try:
                result = await asyncio.wait_for(handle_callback(ctx, data), timeout=9.0)
                ok = True
            except asyncio.TimeoutError:
                result = CallbackResult("Timeout saat memproses. Coba lagi.", answer="Timeout")
                ok = False
            except Exception:
                result = CallbackResult("Terjadi kesalahan internal.", answer="Error")
                ok = False

            try:
                await _answer_callback(cb_id, result.answer)
                await _edit_telegram(chat_id, message_id, result.text, reply_markup=result.reply_markup)
            finally:
                audit: AuditStore = app.state.audit
                ev = make_event(
                    chat_id=chat_id,
                    user_id=user_id if isinstance(user_id, int) else None,
                    command="callback",
                    args=data[:500],
                    ok=ok,
                    message=result.text[:4000],
                    start_ts=start_ts,
                )
                await audit.write(ev)

        background.add_task(_process_cb)
        return {"ok": True}

    msg = update.get_message()
    if not msg or not msg.text:
        return {"ok": True}

    parsed = parse_command(msg.text)
    if not parsed:
        return {"ok": True}

    user_id = msg.from_user.id if msg.from_user else None
    if not _is_allowed_user(settings, user_id):
        background.add_task(_send_telegram, msg.chat.id, msg.message_id, _DENY_TEXT, reply_markup=None)
        return {"ok": True}
    key = f"{msg.chat.id}:{user_id}"
    limiter: RateLimiter = app.state.rate_limiter
    if not limiter.allow(key):
        logger.info("rate_limited chat_id=%s user_id=%s", msg.chat.id, user_id)
        background.add_task(_send_telegram, msg.chat.id, msg.message_id, "Rate limit. Coba lagi sebentar.", reply_markup=None)
        return {"ok": True}

    start_ts = time.time()

    async def _process() -> None:
        logger.info(
            "command chat_id=%s user_id=%s name=%s args=%s",
            msg.chat.id,
            user_id,
            parsed.name,
            " ".join(parsed.args),
        )
        try:
            reply = await asyncio.wait_for(handle_command(ctx, parsed.name, parsed.args), timeout=9.0)
            ok = True
        except asyncio.TimeoutError:
            reply = BotReply("Timeout saat memproses perintah. Coba lagi.")
            ok = False
        except Exception:
            reply = BotReply("Terjadi kesalahan internal.")
            ok = False

        try:
            await _send_telegram(msg.chat.id, msg.message_id, reply.text, reply_markup=reply.reply_markup)
        finally:
            audit: AuditStore = app.state.audit
            ev = make_event(
                chat_id=msg.chat.id,
                user_id=user_id,
                command=parsed.name,
                args=" ".join(parsed.args),
                ok=ok,
                message=reply.text[:4000],
                start_ts=start_ts,
            )
            await audit.write(ev)

    background.add_task(_process)
    return {"ok": True}
