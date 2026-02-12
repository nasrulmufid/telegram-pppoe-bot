from __future__ import annotations

from pathlib import Path
import time
from dataclasses import dataclass
from typing import Optional

import aiosqlite


@dataclass(frozen=True)
class AuditEvent:
    ts: float
    chat_id: int
    user_id: Optional[int]
    command: str
    args: str
    ok: bool
    message: str
    latency_ms: int


class AuditStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        db_path = Path(self._db_path)
        if db_path.parent and str(db_path.parent) not in (".", ""):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NULL,
                    command TEXT NOT NULL,
                    args TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def write(self, event: AuditEvent) -> None:
        db_path = Path(self._db_path)
        if db_path.parent and str(db_path.parent) not in (".", ""):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO bot_activity (ts, chat_id, user_id, command, args, ok, message, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.ts,
                    event.chat_id,
                    event.user_id,
                    event.command,
                    event.args,
                    1 if event.ok else 0,
                    event.message,
                    event.latency_ms,
                ),
            )
            await db.commit()


def make_event(
    *,
    chat_id: int,
    user_id: Optional[int],
    command: str,
    args: str,
    ok: bool,
    message: str,
    start_ts: float,
) -> AuditEvent:
    latency_ms = int((time.time() - start_ts) * 1000)
    return AuditEvent(
        ts=time.time(),
        chat_id=chat_id,
        user_id=user_id,
        command=command,
        args=args,
        ok=ok,
        message=message,
        latency_ms=latency_ms,
    )
