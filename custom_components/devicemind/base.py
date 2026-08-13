"""DeviceMind 平台公共基类（mixin）。

各平台实体继承本 mixin + 对应的 HA Entity，复用：
- 设备协议读取（_has_capability / _cap_property）
- 命令构建与 MQTT 发布（_send）

避免在每个平台重复实现 build_command + mqtt.publish 逻辑。
"""

from __future__ import annotations

import logging
from typing import Any

from .runtime import build_command, command_payload_str

_LOGGER = logging.getLogger(__name__)


class DeviceMindEntityMixin:
    """设备协议 JSON 驱动的实体公共逻辑（mixin，非 HA Entity）。"""

    def _init_device(self, hass, device: dict[str, Any]) -> None:
        self.hass = hass
        self._device = device
        self._attr_name = device.get("name", device.get("id", ""))
        self._attr_unique_id = f"devicemind_{device.get('id')}"

    def _has_capability(self, name: str) -> bool:
        return any(cap.get("name") == name for cap in self._device.get("capabilities", []))

    def _cap_property(self, cap_name: str, prop_name: str) -> dict[str, Any] | None:
        for cap in self._device.get("capabilities", []):
            if cap.get("name") == cap_name:
                return (cap.get("properties") or {}).get(prop_name)
        return None

    def _cap_enum(self, cap_name: str) -> list[Any]:
        """取某个能力下第一个属性的 enum（用于模式/档位映射）。"""
        for cap in self._device.get("capabilities", []):
            if cap.get("name") != cap_name:
                continue
            for prop in (cap.get("properties") or {}).values():
                if isinstance(prop, dict) and "enum" in prop:
                    return list(prop["enum"])
        return []

    async def _send(self, action: str, params: dict[str, Any] | None = None) -> None:
        """构建并发布一条控制指令（topic 缺失或动作不匹配时仅告警）。"""
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
