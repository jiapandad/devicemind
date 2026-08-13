"""DeviceMind cover 平台：把 type=cover 的设备协议注册为 HA 窗帘/卷帘实体。

动作映射：
- 打开 -> open
- 关闭 -> close
- 停止 -> stop
- 设置开合度 -> set_position（需设备声明 position 能力）
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("cover", [])
    async_add_entities([DeviceMindCover(hass, device) for device in devices])


class DeviceMindCover(DeviceMindEntityMixin, CoverEntity):
    """一个由设备协议 JSON 驱动的窗帘实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        CoverEntity.__init__(self)
        self._init_device(hass, device)
        self._is_closed = False
        self._position: int | None = None

        self._has_position = self._has_capability("position")
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if self._has_position:
            features |= CoverEntityFeature.SET_POSITION
        self._attr_supported_features = features

    # ------------------------------------------------------------------
    # 状态属性
    # ------------------------------------------------------------------
    @property
    def is_closed(self) -> bool:
        return self._is_closed

    @property
    def current_cover_position(self) -> int | None:
        return self._position

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------
    async def async_open_cover(self, **kwargs) -> None:
        await self._send("open")
        self._is_closed = False
        self._position = 100

    async def async_close_cover(self, **kwargs) -> None:
        await self._send("close")
        self._is_closed = True
        self._position = 0

    async def async_stop_cover(self, **kwargs) -> None:
        await self._send("stop")

    async def async_set_cover_position(self, **kwargs) -> None:
        position = kwargs.get("position")
        if position is None:
            return
        await self._send("set_position", {"position": position})
        self._position = position
        self._is_closed = position == 0
