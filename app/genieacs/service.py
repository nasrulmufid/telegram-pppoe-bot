from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.genieacs.client import GenieAcsClient, GenieAcsError


@dataclass(frozen=True)
class WifiParams:
    ssid_path: str = "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.SSID"
    password_path: str = "InternetGatewayDevice.LANDevice.1.WLANConfiguration.1.KeyPassphrase"


class GenieAcsService:
    def __init__(self, client: GenieAcsClient) -> None:
        self._client = client
        self._wifi = WifiParams()

    @property
    def wifi(self) -> WifiParams:
        return self._wifi

    @staticmethod
    def _get_value(node: Any) -> Optional[str]:
        if isinstance(node, dict):
            v = node.get("_value")
            if v is None:
                return None
            return str(v)
        return None

    @staticmethod
    def _get_path(device: dict[str, Any], path: str) -> Any:
        cur: Any = device
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur

    async def get_virtual_param(self, *, device_id: str, name: str) -> str:
        dev = await self._client.find_device_by_id(device_id)
        node = self._get_path(dev, f"VirtualParameters.{name}")
        value = self._get_value(node)
        if value is None or not value.strip():
            raise GenieAcsError(f"Virtual parameter {name} tidak ditemukan")
        return value.strip()

    async def set_wifi_ssid(self, *, device_id: str, ssid: str) -> int:
        pv = [[self._wifi.ssid_path, ssid, "xsd:string"]]
        status, _ = await self._client.post_task_set_params(device_id=device_id, parameter_values=pv, connection_request=True)
        return status

    async def set_wifi_password(self, *, device_id: str, password: str) -> int:
        pv = [[self._wifi.password_path, password, "xsd:string"]]
        status, _ = await self._client.post_task_set_params(device_id=device_id, parameter_values=pv, connection_request=True)
        return status

