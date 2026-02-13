from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.mikrotik.client import MikrotikClient, MikrotikConfig


@dataclass(frozen=True)
class RemoteOnuConfig:
    ip_public: str
    port_onu: int
    comment_firewall: str


class MikrotikService:
    def __init__(self, *, mikrotik: MikrotikConfig, onu: RemoteOnuConfig) -> None:
        self._client = MikrotikClient(mikrotik)
        self._onu = onu

    @property
    def onu(self) -> RemoteOnuConfig:
        return self._onu

    async def ensure_onu_forward(self, *, to_address: str, to_port: int = 80) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._client.ensure_onu_forward_rule,
            ip_public=self._onu.ip_public,
            port_onu=self._onu.port_onu,
            comment=self._onu.comment_firewall,
            to_address=to_address,
            to_port=to_port,
        )

