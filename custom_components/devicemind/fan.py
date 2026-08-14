"""DeviceMind fan 平台：把 type=fan 的设备协议注册为 HA 风扇实体。

动作映射：
- 开关 -> turn_on / turn_off
- 调速 -> set_fan_speed（经 mapping.map_fan_speed 做百分比->档位/范围转换）
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN
from .mapping import map_fan_speed


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("fan", [])
    await add_entities_with_state(hass, devices, DeviceMindFan, async_add_entities)


class DeviceMindFan(DeviceMindEntityMixin, FanEntity):
    """一个由设备协议 JSON 驱动的风扇实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        FanEntity.__init__(self)
        self._init_device(hass, device)

        self._is_on = False
        self._percentage: int | None = None

        self._has_speed = self._has_capability("fan_speed")
        self._fan_spec = self._cap_property("fan_speed", "fan_speed") or {}

        features = FanEntityFeature.SET_SPEED if self._has_speed else 0
        self._attr_supported_features = features

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def percentage(self) -> int | None:
        return self._percentage

    async def async_turn_on(self, percentage: int | None = None, **kwargs) -> None:
        await self._send("turn_on")
        self._is_on = True
        if percentage is not None and self._has_speed:
            await self._set_speed(percentage)

    async def async_turn_off(self, **kwargs) -> None:
        await self._send("turn_off")
        self._is_on = False

    async def async_set_percentage(self, percentage: int) -> None:
        if not self._has_speed:
            return
        await self._set_speed(percentage)

    async def _set_speed(self, percentage: int) -> None:
        """HA 百分比 -> 设备 fan_speed 值（档位或范围），发 set_fan_speed 指令。"""
        speed = map_fan_speed(percentage, self._fan_spec)
        await self._send("set_fan_speed", {"fan_speed": speed})
        self._percentage = percentage
