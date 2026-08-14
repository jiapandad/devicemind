"""DeviceMind vacuum 平台：把 type=vacuum 的设备协议注册为 HA 扫地机实体。

动作映射（复用设备协议的 turn_on/turn_off/stop）：
- 开始清扫 -> turn_on
- 停止清扫 -> turn_off
- 暂停 -> stop（若设备无 stop 动作则降级为 turn_off）
- 回充 -> turn_off
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    STATE_CLEANING,
    STATE_DOCKED,
    STATE_PAUSED,
    VacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("vacuum", [])
    await add_entities_with_state(hass, devices, DeviceMindVacuum, async_add_entities)


class DeviceMindVacuum(DeviceMindEntityMixin, VacuumEntity):
    """一个由设备协议 JSON 驱动的扫地机实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        VacuumEntity.__init__(self)
        self._init_device(hass, device)
        self._attr_state = STATE_DOCKED
        self._attr_supported_features = (
            VacuumEntityFeature.START
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.RETURN_HOME
        )

    async def async_start(self) -> None:
        await self._send("turn_on")
        self._attr_state = STATE_CLEANING

    async def async_stop(self, **kwargs) -> None:
        await self._send("turn_off")
        self._attr_state = STATE_DOCKED

    async def async_pause(self) -> None:
        await self._send("stop")
        self._attr_state = STATE_PAUSED

    async def async_return_to_base(self, **kwargs) -> None:
        await self._send("turn_off")
        self._attr_state = STATE_DOCKED
