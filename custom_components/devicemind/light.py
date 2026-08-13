"""DeviceMind light 平台：把 type=light 的设备协议注册为 HA 灯实体。

支持的能力映射（按设备协议 capability 自动识别）：
- power      -> 开关
- brightness -> 亮度调节
- color      -> RGB 颜色
- color_temp -> 色温（Kelvin）

控制时读取设备协议里的 control.commands，通过 runtime.build_command 构建指令，
再经 HA 的 mqtt.publish 服务发出 MQTT 指令（复用用户已配置的 MQTT Broker）。
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("light", [])
    async_add_entities([DeviceMindLight(hass, device) for device in devices])


class DeviceMindLight(DeviceMindEntityMixin, LightEntity):
    """一个由设备协议 JSON 驱动的灯实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        LightEntity.__init__(self)
        self._init_device(hass, device)

        self._is_on = False
        self._brightness: int | None = None
        self._rgb_color: tuple[int, int, int] | None = None
        self._color_temp_kelvin: int | None = None

        self._has_brightness = self._has_capability("brightness")
        self._has_color = self._has_capability("color")
        self._has_color_temp = self._has_capability("color_temp")

        # 声明支持的色彩模式，让 HA 前端正确渲染调节控件
        modes = {ColorMode.ONOFF}
        if self._has_brightness:
            modes.add(ColorMode.BRIGHTNESS)
        if self._has_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        if self._has_color:
            modes.add(ColorMode.RGB)
        self._attr_supported_color_modes = modes

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
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._rgb_color

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._color_temp_kelvin

    @property
    def color_mode(self) -> str | None:
        if self._has_color and self._rgb_color is not None:
            return ColorMode.RGB
        if self._has_color_temp and self._color_temp_kelvin is not None:
            return ColorMode.COLOR_TEMP
        if self._has_brightness:
            return ColorMode.BRIGHTNESS
        return ColorMode.ONOFF

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    async def async_turn_on(self, **kwargs) -> None:
        # 1. 发送开关指令
        await self._send("turn_on")
        self._is_on = True

        # 2. 亮度（单独发 set_brightness，而非塞进 turn_on payload）
        brightness = kwargs.get("brightness")
        if brightness is not None and self._has_brightness:
            scaled = self._scale_brightness(brightness)
            await self._send("set_brightness", {"brightness": scaled})
            self._brightness = brightness

        # 3. 颜色（RGB -> hex 字符串）
        rgb = kwargs.get("rgb_color")
        if rgb is not None and self._has_color:
            hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
            await self._send("set_color", {"color": hex_color})
            self._rgb_color = tuple(rgb)

        # 4. 色温（Kelvin）
        kelvin = kwargs.get("color_temp_kelvin")
        if kelvin is not None and self._has_color_temp:
            await self._send("set_color_temp", {"color_temp": kelvin})
            self._color_temp_kelvin = kelvin

    async def async_turn_off(self, **kwargs) -> None:
        await self._send("turn_off")
        self._is_on = False

    # ------------------------------------------------------------------
    # 指令发送
    # ------------------------------------------------------------------
    def _scale_brightness(self, ha_brightness: int) -> int:
        """HA 亮度 0-255 -> 设备协议亮度范围（默认 1-100）。"""
        spec = self._cap_property("brightness", "brightness") or {}
        lo = int(spec.get("min", 1))
        hi = int(spec.get("max", 100))
        return max(lo, min(hi, round(lo + (ha_brightness / 255) * (hi - lo))))
