from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from typing import Any, Optional

from app.nuxbill.client import NuxBillError
from app.nuxbill.service import NuxBillService, Package, Plan
from app.security.validation import validate_page, validate_plan_query, validate_username


@dataclass(frozen=True)
class BotContext:
    nuxbill: NuxBillService
    recharge_using: str
    activate_using: str


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
        "/customer [page] - daftar customer PPPoE (paginasi)\n"
        "/status <username> - status detail customer\n"
        "/recharge - pilih customer & paket (interaktif)\n"
        "/recharge <username> <paket> - recharge customer dengan paket PPPoE\n"
        "/activate <username> - aktifkan kembali customer\n"
        "/deactivate <username> - nonaktifkan customer\n"
        "/help - bantuan"
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


def _build_plans_markup(*, customer_id: int, page: int, plans: list[Plan]) -> dict[str, Any]:
    buttons: list[dict[str, str]] = []
    for p in plans:
        label = p.name_plan.strip() or f"plan_id={p.id}"
        server = p.server_name()
        buttons.append(
            {
                "text": label[:64],
                "callback_data": f"rch_exec:{customer_id}:{p.id}:{_b64e(server)}",
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


async def handle_command(ctx: BotContext, name: str, args: list[str]) -> BotReply:
    try:
        if name in ("help", "start"):
            return BotReply(help_text())

        if name == "status":
            if len(args) != 1:
                return BotReply("Format: /status <username>\n\n" + help_text())
            username = validate_username(args[0])
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            pkgs = ctx.nuxbill.parse_packages(view)
            pppoe = ctx.nuxbill.pick_active_pppoe_package(pkgs)
            lines = [
                f"Nama: {cust.fullname}",
                f"Username: {cust.username}",
                f"Status akun: {cust.status}",
            ]
            if cust.pppoe_username:
                lines.append(f"PPPoE username: {cust.pppoe_username}")
            if cust.service_type:
                lines.append(f"Service type: {cust.service_type}")
            lines.append(f"Paket: {_fmt_pkg(pppoe)}")
            return BotReply("\n".join(lines))

        if name == "customer":
            page = 1
            if args:
                if len(args) != 1:
                    return BotReply("Format: /customer [page]\n\n" + help_text())
                page = validate_page(args[0])
            items = await ctx.nuxbill.get_pppoe_customers_page_with_packages(
                page=page,
                include_inactive=True,
                concurrency=10,
                time_budget_sec=8.5,
            )
            if not items:
                return BotReply("Tidak ada customer PPPoE pada page ini.")
            header = f"Daftar customer PPPoE (page {page}):"
            lines = [header]
            for cust, pkg in items[:30]:
                lines.append(f"- {cust.fullname} | {cust.username} | {cust.status} | {_fmt_pkg(pkg)}")
            if len(items) > 30:
                lines.append(f"... dan {len(items) - 30} lainnya")
            return BotReply("\n".join(lines))

        if name == "recharge":
            if not args:
                status = "Active"
                page = 1
                customers = await ctx.nuxbill.list_customers(status_filter=status, page=page)
                text = f"Pilih customer ({status}, page {page}):"
                return BotReply(text, reply_markup=_build_customers_markup(status=status, page=page, customers=customers))
            if len(args) < 2:
                return BotReply("Format: /recharge <username> <paket>\n\n" + help_text())
            username = validate_username(args[0])
            paket = validate_plan_query(" ".join(args[1:]))
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            plan = await ctx.nuxbill.find_pppoe_plan_best_match(paket)
            await ctx.nuxbill.recharge(customer_id=cust.id, plan=plan, using=ctx.recharge_using)
            return BotReply(f"Recharge berhasil untuk {cust.username} dengan paket {plan.name_plan}.")

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

        return BotReply("Perintah tidak dikenal.\n\n" + help_text())
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

        if data.startswith("rch_exec:"):
            parts = data.split(":", 3)
            if len(parts) != 4:
                raise ValueError("Format callback tidak valid")
            customer_id = _parse_int(parts[1], field="Customer ID")
            plan_id = _parse_int(parts[2], field="Plan ID")
            server = _b64d(parts[3])
            await ctx.nuxbill.recharge_by_plan_id(
                customer_id=customer_id,
                plan_id=plan_id,
                server=server,
                using=ctx.recharge_using,
            )
            view = await ctx.nuxbill.get_customer_view_by_id(customer_id)
            cust = ctx.nuxbill.parse_customer(view)
            text = f"Recharge berhasil untuk {cust.username} (plan_id={plan_id})."
            return CallbackResult(
                text,
                reply_markup=_inline_keyboard([[{"text": "Recharge lagi", "callback_data": "rch_c:Active:1"}]]),
                answer="Recharge berhasil",
            )

        return CallbackResult("Perintah tidak dikenali.", answer="Perintah tidak dikenali")
    except asyncio.TimeoutError:
        return CallbackResult("Timeout saat mengakses NuxBill. Coba lagi.", answer="Timeout")
    except ValueError as exc:
        return CallbackResult(str(exc), answer=str(exc)[:150])
    except NuxBillError as exc:
        return CallbackResult(f"NuxBill error: {exc}", answer="NuxBill error")
    except Exception:
        return CallbackResult("Terjadi kesalahan internal.", answer="Error")
