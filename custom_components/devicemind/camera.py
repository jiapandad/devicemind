"""DeviceMind camera 平台：把 type=camera 的设备协议注册为 HA 摄像头实体。

摄像头是流媒体设备，控制通道与 MQTT 开关类设备不同（通常走 RTSP/HTTP 流）。
本骨架先注册 entity，流媒体地址读取设备协议 control 里的 stream_url 字段
（若说明书编译时提取到）；截图/推流待后续扩展。
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("camera", [])
    async_add_entities([DeviceMindCamera(device) for device in devices])


class DeviceMindCamera(Camera):
    """一个由设备协议 JSON 驱动的摄像头实体。"""

    def __init__(self, device: dict[str, Any]) -> None:
        super().__init__()
        self._device = device
        self._attr_name = device.get("name", device.get("id", ""))
        self._attr_unique_id = f"devicemind_{device.get('id')}"

    @property
    def stream_source(self) -> str | None:
        control = self._device.get("control") or {}
        source = control.get("stream_url")
        if not source:
            _LOGGER.info("摄像头 %s 未提供 stream_url，请在设备协议中补充", self._attr_name)
        return source
