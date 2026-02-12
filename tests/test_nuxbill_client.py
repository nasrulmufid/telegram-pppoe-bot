import httpx
import pytest

from app.nuxbill.client import NuxBillClient, NuxBillError


@pytest.mark.asyncio
async def test_nuxbill_client_login_and_request_adds_token():
    calls = {"login": 0, "customers": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        r = q.get("r")
        if r == "admin/post":
            calls["login"] += 1
            return httpx.Response(
                200,
                json={"success": True, "message": "", "result": {"token": "a.1.1700000000.x"}, "meta": {}},
            )
        if r == "customers":
            calls["customers"] += 1
            assert q.get("token") == "a.1.1700000000.x"
            return httpx.Response(200, json={"success": True, "message": "", "result": {"d": []}, "meta": {}})
        return httpx.Response(404, json={"success": False, "message": "not found", "result": {}, "meta": {}})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = NuxBillClient(api_url="https://example.com/system/api.php", username="u", password="p", http=http)
        payload = await client.get(r="customers")
        assert payload["success"] is True
        assert calls["login"] == 1
        assert calls["customers"] == 1


def test_require_success_raises():
    with pytest.raises(NuxBillError):
        NuxBillClient.require_success({"success": False, "message": "bad"})
