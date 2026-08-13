"""DeviceMind climate 平台：把 type=climate 的设备协议注册为 HA 空调实体。

映射关系：
- 设备协议 mode 能力（制冷/制热/自动...）-> HA HVACMode
- 设备协议 temperature 能力 -> HA target_temperature
- 设备协议 fan_speed 能力 -> HA fan_mode

模式值通过 mapping.normalize_hvac_key / reverse_hvac_value 做双向转换，
反向控制时优先保留设备协议里的原始枚举值（中文/英文原文）。
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity, HVACMode
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin
from .const import DOMAIN
from .mapping import normalize_hvac_key, reverse_hvac_value

_KEY_TO_HVAC = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "auto": HVACMode.AUTO,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
    "heat_cool": HVACMode.HEAT_COOL,
}

_HVAC_TO_KEY = {v: k for k, v in _KEY_TO_HVAC.items()}


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("climate", [])
    async_add_entities([DeviceMindClimate(hass, device) for device in devices])


class DeviceMindClimate(DeviceMindEntityMixin, ClimateEntity):
    """一个由设备协议 JSON 驱动的空调实体。"""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        ClimateEntity.__init__(self)
        self._init_device(hass, device)

        self._has_mode = self._has_capability("mode")
        self._has_fan = self._has_capability("fan_speed")
        self._has_temp = self._has_capability("temperature")

        # 设备声明的原始模式值（反向控制时优先使用）
        self._device_modes: list[Any] = self._cap_enum("mode")

        # 温度单位与范围（默认摄氏度 16-30）
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        temp_spec = self._cap_property("temperature", "temperature") or {}
        self._attr_min_temp = float(temp_spec.get("min", 16))
        self._attr_max_temp = float(temp_spec.get("max", 30))
        self._attr_target_temperature_step = 1.0

        # 支持的模式：优先取 mode 能力的 enum，否则给一组常见默认
        if self._device_modes:
            modes = {_KEY_TO_HVAC[normalize_hvac_key(m)] for m in self._device_modes}
            modes.discard(HVACMode.OFF)
        else:
            modes = {HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO}
        self._attr_hvac_modes = [HVACMode.OFF, *sorted(modes, key=lambda m: m.value)]
        self._attr_hvac_mode = HVACMode.OFF

        # 风速
        self._attr_fan_modes = None
        self._attr_fan_mode = None

        # 支持的功能
        features = 0
        if self._has_temp:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self._has_fan:
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = features

    # ------------------------------------------------------------------
    # 状态属性
    # ------------------------------------------------------------------
    @property
    def current_temperature(self) -> float | None:
        # 状态回传闭环接入前，当前温度未知
        return None

    @property
    def target_temperature(self) -> float | None:
        return self._attr_target_temperature

    @property
    def fan_mode(self) -> str | None:
        return self._attr_fan_mode

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._send("turn_off")
        else:
            key = _HVAC_TO_KEY.get(hvac_mode, "auto")
            # 反向映射：优先返回设备协议里的原始模式值（中文/英文原文）
            value = reverse_hvac_value(key, self._device_modes)
            await self._send("set_mode", {"mode": value})
        self._attr_hvac_mode = hvac_mode

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        await self._send("set_temperature", {"temperature": temperature})
        self._attr_target_temperature = temperature

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self._send("set_fan_speed", {"fan_speed": fan_mode})
        self._attr_fan_mode = fan_mode
