from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from app.nuxbill.client import NuxBillError
from app.nuxbill.service import NuxBillService, Package, Plan
from app.security.validation import validate_page, validate_plan_query, validate_username


@dataclass(frozen=True)
class BotContext:
    nuxbill: NuxBillService
    recharge_using: str
    activate_using: str


def help_text() -> str:
    return (
        "Perintah tersedia:\n"
        "/customer [page] - daftar customer PPPoE (paginasi)\n"
        "/status <username> - status detail customer\n"
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


async def handle_command(ctx: BotContext, name: str, args: list[str]) -> str:
    try:
        if name in ("help", "start"):
            return help_text()

        if name == "status":
            if len(args) != 1:
                return "Format: /status <username>\n\n" + help_text()
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
            return "\n".join(lines)

        if name == "customer":
            page = 1
            if args:
                if len(args) != 1:
                    return "Format: /customer [page]\n\n" + help_text()
                page = validate_page(args[0])
            items = await ctx.nuxbill.get_pppoe_customers_page_with_packages(
                page=page,
                include_inactive=True,
                concurrency=10,
                time_budget_sec=8.5,
            )
            if not items:
                return "Tidak ada customer PPPoE pada page ini."
            header = f"Daftar customer PPPoE (page {page}):"
            lines = [header]
            for cust, pkg in items[:30]:
                lines.append(f"- {cust.fullname} | {cust.username} | {cust.status} | {_fmt_pkg(pkg)}")
            if len(items) > 30:
                lines.append(f"... dan {len(items) - 30} lainnya")
            return "\n".join(lines)

        if name == "recharge":
            if len(args) < 2:
                return "Format: /recharge <username> <paket>\n\n" + help_text()
            username = validate_username(args[0])
            paket = validate_plan_query(" ".join(args[1:]))
            view = await ctx.nuxbill.get_customer_view_by_username(username)
            cust = ctx.nuxbill.parse_customer(view)
            plan = await ctx.nuxbill.find_pppoe_plan_best_match(paket)
            await ctx.nuxbill.recharge(customer_id=cust.id, plan=plan, using=ctx.recharge_using)
            return f"Recharge berhasil untuk {cust.username} dengan paket {plan.name_plan}."

        if name == "deactivate":
            if len(args) != 1:
                return "Format: /deactivate <username>\n\n" + help_text()
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
                return "Tidak ada paket PPPoE aktif untuk dinonaktifkan."
            await ctx.nuxbill.deactivate(customer_id=cust.id, plan_id=active.plan_id)
            return f"Deaktivasi berhasil untuk {cust.username} (plan_id={active.plan_id})."

        if name == "activate":
            if len(args) != 1:
                return "Format: /activate <username>\n\n" + help_text()
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
                return f"Customer masih aktif. Sync dijalankan untuk {cust.username}."

            if not last_pppoe:
                return "Tidak ada riwayat paket PPPoE untuk diaktifkan."

            server = last_pppoe.routers or "radius"
            await ctx.nuxbill.recharge_by_plan_id(
                customer_id=cust.id,
                plan_id=last_pppoe.plan_id,
                server=server,
                using=ctx.activate_using,
            )
            return f"Aktivasi berhasil untuk {cust.username} (plan_id={last_pppoe.plan_id})."

        return "Perintah tidak dikenal.\n\n" + help_text()
    except asyncio.TimeoutError:
        return "Timeout saat mengakses NuxBill. Coba lagi."
    except ValueError as exc:
        return str(exc)
    except NuxBillError as exc:
        return f"NuxBill error: {exc}"
    except Exception:
        return "Terjadi kesalahan internal."
