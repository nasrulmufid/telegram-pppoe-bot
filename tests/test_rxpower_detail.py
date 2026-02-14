from app.commands.handlers import BotContext, handle_callback
from app.nuxbill.service import Customer


class DummyNuxBill:
    async def get_customer_view_by_id(self, customer_id: int):
        return {"d": {"pppoe_username": "PPPOEUSER"}, "activation": [{"type": "PPPoE"}]}

    def parse_customer(self, view):
        return Customer(
            id=41,
            username="user1",
            fullname="Nama 1",
            status="Active",
            service_type="PPPoE",
            pppoe_username="PPPOEUSER",
        )


class DummyGenieAcs:
    async def resolve_device_id_by_pppoe_username(self, *, pppoe_username: str) -> str:
        assert pppoe_username == "PPPOEUSER"
        return "DEVICEID"

    async def get_virtual_param(self, *, device_id: str, name: str) -> str:
        assert device_id == "DEVICEID"
        assert name == "RXPower"
        return "-18.5"


async def test_customer_detail_includes_rxpower_bold():
    ctx = BotContext(nuxbill=DummyNuxBill(), activate_using="zero", genieacs=DummyGenieAcs())
    res = await handle_callback(ctx, "cus_v:41:Active:1")
    assert res.parse_mode == "HTML"
    assert "RXPower:" in res.text
    assert "<b>-18.5 dBm</b>" in res.text

