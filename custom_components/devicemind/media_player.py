"""DeviceMind media_player 平台：把 type=media 的设备协议注册为 HA 影音实体。

基础版聚焦音量与开关控制；播放/暂停等媒体控制依赖设备的 play/pause 动作，
当前复用 turn_on/turn_off，流媒体播放列表等高级能力后续扩展。
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("media_player", [])
    await add_entities_with_state(hass, devices, DeviceMindMediaPlayer, async_add_entities)


class DeviceMindMediaPlayer(DeviceMindEntityMixin, MediaPlayerEntity):
    """一个由设备协议 JSON 驱动的影音实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        MediaPlayerEntity.__init__(self)
        self._init_device(hass, device)
        self._attr_state = STATE_OFF
        self._volume: float | None = None

        self._has_volume = self._has_capability("volume")
        features = MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        if self._has_volume:
            features |= MediaPlayerEntityFeature.VOLUME_SET | MediaPlayerEntityFeature.VOLUME_STEP
        self._attr_supported_features = features

    @property
    def volume_level(self) -> float | None:
        return self._volume

    async def async_turn_on(self) -> None:
        await self._send("turn_on")
        self._attr_state = STATE_ON

    async def async_turn_off(self) -> None:
        await self._send("turn_off")
        self._attr_state = STATE_OFF

    async def async_set_volume_level(self, volume: float) -> None:
        # HA 音量 0.0-1.0 -> 设备协议 0-100
        scaled = int(round(volume * 100))
        await self._send("set_volume", {"volume": scaled})
        self._volume = volume

    async def async_volume_up(self) -> None:
        current = int((self._volume or 0.0) * 100) + 10
        await self._send("set_volume", {"volume": min(100, current)})

    async def async_volume_down(self) -> None:
        current = int((self._volume or 0.0) * 100) - 10
        await self._send("set_volume", {"volume": max(0, current)})
