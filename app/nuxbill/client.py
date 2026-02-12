from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.util.retry import retry_nuxbill


class NuxBillError(RuntimeError):
    pass


@dataclass
class NuxBillToken:
    value: str
    issued_at: Optional[int]

    def is_expired(self) -> bool:
        if self.issued_at is None:
            return False
        return (time.time() - self.issued_at) > 7_776_000


class NuxBillClient:
    def __init__(
        self,
        *,
        api_url: str,
        username: str,
        password: str,
        http: httpx.AsyncClient,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._username = username
        self._password = password
        self._http = http
        self._token: Optional[NuxBillToken] = None

    @staticmethod
    def _parse_token_time(token: str) -> Optional[int]:
        parts = token.split(".")
        if len(parts) != 4:
            return None
        try:
            return int(parts[2])
        except ValueError:
            return None

    @retry_nuxbill()
    async def _post_form(self, *, r: str, data: dict[str, Any], params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        q = {"r": r}
        if params:
            q.update(params)
        resp = await self._http.post(self._api_url, params=q, data=data)
        resp.raise_for_status()
        return resp.json()

    @retry_nuxbill()
    async def _request(self, method: str, *, r: str, params: Optional[dict[str, Any]] = None, data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        token = await self.get_token()
        q = {"r": r, "token": token}
        if params:
            q.update(params)

        req = self._http.build_request(method, self._api_url, params=q, data=data)
        resp = await self._http.send(req)
        resp.raise_for_status()
        return resp.json()

    async def get_token(self) -> str:
        if self._token and not self._token.is_expired():
            return self._token.value

        payload = await self._post_form(
            r="admin/post",
            data={"username": self._username, "password": self._password},
        )
        if not payload.get("success"):
            raise NuxBillError(payload.get("message") or "Login NuxBill gagal")
        token = (payload.get("result") or {}).get("token")
        if not isinstance(token, str) or not token:
            raise NuxBillError("Token NuxBill tidak ditemukan pada response")
        self._token = NuxBillToken(value=token, issued_at=self._parse_token_time(token))
        return token

    async def get(self, *, r: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        payload = await self._request("GET", r=r, params=params)
        return payload

    async def post_form(self, *, r: str, data: dict[str, Any], params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        payload = await self._request("POST", r=r, params=params, data=data)
        return payload

    @staticmethod
    def require_success(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("success") is True:
            return payload
        raise NuxBillError(payload.get("message") or "Request NuxBill gagal")
