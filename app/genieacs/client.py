from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

import httpx


class GenieAcsError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenieAcsConfig:
    base_url: str
    username: str
    password: str


class GenieAcsClient:
    def __init__(self, *, config: GenieAcsConfig, http: httpx.AsyncClient) -> None:
        self._config = config
        self._http = http

    async def find_device_by_id(self, device_id: str, *, projection: Optional[list[str]] = None) -> dict[str, Any]:
        did = (device_id or "").strip()
        if not did:
            raise GenieAcsError("DeviceID kosong")
        query = json.dumps({"_id": did}, separators=(",", ":"))
        params: dict[str, Any] = {"query": query}
        if projection:
            params["projection"] = ",".join(projection)
        resp = await self._http.get("/devices", params=params)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            raise GenieAcsError("Device tidak ditemukan di GenieACS")
        if not isinstance(data[0], dict):
            raise GenieAcsError("Format data GenieACS tidak dikenali")
        return data[0]

    async def post_task_set_params(
        self,
        *,
        device_id: str,
        parameter_values: list[list[Any]],
        connection_request: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        did = (device_id or "").strip()
        if not did:
            raise GenieAcsError("DeviceID kosong")
        params: dict[str, Any] = {}
        if connection_request:
            params["connection_request"] = ""
        payload = {"name": "setParameterValues", "parameterValues": parameter_values}
        did_enc = urllib.parse.quote(did, safe="")
        resp = await self._http.post(f"/devices/{did_enc}/tasks", params=params, json=payload)
        resp.raise_for_status()
        try:
            body = resp.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        return resp.status_code, body
