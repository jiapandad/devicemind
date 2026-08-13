"""DeviceMind humidifier 平台：把 type=humidifier 的设备协议注册为 HA 加湿器实体。

动作映射：
- 开关 -> turn_on / turn_off
- 目标湿度 -> set_humidity（若设备声明 target_humidity 能力）
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import HumidifierEntity
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("humidifier", [])
    async_add_entities([DeviceMindHumidifier(hass, device) for device in devices])


class DeviceMindHumidifier(DeviceMindEntityMixin, HumidifierEntity):
    """一个由设备协议 JSON 驱动的加湿器实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        HumidifierEntity.__init__(self)
        self._init_device(hass, device)
        self._is_on = False
        self._target_humidity: int | None = None

        spec = self._cap_property("target_humidity", "target_humidity") or {}
        self._attr_min_humidity = int(spec.get("min", 30))
        self._attr_max_humidity = int(spec.get("max", 80))

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def target_humidity(self) -> int | None:
        return self._target_humidity

    async def async_turn_on(self, **kwargs) -> None:
        await self._send("turn_on")
        self._is_on = True

    async def async_turn_off(self, **kwargs) -> None:
        await self._send("turn_off")
        self._is_on = False

    async def async_set_humidity(self, humidity: int) -> None:
        await self._send("set_humidity", {"humidity": humidity})
        self._target_humidity = humidity
