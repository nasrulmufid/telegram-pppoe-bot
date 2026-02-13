from __future__ import annotations

import asyncio
import base64
import ipaddress
from dataclasses import dataclass
from typing import Any, Optional

from app.mikrotik.client import MikrotikError
from app.mikrotik.service import MikrotikService
from app.nuxbill.client import NuxBillError
from app.nuxbill.service import NuxBillService, Package, Plan
from app.security.validation import validate_page, validate_username


@dataclass(frozen=True)
class BotContext:
    nuxbill: NuxBillService
    activate_using: str
    mikrotik: Optional[MikrotikService] = None


@dataclass(frozen=True)
class BotReply:
    text: str
    reply_markup: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class CallbackResult:
    text: str
    reply_markup: Optional[dict[str, Any]] = None
    answer: Optional[str] = None


def help_text() -> str:
    return (
        "Perintah tersedia:\n"
        "/customer [page] - daftar customer (interaktif)\n"
        "/status <username> - status detail customer\n"
        "/recharge - pilih customer & paket (interaktif)\n"
        "/activate <username> - aktifkan kembali customer\n"
        "/deactivate <username> - nonaktifkan customer\n"
        "/help - menu\n"
        "/start - menu"
    )


def _fmt_pkg(pkg: Optional[Package]) -> str:
    if not pkg:
        return "-"
    name = pkg.namebp or f"plan_id={pkg.plan_id}"
    exp = f"{pkg.expiration or '-'} {pkg.time or ''}".strip()
    router = pkg.routers or "-"
    return f"{name} | {pkg.status} | exp {exp} | {router}"


def _b64e(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _b64d(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")


def _inline_keyboard(rows: list[list[dict[str, str]]]) -> dict[str, Any]:
    return {"inline_keyboard": rows}


def _main_menu_markup() -> dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "/customer"}, {"text": "/recharge"}],
            [{"text": "/status"}, {"text": "/activate"}],
            [{"text": "/deactivate"}, {"text": "/help"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "selective": True,
    }


def _chunk_buttons(buttons: list[dict[str, str]], *, per_row: int = 2) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for b in buttons:
        row.append(b)
        if len(row) >= per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return rows


def _parse_int(value: str, *, field: str) -> int:
    v = value.strip()
    if not v.isdigit():
        raise ValueError(f"{field} harus angka")
    n = int(v)
    if n < 1 or n > 2_000_000_000:
        raise ValueError(f"{field} tidak valid")
    return n


def _normalize_using(value: str) -> str:
    v = (value or "").strip().lower()
    if v in ("cash", "transfer", "dana", "zero"):
        return v
    raise ValueError("Metode pembayaran tidak valid")


def _using_label(using: str) -> str:
    u = _normalize_using(using)
    if u == "cash":
        return "Cash"
    if u == "transfer":
        return "Transfer"
    if u == "dana":
        return "DANA"
    return "Rp.0"


def _build_customers_markup(*, status: str, page: int, customers: list[dict[str, Any]]) -> dict[str, Any]:
    buttons: list[dict[str, str]] = []
    for c in customers:
        if not isinstance(c, dict):
            continue
        try:
            cid = int(c.get("id") or 0)
        except Exception:
            continue
        if cid <= 0:
            continue
        username = str(c.get("username") or "").strip()
        if not username:
            continue
        buttons.append({"text": username, "callback_data": f"rch_selc:{cid}"})

    rows = _chunk_buttons(buttons, per_row=2)

    nav: list[dict[str, str]] = []
    if page > 1:
        nav.append({"text": "⬅️ Prev", "callback_data": f"rch_c:{status}:{page - 1}"})
    if len(customers) >= 30:
        nav.append({"text": "Next ➡️", "callback_data": f"rch_c:{status}:{page + 1}"})
    if nav:
        rows.append(nav)

    other_status = "Inactive" if status.lower() == "active" else "Active"
    rows.append(
        [
            {"text": f"Tampilkan {other_status}", "callback_data": f"rch_c:{other_status}:1"},
        ]
    )
    return _inline_keyboard(rows)


def _build_customer_list_markup(*, status: str, page: int, customers: list[dict[str, Any]]) -> dict[str, Any]:
    buttons: list[dict[str, str]] = []
    for c in customers:
        if not isinstance(c, dict):
            continue
        if str(c.get("service_type") or "").upper() != "PPPOE":
            continue
        try:
            cid = int(c.get("id") or 0)
        except Exception:
            continue
        if cid <= 0:
            continue
        username = str(c.get("username") or "").strip()
        label = username or f"id={cid}"
        buttons.append({"text": label[:64], "callback_data": f"cus_v:{cid}:{status}:{page}"})

    rows = _chunk_buttons(buttons, per_row=2)

    nav: list[dict[str, str]] = []
    if page > 1:
        nav.append({"text": "⬅️ Prev", "callback_data": f"cus_l:{status}:{page - 1}"})
    if len(customers) >= 30:
        nav.append({"text": "Next ➡️", "callback_data": f"cus_l:{status}:{page + 1}"})
    if nav:
        rows.append(nav)

    other_status = "Inactive" if status.lower() == "active" else "Active"
    rows.append([{"text": f"Tampilkan {other_status}", "callback_data": f"cus_l:{other_status}:1"}])
    return _inline_keyboard(rows)


def _first_activation(view: dict[str, Any]) -> Optional[dict[str, Any]]:
    raw = view.get("activation") or []
    if not isinstance(raw, list):
        return None
    for item in raw:
        if isinstance(item, dict):
            return item
    return None


def _build_customer_detail_markup(*, customer_id: int, status: str, page: int, onu_enabled: bool) -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []
    if onu_enabled:
        rows.append([{"text": "Remote ONU", "callback_data": f"cus_onu:{customer_id}:{status}:{page}"}])
    rows.append(
        [
            {"text": "Deactivate", "callback_data": f"cus_d:{customer_id}:{status}:{page}"},
            {"text": "Recharge", "callback_data": f"rch_selc:{customer_id}"},
        ]
    )
    rows.append([{"text": "⬅️ Back", "callback_data": f"cus_l:{status}:{page}"}])
    return _inline_keyboard(rows)


def _build_status_markup(*, customer_id: int, onu_enabled: bool) -> Optional[dict[str, Any]]:
    if not onu_enabled:
        return None
    return _inline_keyboard([[{"text": "Remote ONU", "callback_data": f"onu_go:{customer_id}"}]])


def _build_onu_open_markup(*, url: str, back_data: str) -> dict[str, Any]:
    return _inline_keyboard(
        [
            [{"text": "Buka Remote ONU", "url": url}],
            [{"text": "⬅️ Back", "callback_data": back_data}],
        ]
    )


def _extract_pppoe_ip(view: dict[str, Any]) -> Optional[str]:
    d = view.get("d")
    if not isinstance(d, dict):
        return None
    ip = str(d.get("pppoe_ip") or d.get("pppoe_ip_address") or "").strip()
    return ip or None


async def _render_status(ctx: BotContext, *, customer_id: int) -> CallbackResult:
    view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
    cust = ctx.nuxbill.parse_customer(view)
    pkgs = ctx.nuxbill.parse_packages(view)
    pppoe = ctx.nuxbill.pick_active_pppoe_package(pkgs)
    lines = [
        f"Nama: {cust.fullname}",
        f"Username: {cust.username}",
        f"Status akun: {cust.status}",
    ]
    ip = _extract_pppoe_ip(view)
    if ip:
        lines.append(f"IP: {ip}")
    if cust.pppoe_username:
        lines.append(f"PPPoE username: {cust.pppoe_username}")
    if cust.service_type:
        lines.append(f"Service type: {cust.service_type}")
    lines.append(f"Paket: {_fmt_pkg(pppoe)}")
    onu_enabled = ctx.mikrotik is not None
    return CallbackResult("\n".join(lines), reply_markup=_build_status_markup(customer_id=customer_id, onu_enabled=onu_enabled))


def _build_plans_markup(*, customer_id: int, page: int, plans: list[Plan]) -> dict[str, Any]:
    buttons: list[dict[str, str]] = []
    for p in plans:
        label = p.name_plan.strip() or f"plan_id={p.id}"
        server = p.server_name()
        buttons.append(
            {
                "text": label[:64],
                "callback_data": f"rch_pay:{customer_id}:{p.id}:{_b64e(server)}:{page}",
            }
        )

    rows = _chunk_buttons(buttons, per_row=1)

    nav: list[dict[str, str]] = []
    if page > 1:
        nav.append({"text": "⬅️ Prev", "callback_data": f"rch_pl:{customer_id}:{page - 1}"})
    if len(plans) >= 20:
        nav.append({"text": "Next ➡️", "callback_data": f"rch_pl:{customer_id}:{page + 1}"})
    if nav:
        rows.append(nav)

    rows.append([{"text": "⬅️ Kembali ke customer", "callback_data": "rch_c:Active:1"}])
    return _inline_keyboard(rows)


def _build_payment_markup(*, customer_id: int, plan_id: int, server: str, page: int) -> dict[str, Any]:
    s = _b64e(server)
    options = [
        ("cash", "Cash"),
        ("transfer", "Transfer"),
        ("dana", "DANA"),
        ("zero", "Rp.0"),
    ]
    rows = [
        [{"text": label, "callback_data": f"rch_do:{customer_id}:{plan_id}:{s}:{using}:{page}"}]
        for using, label in options
    ]
    rows.append([{"text": "⬅️ Kembali ke paket", "callback_data": f"rch_pl:{customer_id}:{page}"}])
    rows.append([{"text": "⬅️ Kembali ke customer", "callback_data": "rch_c:Active:1"}])
    return _inline_keyboard(rows)


async def handle_command(ctx: BotContext, name: str, args: list[str]) -> BotReply:
    try:
        if name in ("help", "start"):
            return BotReply("Pilih menu:", reply_markup=_main_menu_markup())

        if name == "status":
            if len(args) != 1:
                return BotReply("Format: /status <username>\n\n" + help_text())
            username = validate_username(args[0])
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            rendered = await _render_status(ctx, customer_id=cust.id)
            return BotReply(rendered.text, reply_markup=rendered.reply_markup)

        if name == "customer":
            page = 1
            if args:
                if len(args) != 1:
                    return BotReply("Format: /customer [page]\n\n" + help_text())
                page = validate_page(args[0])
            status = "Active"
            customers = await ctx.nuxbill.list_customers(status_filter=status, page=page)
            text = f"Daftar customer PPPoE ({status}, page {page}):"
            return BotReply(text, reply_markup=_build_customer_list_markup(status=status, page=page, customers=customers))

        if name == "recharge":
            status = "Active"
            page = 1
            customers = await ctx.nuxbill.list_customers(status_filter=status, page=page)
            text = f"Pilih customer ({status}, page {page}):"
            return BotReply(text, reply_markup=_build_customers_markup(status=status, page=page, customers=customers))

        if name == "deactivate":
            if len(args) != 1:
                return BotReply("Format: /deactivate <username>\n\n" + help_text())
            username = validate_username(args[0])
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            pkgs = ctx.nuxbill.parse_packages(view)
            active = None
            for p in pkgs:
                if p.type.upper() == "PPPOE" and p.status.lower() == "on":
                    active = p
                    break
            if not active:
                return BotReply("Tidak ada paket PPPoE aktif untuk dinonaktifkan.")
            await ctx.nuxbill.deactivate(customer_id=cust.id, plan_id=active.plan_id)
            return BotReply(f"Deaktivasi berhasil untuk {cust.username} (plan_id={active.plan_id}).")

        if name == "activate":
            if len(args) != 1:
                return BotReply("Format: /activate <username>\n\n" + help_text())
            username = validate_username(args[0])
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            pkgs = ctx.nuxbill.parse_packages(view)
            active = None
            last_pppoe = None
            for p in pkgs:
                if p.type.upper() == "PPPOE":
                    if last_pppoe is None:
                        last_pppoe = p
                    if p.status.lower() == "on":
                        active = p
                        break

            if active:
                await ctx.nuxbill.sync(customer_id=cust.id)
                return BotReply(f"Customer masih aktif. Sync dijalankan untuk {cust.username}.")

            if not last_pppoe:
                return BotReply("Tidak ada riwayat paket PPPoE untuk diaktifkan.")

            server = last_pppoe.routers or "radius"
            await ctx.nuxbill.recharge_by_plan_id(
                customer_id=cust.id,
                plan_id=last_pppoe.plan_id,
                server=server,
                using=ctx.activate_using,
            )
            return BotReply(f"Aktivasi berhasil untuk {cust.username} (plan_id={last_pppoe.plan_id}).")

        return BotReply("Perintah tidak dikenal.", reply_markup=_main_menu_markup())
    except asyncio.TimeoutError:
        return BotReply("Timeout saat mengakses NuxBill. Coba lagi.")
    except ValueError as exc:
        return BotReply(str(exc))
    except NuxBillError as exc:
        return BotReply(f"NuxBill error: {exc}")
    except Exception:
        return BotReply("Terjadi kesalahan internal.")


async def handle_callback(ctx: BotContext, data: str) -> CallbackResult:
    try:
        if not data:
            return CallbackResult("Perintah tidak dikenali.", answer="Perintah tidak dikenali")

        if data.startswith("onu_st:"):
            parts = data.split(":", 1)
            customer_id = _parse_int(parts[1], field="Customer ID")
            return await _render_status(ctx, customer_id=customer_id)

        if data.startswith("onu_go:"):
            if ctx.mikrotik is None:
                return CallbackResult("Remote ONU belum dikonfigurasi.", answer="Belum dikonfigurasi")
            parts = data.split(":", 1)
            customer_id = _parse_int(parts[1], field="Customer ID")
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            ip = _extract_pppoe_ip(view)
            if not ip:
                return CallbackResult("IP PPPoE customer tidak ditemukan.", answer="IP tidak ada")
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                return CallbackResult("IP PPPoE customer tidak valid.", answer="IP invalid")
            result = await ctx.mikrotik.ensure_onu_forward(to_address=ip, to_port=80)
            url = f"http://{ctx.mikrotik.onu.ip_public.strip()}:{int(ctx.mikrotik.onu.port_onu)}"
            text = "\n".join(
                [
                    f"Remote ONU siap untuk {cust.username}.",
                    f"Rule: {result.get('action')}",
                    f"URL: {url}",
                ]
            )
            return CallbackResult(text, reply_markup=_build_onu_open_markup(url=url, back_data=f"onu_st:{customer_id}"), answer="OK")

        if data.startswith("cus_onu:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            status = parts[2].strip() or "Active"
            page = _parse_int(parts[3], field="Page")
            if ctx.mikrotik is None:
                return CallbackResult(
                    "Remote ONU belum dikonfigurasi.",
                    reply_markup=_build_customer_detail_markup(
                        customer_id=customer_id,
                        status=status,
                        page=page,
                        onu_enabled=False,
                    ),
                    answer="Belum dikonfigurasi",
                )
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            ip = _extract_pppoe_ip(view)
            if not ip:
                return CallbackResult("IP PPPoE customer tidak ditemukan.", answer="IP tidak ada")
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                return CallbackResult("IP PPPoE customer tidak valid.", answer="IP invalid")
            result = await ctx.mikrotik.ensure_onu_forward(to_address=ip, to_port=80)
            url = f"http://{ctx.mikrotik.onu.ip_public.strip()}:{int(ctx.mikrotik.onu.port_onu)}"
            text = "\n".join(
                [
                    f"Remote ONU siap untuk {cust.username}.",
                    f"Rule: {result.get('action')}",
                    f"URL: {url}",
                ]
            )
            return CallbackResult(
                text,
                reply_markup=_build_onu_open_markup(url=url, back_data=f"cus_v:{customer_id}:{status}:{page}"),
                answer="OK",
            )

        if data.startswith("cus_l:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                raise ValueError("Format callback tidak valid")
            status = parts[1].strip() or "Active"
            page = _parse_int(parts[2], field="Page")
            customers = await ctx.nuxbill.list_customers(status_filter=status, page=page)
            text = f"Daftar customer PPPoE ({status}, page {page}):"
            return CallbackResult(text, reply_markup=_build_customer_list_markup(status=status, page=page, customers=customers))

        if data.startswith("cus_v:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            status = parts[2].strip() or "Active"
            page = _parse_int(parts[3], field="Page")
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            d = view.get("d") or {}
            ip = "-"
            if isinstance(d, dict):
                ip = str(d.get("pppoe_ip") or d.get("pppoe_ip_address") or d.get("ip") or "-")
            act = _first_activation(view)
            recharged_on = str(act.get("recharged_on") or "-") if isinstance(act, dict) else "-"
            expiration = str(act.get("expiration") or "-") if isinstance(act, dict) else "-"
            ctype = str(act.get("type") or cust.service_type or "-") if isinstance(act, dict) else (cust.service_type or "-")
            lines = [
                f"Nama: {cust.fullname or '-'}",
                f"Username: {cust.username or '-'}",
                f"IP: {ip}",
                f"Recharged on: {recharged_on}",
                f"Expiration: {expiration}",
                f"Type: {ctype}",
            ]
            return CallbackResult(
                "\n".join(lines),
                reply_markup=_build_customer_detail_markup(
                    customer_id=customer_id,
                    status=status,
                    page=page,
                    onu_enabled=ctx.mikrotik is not None,
                ),
            )

        if data.startswith("cus_d:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            status = parts[2].strip() or "Active"
            page = _parse_int(parts[3], field="Page")
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            pkgs = ctx.nuxbill.parse_packages(view)
            active = ctx.nuxbill.pick_active_pppoe_package(pkgs)
            if not active:
                return CallbackResult(
                    f"Tidak ada paket PPPoE untuk dinonaktifkan.\n\nUsername: {cust.username}",
                    reply_markup=_build_customer_detail_markup(
                        customer_id=customer_id,
                        status=status,
                        page=page,
                        onu_enabled=ctx.mikrotik is not None,
                    ),
                    answer="Tidak ada paket",
                )
            await ctx.nuxbill.deactivate(customer_id=cust.id, plan_id=active.plan_id)
            return CallbackResult(
                f"Deaktivasi berhasil untuk {cust.username} (plan_id={active.plan_id}).",
                reply_markup=_build_customer_detail_markup(
                    customer_id=customer_id,
                    status=status,
                    page=page,
                    onu_enabled=ctx.mikrotik is not None,
                ),
                answer="Deaktivasi berhasil",
            )

        if data.startswith("rch_c:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                raise ValueError("Format callback tidak valid")
            status = parts[1].strip() or "Active"
            page = _parse_int(parts[2], field="Page")
            customers = await ctx.nuxbill.list_customers(status_filter=status, page=page)
            text = f"Pilih customer ({status}, page {page}):"
            return CallbackResult(text, reply_markup=_build_customers_markup(status=status, page=page, customers=customers))

        if data.startswith("rch_selc:"):
            parts = data.split(":", 1)
            customer_id = _parse_int(parts[1], field="Customer ID")
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            page = 1
            plans = await ctx.nuxbill.list_pppoe_plans(page=page)
            text = f"Customer: {cust.username}\nPilih paket (page {page}):"
            return CallbackResult(text, reply_markup=_build_plans_markup(customer_id=customer_id, page=page, plans=plans))

        if data.startswith("rch_pl:"):
            parts = data.split(":", 2)
            if len(parts) != 3:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            page = _parse_int(parts[2], field="Page")
            plans = await ctx.nuxbill.list_pppoe_plans(page=page)
            text = f"Pilih paket (page {page}):"
            return CallbackResult(text, reply_markup=_build_plans_markup(customer_id=customer_id, page=page, plans=plans))

        if data.startswith("rch_pay:"):
            parts = data.split(":", 4)
            if len(parts) != 5:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            plan_id = _parse_int(parts[2], field="Plan ID")
            server = _b64d(parts[3])
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            page = _parse_int(parts[4], field="Page")
            text = f"Customer: {cust.username}\nPaket: plan_id={plan_id}\nPilih pembayaran:"
            return CallbackResult(
                text,
                reply_markup=_build_payment_markup(customer_id=customer_id, plan_id=plan_id, server=server, page=page),
                answer="Pilih pembayaran",
            )

        if data.startswith("rch_do:"):
            parts = data.split(":", 5)
            if len(parts) != 6:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            plan_id = _parse_int(parts[2], field="Plan ID")
            server = _b64d(parts[3])
            using = _normalize_using(parts[4])
            page = _parse_int(parts[5], field="Page")
            await ctx.nuxbill.recharge_by_plan_id(
                customer_id=customer_id,
                plan_id=plan_id,
                server=server,
                using=using,
            )
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            text = f"Recharge berhasil untuk {cust.username} (plan_id={plan_id}) via {_using_label(using)}."
            return CallbackResult(
                text,
                reply_markup=_inline_keyboard(
                    [
                        [{"text": "Recharge lagi", "callback_data": "rch_c:Active:1"}],
                        [{"text": "Pilih paket lagi", "callback_data": f"rch_pl:{customer_id}:{page}"}],
                    ]
                ),
                answer="Recharge berhasil",
            )

        return CallbackResult("Perintah tidak dikenali.", answer="Perintah tidak dikenali")
    except asyncio.TimeoutError:
        return CallbackResult("Timeout saat mengakses NuxBill. Coba lagi.", answer="Timeout")
    except ValueError as exc:
        return CallbackResult(str(exc), answer=str(exc)[:150])
    except NuxBillError as exc:
        return CallbackResult(f"NuxBill error: {exc}", answer="NuxBill error")
    except MikrotikError as exc:
        return CallbackResult(f"Mikrotik error: {exc}", answer="Mikrotik error")
    except Exception:
        return CallbackResult("Terjadi kesalahan internal.", answer="Error")
