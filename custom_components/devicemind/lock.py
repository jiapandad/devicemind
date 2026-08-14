"""DeviceMind lock 平台：把 type=lock 的设备协议注册为 HA 门锁实体。"""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant

from .base import DeviceMindEntityMixin, add_entities_with_state
from .const import DOMAIN


async def async_setup_platform(
    hass: HomeAssistant, config: dict, async_add_entities, discovery_info=None
) -> None:
    devices = hass.data.get(DOMAIN, {}).get("devices", {}).get("lock", [])
    await add_entities_with_state(hass, devices, DeviceMindLock, async_add_entities)


class DeviceMindLock(DeviceMindEntityMixin, LockEntity):
    """一个由设备协议 JSON 驱动的门锁实体。"""

    def __init__(self, hass: HomeAssistant, device: dict[str, Any]) -> None:
        LockEntity.__init__(self)
        self._init_device(hass, device)
        self._is_locked = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    async def async_lock(self, **kwargs) -> None:
        await self._send("lock")
        self._is_locked = True

    async def async_unlock(self, **kwargs) -> None:
        await self._send("unlock")
        self._is_locked = False

    def update_from_state(self, payload: dict[str, Any]) -> None:
        if "lock_state" in payload:
            self._is_locked = payload["lock_state"] in ("locked", "lock", "1", 1, True)
