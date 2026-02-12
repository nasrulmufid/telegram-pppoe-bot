from __future__ import annotations

import re


_USERNAME_RE = re.compile(r"^[A-Za-z0-9:+_.@-]{2,55}$")


def validate_username(value: str) -> str:
    v = value.strip()
    if not _USERNAME_RE.match(v):
        raise ValueError("Username tidak valid")
    return v


def validate_plan_query(value: str) -> str:
    v = value.strip()
    if len(v) < 1 or len(v) > 64:
        raise ValueError("Nama paket tidak valid")
    return v


def validate_page(value: str) -> int:
    v = value.strip()
    if not v.isdigit():
        raise ValueError("Page harus angka")
    page = int(v)
    if page < 1 or page > 9999:
        raise ValueError("Page tidak valid")
    return page
