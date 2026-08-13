"""DeviceMind switch 平台：把 type=switch（或 other）的设备注册为 HA 开关实体。"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .runtime import build_command, command_payload_str

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("switch", [])
    async_add_entities([DeviceMindSwitch(hass, device) for device in devices])


class DeviceMindSwitch(SwitchEntity):
    """一个由设备协议 JSON 驱动的开关实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        self.hass = hass
        self._device = device
        self._attr_name = device.get("name", device.get("id", ""))
        self._attr_unique_id = f"devicemind_{device.get('id')}"
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

    async def _send(self, action: str) -> None:
        try:
            command = build_command(self._device, action)
        except ValueError as exc:
            _LOGGER.warning("设备 %s 无法构建指令 %s: %s", self._attr_name, action, exc)
            return

        if command.topic is None:
            _LOGGER.warning("设备 %s 未定义指令 %s", self._attr_name, action)
            return

        await self.hass.services.async_call(
            "mqtt",
            "publish",
            {"topic": command.topic, "payload": command_payload_str(command)},
        )
