"""DeviceMind light 平台：把 type=light 的设备协议注册为 HA 灯实体。

控制时读取设备协议里的 control.commands，通过 runtime.build_command
构建指令，再经 HA 的 mqtt.publish 服务发出 MQTT 指令（复用用户已配置
的 MQTT Broker）。动作名由 runtime.match_action 模糊匹配，容忍 LLM
编译出的非规范命名。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .runtime import build_command, command_payload_str

_LOGGER = logging.getLogger(__name__)


def _has_capability(device: dict[str, Any], name: str) -> bool:
    return any(cap.get("name") == name for cap in device.get("capabilities", []))


def _cap_property(device: dict[str, Any], cap_name: str, prop_name: str) -> dict[str, Any] | None:
    for cap in device.get("capabilities", []):
        if cap.get("name") == cap_name:
            return (cap.get("properties") or {}).get(prop_name)
    return None


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("light", [])
    async_add_entities([DeviceMindLight(hass, device) for device in devices])


class DeviceMindLight(LightEntity):
    """一个由设备协议 JSON 驱动的灯实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        self.hass = hass
        self._device = device
        self._attr_name = device.get("name", device.get("id", ""))
        self._attr_unique_id = f"devicemind_{device.get('id')}"
        self._is_on = False
        self._brightness: int | None = None

        self._has_brightness = _has_capability(device, "brightness")

        # 声明支持的色彩模式，让 HA 前端正确渲染亮度调节条
        self._attr_supported_color_modes = (
            {ColorMode.BRIGHTNESS} if self._has_brightness else {ColorMode.ONOFF}
        )

    # ------------------------------------------------------------------
    # 状态属性
    # ------------------------------------------------------------------
    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness

    @property
    def color_mode(self) -> str | None:
        return ColorMode.BRIGHTNESS if self._has_brightness else ColorMode.ONOFF

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    async def async_turn_on(self, **kwargs) -> None:
        # 1. 发送开关指令
        await self._send("turn_on")
        self._is_on = True

        # 2. 若携带亮度，单独发 set_brightness 指令（而非塞进 turn_on payload）
        brightness = kwargs.get("brightness")
        if brightness is not None and self._has_brightness:
            scaled = self._scale_brightness(brightness)
            await self._send("set_brightness", {"brightness": scaled})
            self._brightness = brightness

    async def async_turn_off(self, **kwargs) -> None:
        await self._send("turn_off")
        self._is_on = False

    # ------------------------------------------------------------------
    # 指令发送
    # ------------------------------------------------------------------
    async def _send(self, action: str, params: dict[str, Any] | None = None) -> None:
        try:
            command = build_command(self._device, action, params)
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

    def _scale_brightness(self, ha_brightness: int) -> int:
        """HA 亮度 0-255 -> 设备协议亮度范围（默认 1-100）。"""
        spec = _cap_property(self._device, "brightness", "brightness") or {}
        lo = int(spec.get("min", 1))
        hi = int(spec.get("max", 100))
        return max(lo, min(hi, round(lo + (ha_brightness / 255) * (hi - lo))))
