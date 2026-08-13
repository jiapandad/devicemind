"""DeviceMind sensor 平台：把 type=sensor 的设备注册为 HA 传感器实体。

传感器是只读设备，真实数据回传依赖 MQTT 订阅（get_state 指令 + 响应 topic），
骨架阶段先以 unknown 状态注册，状态回传闭环留待实机联调。
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("sensor", [])
    async_add_entities([DeviceMindSensor(device) for device in devices])


class DeviceMindSensor(SensorEntity):
    """一个由设备协议 JSON 驱动的传感器实体。"""

    def __init__(self, device: dict[str, Any]) -> None:
        self._device = device
        self._attr_name = device.get("name", device.get("id", ""))
        self._attr_unique_id = f"devicemind_{device.get('id')}"

    @property
    def native_value(self):
        # TODO: 接入 MQTT 状态订阅后，返回真实读数
        return None
