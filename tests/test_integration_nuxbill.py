import os

import httpx
import pytest

from app.nuxbill.client import NuxBillClient


def _env(name: str) -> str | None:
    v = os.getenv(name)
    return v if v else None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_login_and_me():
    api_url = _env("NUXBILL_API_URL")
    username = _env("NUXBILL_USERNAME")
    password = _env("NUXBILL_PASSWORD")
    if not api_url or not username or not password:
        pytest.skip("env NUXBILL_* belum diset")

    timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as http:
        client = NuxBillClient(api_url=api_url, username=username, password=password, http=http)
        payload = await client.get(r="me")
        assert payload.get("success") is True
