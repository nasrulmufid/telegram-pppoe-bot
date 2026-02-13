from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


class MikrotikError(RuntimeError):
    pass


@dataclass(frozen=True)
class MikrotikConfig:
    host: str
    username: str
    password: str
    port: int = 8728


class MikrotikClient:
    def __init__(self, config: MikrotikConfig) -> None:
        self._config = config

    def ensure_onu_forward_rule(
        self,
        *,
        ip_public: str,
        port_onu: int,
        comment: str,
        to_address: str,
        to_port: int = 80,
    ) -> dict[str, Any]:
        if not ip_public.strip():
            raise MikrotikError("IP_PUBLIC kosong")
        if port_onu <= 0:
            raise MikrotikError("PORT_ONU tidak valid")
        if not comment.strip():
            raise MikrotikError("COMMENT_FIREWALL kosong")
        if not to_address.strip():
            raise MikrotikError("IP customer tidak ditemukan")

        try:
            import routeros_api
        except Exception as exc:
            raise MikrotikError("Library routeros-api belum terpasang") from exc

        pool = routeros_api.RouterOsApiPool(
            self._config.host,
            username=self._config.username,
            password=self._config.password,
            port=self._config.port,
            plaintext_login=True,
        )
        try:
            api = pool.get_api()
            nat = api.get_resource("/ip/firewall/nat")
            found = nat.get(comment=comment)
            rule_id: Optional[str] = None
            if isinstance(found, list) and found:
                first = found[0]
                if isinstance(first, dict):
                    rule_id = str(first.get("id") or first.get(".id") or "")
                    if not rule_id:
                        rule_id = None

            payload = {
                "chain": "dstnat",
                "protocol": "tcp",
                "dst_address": ip_public.strip(),
                "dst_port": str(int(port_onu)),
                "action": "dst-nat",
                "to_addresses": to_address.strip(),
                "to_ports": str(int(to_port)),
                "comment": comment.strip(),
                "disabled": "no",
            }

            if rule_id is None:
                nat.add(**payload)
                action = "created"
            else:
                nat.set(id=rule_id, **payload)
                action = "updated"
            return {"action": action, "comment": comment.strip(), "dst": f"{ip_public.strip()}:{int(port_onu)}"}
        except Exception as exc:
            raise MikrotikError(str(exc)) from exc
        finally:
            pool.disconnect()
