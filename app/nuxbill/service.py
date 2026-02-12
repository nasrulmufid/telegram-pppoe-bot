from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

from cachetools import TTLCache

from app.nuxbill.client import NuxBillClient, NuxBillError


@dataclass(frozen=True)
class Customer:
    id: int
    username: str
    fullname: str
    status: str
    service_type: Optional[str]
    pppoe_username: Optional[str]


@dataclass(frozen=True)
class Package:
    id: int
    plan_id: int
    type: str
    namebp: Optional[str]
    status: str
    routers: Optional[str]
    expiration: Optional[str]
    time: Optional[str]


@dataclass(frozen=True)
class Plan:
    id: int
    name_plan: str
    routers: Optional[str]
    is_radius: Optional[int]
    type: Optional[str]

    def server_name(self) -> str:
        if self.is_radius == 1:
            return "radius"
        if self.routers:
            return self.routers
        return "radius"


class NuxBillService:
    def __init__(self, client: NuxBillClient) -> None:
        self._client = client
        self._cache_customers_list: TTLCache = TTLCache(maxsize=200, ttl=15)
        self._cache_customer_view: TTLCache = TTLCache(maxsize=500, ttl=30)
        self._cache_pppoe_plans_search: TTLCache = TTLCache(maxsize=200, ttl=300)
        self._cache_pppoe_plans_list: TTLCache = TTLCache(maxsize=200, ttl=60)

    async def list_customers(self, *, status_filter: str, search: str = "", page: int = 1) -> list[dict[str, Any]]:
        cache_key = f"customers:{status_filter}:{search}:{page}"
        cached = self._cache_customers_list.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(
            r="customers",
            params={"filter": status_filter, "search": search, "order": "username", "orderby": "asc", "p": page},
        )
        self._client.require_success(payload)
        result = payload.get("result") or {}
        customers = result.get("d") or []
        if not isinstance(customers, list):
            customers = []
        self._cache_customers_list[cache_key] = customers
        return customers

    async def get_customer_view_by_username(self, username: str) -> dict[str, Any]:
        cache_key = f"customer_viewu:{username}"
        cached = self._cache_customer_view.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(r=f"customers/viewu/{username}")
        self._client.require_success(payload)
        result = payload.get("result") or {}
        self._cache_customer_view[cache_key] = result
        return result

    async def get_customer_view_by_id(self, customer_id: int) -> dict[str, Any]:
        cache_key = f"customer_view:{customer_id}"
        cached = self._cache_customer_view.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(r=f"customers/view/{customer_id}/activation")
        self._client.require_success(payload)
        result = payload.get("result") or {}
        self._cache_customer_view[cache_key] = result
        return result

    @staticmethod
    def parse_customer(view_result: dict[str, Any]) -> Customer:
        d = view_result.get("d") or {}
        try:
            return Customer(
                id=int(d["id"]),
                username=str(d.get("username") or ""),
                fullname=str(d.get("fullname") or ""),
                status=str(d.get("status") or ""),
                service_type=(d.get("service_type") or None),
                pppoe_username=(d.get("pppoe_username") or None),
            )
        except Exception as exc:
            raise NuxBillError(f"Format data customer tidak dikenali: {exc!r}") from exc

    @staticmethod
    def parse_packages(view_result: dict[str, Any]) -> list[Package]:
        pkgs_raw = view_result.get("packages") or []
        if not isinstance(pkgs_raw, list):
            return []
        pkgs: list[Package] = []
        for item in pkgs_raw:
            if not isinstance(item, dict):
                continue
            try:
                pkgs.append(
                    Package(
                        id=int(item.get("id") or 0),
                        plan_id=int(item.get("plan_id") or 0),
                        type=str(item.get("type") or ""),
                        namebp=(item.get("namebp") or None),
                        status=str(item.get("status") or ""),
                        routers=(item.get("routers") or None),
                        expiration=(item.get("expiration") or None),
                        time=(item.get("time") or None),
                    )
                )
            except Exception:
                continue
        pkgs.sort(key=lambda p: p.id, reverse=True)
        return pkgs

    @staticmethod
    def pick_active_pppoe_package(packages: list[Package]) -> Optional[Package]:
        for p in packages:
            if p.type.upper() == "PPPOE" and p.status.lower() == "on":
                return p
        for p in packages:
            if p.type.upper() == "PPPOE":
                return p
        return None

    async def search_pppoe_plans(self, query: str) -> list[Plan]:
        cache_key = f"pppoe_plans:{query.lower()}"
        cached = self._cache_pppoe_plans_search.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(r="services/pppoe", params={"name": query, "p": 1})
        self._client.require_success(payload)
        result = payload.get("result") or {}
        plans_raw = result.get("d") or []
        plans: list[Plan] = []
        if isinstance(plans_raw, list):
            for item in plans_raw:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").upper() != "PPPOE":
                    continue
                try:
                    plans.append(
                        Plan(
                            id=int(item.get("id") or 0),
                            name_plan=str(item.get("name_plan") or ""),
                            routers=(item.get("routers") or None),
                            is_radius=(int(item["is_radius"]) if item.get("is_radius") is not None else None),
                            type=(item.get("type") or None),
                        )
                    )
                except Exception:
                    continue

        self._cache_pppoe_plans_search[cache_key] = plans
        return plans

    async def list_pppoe_plans(self, *, page: int = 1, name: str = "") -> list[Plan]:
        cache_key = f"pppoe_plans_list:{page}:{name.lower()}"
        cached = self._cache_pppoe_plans_list.get(cache_key)
        if cached is not None:
            return cached

        payload = await self._client.get(r="services/pppoe", params={"name": name, "p": page})
        self._client.require_success(payload)
        result = payload.get("result") or {}
        plans_raw = result.get("d") or []
        plans: list[Plan] = []
        if isinstance(plans_raw, list):
            for item in plans_raw:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").upper() != "PPPOE":
                    continue
                try:
                    plans.append(
                        Plan(
                            id=int(item.get("id") or 0),
                            name_plan=str(item.get("name_plan") or ""),
                            routers=(item.get("routers") or None),
                            is_radius=(int(item["is_radius"]) if item.get("is_radius") is not None else None),
                            type=(item.get("type") or None),
                        )
                    )
                except Exception:
                    continue
        self._cache_pppoe_plans_list[cache_key] = plans
        return plans

    async def find_pppoe_plan_best_match(self, query: str) -> Plan:
        plans = await self.search_pppoe_plans(query)
        if not plans:
            raise NuxBillError("Paket PPPoE tidak ditemukan")

        q = query.strip().lower()
        exact = [p for p in plans if p.name_plan.strip().lower() == q]
        if exact:
            return exact[0]

        contains = [p for p in plans if q in p.name_plan.strip().lower()]
        if contains:
            contains.sort(key=lambda p: len(p.name_plan))
            return contains[0]

        return plans[0]

    async def recharge(self, *, customer_id: int, plan: Plan, using: str) -> None:
        payload = await self._client.post_form(
            r="plan/recharge-post",
            data={"id_customer": customer_id, "server": plan.server_name(), "plan": plan.id, "using": using, "svoucher": ""},
        )
        self._client.require_success(payload)

    async def recharge_by_plan_id(self, *, customer_id: int, plan_id: int, server: str, using: str) -> None:
        payload = await self._client.post_form(
            r="plan/recharge-post",
            data={"id_customer": customer_id, "server": server, "plan": plan_id, "using": using, "svoucher": ""},
        )
        self._client.require_success(payload)

    async def deactivate(self, *, customer_id: int, plan_id: int) -> None:
        payload = await self._client.get(r=f"customers/deactivate/{customer_id}/{plan_id}")
        self._client.require_success(payload)

    async def sync(self, *, customer_id: int) -> None:
        payload = await self._client.get(r=f"customers/sync/{customer_id}")
        self._client.require_success(payload)

    async def get_pppoe_customers_page_with_packages(
        self,
        *,
        page: int,
        include_inactive: bool,
        concurrency: int = 10,
        time_budget_sec: float = 8.0,
    ) -> list[tuple[Customer, Optional[Package]]]:
        async def _inner() -> list[tuple[Customer, Optional[Package]]]:
            customers_active = await self.list_customers(status_filter="Active", page=page)
            customers_inactive: list[dict[str, Any]] = []
            if include_inactive:
                customers_inactive = await self.list_customers(status_filter="Inactive", page=page)
            customers_raw = customers_active + customers_inactive

            pppoe_customers = []
            for c in customers_raw:
                if not isinstance(c, dict):
                    continue
                if str(c.get("service_type") or "").upper() != "PPPOE":
                    continue
                try:
                    pppoe_customers.append(int(c["id"]))
                except Exception:
                    continue

            sem = asyncio.Semaphore(concurrency)

            async def _fetch(cid: int) -> tuple[Customer, Optional[Package]]:
                async with sem:
                    view = await self.get_customer_view_by_id(cid)
                    cust = self.parse_customer(view)
                    pkgs = self.parse_packages(view)
                    pkg = self.pick_active_pppoe_package(pkgs)
                    return cust, pkg

            tasks = [_fetch(cid) for cid in pppoe_customers]
            results: list[tuple[Customer, Optional[Package]]] = []
            if tasks:
                for coro in asyncio.as_completed(tasks):
                    results.append(await coro)
            results.sort(key=lambda x: x[0].username.lower())
            return results

        return await asyncio.wait_for(_inner(), timeout=time_budget_sec)
