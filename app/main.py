from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

from app.commands.handlers import BotContext, handle_command
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
async def _send_telegram(chat_id: int, reply_to: Optional[int], text: str) -> None:
    telegram: TelegramClient = app.state.telegram
    await telegram.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to)


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

    msg = update.get_message()
    if not msg or not msg.text:
        return {"ok": True}

    parsed = parse_command(msg.text)
    if not parsed:
        return {"ok": True}

    user_id = msg.from_user.id if msg.from_user else None
    key = f"{msg.chat.id}:{user_id}"
    limiter: RateLimiter = app.state.rate_limiter
    if not limiter.allow(key):
        logger.info("rate_limited chat_id=%s user_id=%s", msg.chat.id, user_id)
        background.add_task(_send_telegram, msg.chat.id, msg.message_id, "Rate limit. Coba lagi sebentar.")
        return {"ok": True}

    ctx = BotContext(
        nuxbill=app.state.nuxbill,
        recharge_using=settings.nuxbill_recharge_using,
        activate_using=settings.nuxbill_activate_using,
    )

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
            text = await asyncio.wait_for(handle_command(ctx, parsed.name, parsed.args), timeout=9.0)
            ok = True
        except asyncio.TimeoutError:
            text = "Timeout saat memproses perintah. Coba lagi."
            ok = False
        except Exception:
            text = "Terjadi kesalahan internal."
            ok = False

        try:
            await _send_telegram(msg.chat.id, msg.message_id, text)
        finally:
            audit: AuditStore = app.state.audit
            ev = make_event(
                chat_id=msg.chat.id,
                user_id=user_id,
                command=parsed.name,
                args=" ".join(parsed.args),
                ok=ok,
                message=text[:4000],
                start_ts=start_ts,
            )
            await audit.write(ev)

    background.add_task(_process)
    return {"ok": True}
