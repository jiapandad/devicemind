"""DeviceMind sensor 平台：把 type=sensor 的设备协议注册为 HA 传感器实体。

传感器是只读设备，读数通过 MQTT 状态回传获得：设备声明 control.state_topic，
集成订阅后把 payload 字段映射为 native_value。
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("sensor", [])
    await add_entities_with_state(hass, devices, DeviceMindSensor, async_add_entities)


class DeviceMindSensor(DeviceMindEntityMixin, SensorEntity):
    """一个由设备协议 JSON 驱动的传感器实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        SensorEntity.__init__(self)
        self._init_device(hass, device)
        self._value: Any = None

        # 确定从状态 payload 里读哪个字段（state_map 的第一个键）
        state_map = (device.get("control") or {}).get("state_map") or {}
        self._state_field = next(iter(state_map), None) if state_map else None

    @property
    def native_value(self) -> Any:
        return self._value

    def update_from_state(self, payload: dict[str, Any]) -> None:
        if self._state_field is not None and self._state_field in payload:
            self._value = payload[self._state_field]
        elif payload:
            self._value = next(iter(payload.values()))
