"""DeviceMind switch 平台：把 type=switch（或 other）的设备注册为 HA 开关实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("switch", [])
    await add_entities_with_state(hass, devices, DeviceMindSwitch, async_add_entities)


class DeviceMindSwitch(DeviceMindEntityMixin, SwitchEntity):
    """一个由设备协议 JSON 驱动的开关实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        SwitchEntity.__init__(self)
        self._init_device(hass, device)
        self._is_on = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs) -> None:
        await self._send("turn_on")
        self._is_on = True

    async def async_turn_off(self, **kwargs) -> None:
        await self._send("turn_off")
        self._is_on = False

    def update_from_state(self, payload: dict[str, Any]) -> None:
        power = payload.get("power")
        if power is not None:
            self._is_on = power in ("on", "ON", "1", 1, True)
