from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str]


def parse_command(text: str) -> ParsedCommand | None:
    t = (text or "").strip()
    if not t.startswith("/"):
        return None

    parts = t.split()
    if not parts:
        return None

    cmd = parts[0][1:]
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    cmd = cmd.strip().lower()
    if not cmd:
        return None
    return ParsedCommand(name=cmd, args=parts[1:])
