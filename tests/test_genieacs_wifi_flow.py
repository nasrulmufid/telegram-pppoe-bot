from app.commands.handlers import BotContext, handle_callback, handle_command
from app.nuxbill.service import Customer
from app.storage.pending import PendingStore


class DummyNuxBill:
    async def get_customer_view_by_id(self, customer_id: int):
        return {"d": {"pppoe_username": "DEVICEID"}}

    def parse_customer(self, view):
        return Customer(
            id=41,
            username="ABEL@LBM",
            fullname="ABEL",
            status="Active",
            service_type="PPPoE",
            pppoe_username="DEVICEID",
        )


class DummyGenieAcs:
    def __init__(self) -> None:
        self.last = None

    async def set_wifi_ssid(self, *, device_id: str, ssid: str) -> int:
        self.last = ("ssid", device_id, ssid)
        return 200

    async def set_wifi_password(self, *, device_id: str, password: str) -> int:
        self.last = ("password", device_id, password)
        return 202


async def test_wifi_ssid_flow_confirm_and_apply():
    pending = PendingStore()
    genie = DummyGenieAcs()
    ctx = BotContext(nuxbill=DummyNuxBill(), activate_using="zero", genieacs=genie, pending=pending, chat_id=1, user_id=2)

    res = await handle_callback(ctx, "wifi_ssid:41:Active:1")
    assert "ketik ssid" in res.text.lower()
    cancel_cb = res.reply_markup["inline_keyboard"][0][0]["callback_data"]
    action_id = cancel_cb.split(":", 1)[1]

    res2 = await handle_command(ctx, "pending_input", [action_id, "MyWifi"])
    assert "konfirmasi" in res2.text.lower()
    apply_cb = res2.reply_markup["inline_keyboard"][0][0]["callback_data"]
    assert apply_cb == f"wifi_apply:{action_id}"

    res3 = await handle_callback(ctx, apply_cb)
    assert "berhasil" in res3.text.lower()
    assert genie.last == ("ssid", "DEVICEID", "MyWifi")


async def test_wifi_password_flow_queued():
    pending = PendingStore()
    genie = DummyGenieAcs()
    ctx = BotContext(nuxbill=DummyNuxBill(), activate_using="zero", genieacs=genie, pending=pending, chat_id=1, user_id=2)

    res = await handle_callback(ctx, "wifi_pwd:41:Active:1")
    cancel_cb = res.reply_markup["inline_keyboard"][0][0]["callback_data"]
    action_id = cancel_cb.split(":", 1)[1]

    res2 = await handle_command(ctx, "pending_input", [action_id, "password123"])
    apply_cb = res2.reply_markup["inline_keyboard"][0][0]["callback_data"]
    res3 = await handle_callback(ctx, apply_cb)
    assert "menunggu" in res3.text.lower()
    assert genie.last == ("password", "DEVICEID", "password123")

