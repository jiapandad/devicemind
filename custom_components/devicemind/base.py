"""DeviceMind 平台公共基类（mixin）。

各平台实体继承本 mixin + 对应的 HA Entity，复用：
- 设备协议读取（_has_capability / _cap_property）
- 命令构建与发布（_send，支持 MQTT / HTTP 两种协议）
- 状态回传订阅（subscribe_state + update_from_state 钩子）

避免在每个平台重复实现构建/发布/订阅逻辑。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .runtime import build_command, command_payload_str

_LOGGER = logging.getLogger(__name__)


async def subscribe_state(hass, entity: "DeviceMindEntityMixin", device: dict[str, Any]) -> None:
    """
    为声明了 state_topic 的设备订阅 MQTT 状态回传。

    收到状态 payload 后调用 entity.update_from_state(payload)，各平台自行
    把 payload 字段映射到实体属性并刷新状态。
    """
    state_topic = (device.get("control") or {}).get("state_topic")
    if not state_topic:
        return

    try:
        from homeassistant.components import mqtt
        from homeassistant.core import callback
    except ImportError:
        _LOGGER.warning("订阅失败：无法导入 mqtt 组件")
        return

    @callback
    def _on_message(msg: Any) -> None:
        payload = msg.payload
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode("utf-8", errors="ignore")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {"value": payload}
        entity.update_from_state(payload)
        entity.async_write_ha_state()

    await mqtt.async_subscribe(hass, state_topic, _on_message)


async def add_entities_with_state(hass, devices, entity_cls, async_add_entities) -> None:
    """创建实体、注册到 HA，并为声明了 state_topic 的设备订阅状态回传。"""
    entities = [entity_cls(hass, device) for device in devices]
    async_add_entities(entities)
    for entity, device in zip(entities, devices):
        await subscribe_state(hass, entity, device)


async def _send_http(hass, command) -> None:
    """通过 HTTP 协议发布控制指令（POST endpoint + JSON payload）。"""
    if not command.endpoint:
        _LOGGER.warning("HTTP 指令缺少 endpoint")
        return
    try:
        from homeassistant.helpers.httpx_client import get_async_client
    except ImportError:
        _LOGGER.warning("无法导入 HTTP 客户端")
        return
    client = get_async_client(hass)
    payload = command.payload if isinstance(command.payload, (dict, list)) else command.payload
    await client.post(command.endpoint, json=payload if isinstance(payload, (dict, list)) else None)


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
        """构建并发布一条控制指令（按协议分派到 MQTT 或 HTTP）。"""
        try:
            command = build_command(self._device, action, params)
        except ValueError as exc:
            _LOGGER.warning("设备 %s 无法构建指令 %s: %s", self._attr_name, action, exc)
            return

        if command.protocol == "http":
            await _send_http(self.hass, command)
            return

        if command.topic is None:
            _LOGGER.warning("设备 %s 未定义指令 %s", self._attr_name, action)
            return
        await self.hass.services.async_call(
            "mqtt",
            "publish",
            {"topic": command.topic, "payload": command_payload_str(command)},
        )

    def update_from_state(self, payload: dict[str, Any]) -> None:
        """
        状态回传钩子：把 payload 字段映射到实体属性。

        默认处理最通用的 power 字段（映射到 _is_on）；各平台可覆盖以处理
        额外字段（亮度/温度/读数等）。
        """
        power = payload.get("power")
        if power is not None:
            self._is_on = power in ("on", "ON", "1", 1, True)
