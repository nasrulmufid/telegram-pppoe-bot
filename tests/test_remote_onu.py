from app.commands.handlers import BotContext, handle_callback
from app.mikrotik.service import RemoteOnuConfig
from app.nuxbill.service import Customer


class DummyNuxBill:
    async def get_customer_view_by_id(self, customer_id: int):
        return {"d": {"pppoe_username": "PPPOEUSER"}}

    def parse_customer(self, view):
        return Customer(
            id=41,
            username="ABEL@LBM",
            fullname="ABEL",
            status="Active",
            service_type="PPPoE",
            pppoe_username="PPPOEUSER",
        )


class DummyMikrotik:
    def __init__(self) -> None:
        self.onu = RemoteOnuConfig(ip_public="103.104.1.1", port_onu=12500, comment_firewall="1. REMOT ONU")

    async def ensure_onu_forward(self, *, to_address: str, to_port: int = 80):
        assert to_address == "172.2.1.37"
        assert to_port == 80
        return {"action": "created"}


class DummyGenieAcs:
    async def resolve_device_id_by_pppoe_username(self, *, pppoe_username: str) -> str:
        assert pppoe_username == "PPPOEUSER"
        return "DEVICEID"

    async def get_virtual_param(self, *, device_id: str, name: str) -> str:
        assert device_id == "DEVICEID"
        assert name == "IPTR069"
        return "172.2.1.37"


async def test_onu_go_requires_config():
    ctx = BotContext(nuxbill=DummyNuxBill(), activate_using="zero", mikrotik=None)
    res = await handle_callback(ctx, "onu_go:41")
    assert "belum dikonfigurasi" in res.text.lower()


async def test_onu_go_returns_url_button():
    ctx = BotContext(nuxbill=DummyNuxBill(), activate_using="zero", mikrotik=DummyMikrotik(), genieacs=DummyGenieAcs())
    res = await handle_callback(ctx, "onu_go:41")
    assert "http://103.104.1.1:12500" in res.text
    assert res.reply_markup is not None
    kb = res.reply_markup.get("inline_keyboard")
    assert isinstance(kb, list)
    assert kb[0][0]["url"] == "http://103.104.1.1:12500"

