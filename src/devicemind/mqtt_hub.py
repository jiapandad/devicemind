"""
真实 MQTT 适配层 (MqttHub)

把 DeviceMind 的运行期指令真正发到 MQTT Broker，接入真实设备（Phase 2）。

与 VirtualHub 接口对齐，上层（webapp / scene / automation）无需感知差异：
    hub.register_device(device_id, name, state)  # 注册设备
    hub.send_command(device_id, command)         # 发控制指令 -> 返回状态
    hub.get_all_states()                          # 导出所有状态（用于持久化）
    hub.probe(device_id, command)                 # 试运行验证（真实设备暂跳过）

配置（环境变量）：
    DEVICEMIND_MQTT_HOST   Broker 地址（默认 localhost）
    DEVICEMIND_MQTT_PORT   端口（默认 1883）
    DEVICEMIND_MQTT_USER   用户名（可选）
    DEVICEMIND_MQTT_PASS   密码（可选）

依赖：paho-mqtt（可选，未安装时首次调用会给出明确提示）。
状态回传：调用 subscribe_state(device_id, topic) 订阅设备的上报 topic，
收到 JSON 载荷后自动合并到本地状态。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from devicemind.runtime import Command


@dataclass
class _DeviceEntry:
    """MqttHub 内部维护的设备状态容器，对外提供与 VirtualDevice 一致的 get_state()。"""
    name: str
    state: dict[str, Any] = field(default_factory=dict)

    def get_state(self) -> dict[str, Any]:
        return dict(self.state)


class MqttHub:
    """真实 MQTT 设备执行器。"""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host or os.getenv("DEVICEMIND_MQTT_HOST", "localhost")
        self.port = int(port or os.getenv("DEVICEMIND_MQTT_PORT", "1883"))
        self.username = username or os.getenv("DEVICEMIND_MQTT_USER")
        self.password = password or os.getenv("DEVICEMIND_MQTT_PASS")
        self.devices: dict[str, _DeviceEntry] = {}
        self._state_topics: dict[str, str] = {}  # device_id -> 状态上报 topic
        self._client: Any = None

    # ------------------------------------------------------------------
    # 设备管理
    # ------------------------------------------------------------------
    def register(self, device: Any) -> None:
        """兼容 VirtualHub 风格：接受有 device_id/name/state 属性的对象。"""
        self.register_device(device.device_id, device.name, getattr(device, "state", {}))

    def register_device(self, device_id: str, name: str, state: dict[str, Any] | None = None) -> None:
        self.devices[device_id] = _DeviceEntry(name, state or {})

    def remove(self, device_id: str) -> None:
        self.devices.pop(device_id, None)
        self._state_topics.pop(device_id, None)

    def get(self, device_id: str) -> _DeviceEntry:
        if device_id not in self.devices:
            raise KeyError(f"设备不存在: {device_id}")
        return self.devices[device_id]

    def list_devices(self) -> list[str]:
        return list(self.devices.keys())

    # ------------------------------------------------------------------
    # 控制指令
    # ------------------------------------------------------------------
    def send_command(self, device_id: str, command: Command) -> dict[str, Any]:
        """发布控制指令到 MQTT，并乐观更新本地状态。"""
        client = self._client_or_raise()
        entry = self.get(device_id)

        payload = (
            json.dumps(command.payload, ensure_ascii=False)
            if command.payload is not None
            else ""
        )
        client.publish(command.topic, payload)

        if isinstance(command.payload, dict):
            entry.state.update(command.payload)
        return entry.get_state()

    def probe(self, device_id: str, command: Command) -> bool:
        """
        试运行验证。真实设备没有 expected_topic 可静态比对，
        需要实机回传机制（订阅响应 topic）才能判断，此处先跳过。
        """
        return True

    # ------------------------------------------------------------------
    # 状态回传
    # ------------------------------------------------------------------
    def subscribe_state(self, device_id: str, topic: str) -> None:
        """订阅设备状态上报 topic，收到 JSON 载荷后自动合并到本地状态。"""
        self._state_topics[device_id] = topic
        if self._client is not None:
            self._client.subscribe(topic)

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any = None, properties: Any = None) -> None:
        for topic in set(self._state_topics.values()):
            client.subscribe(topic)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace")
        try:
            data = json.loads(payload)
        except (ValueError, json.JSONDecodeError):
            data = {"raw": payload}
        if not isinstance(data, dict):
            return
        for device_id, t in self._state_topics.items():
            if t == topic:
                self.devices[device_id].state.update(data)

    # ------------------------------------------------------------------
    # 状态持久化接口
    # ------------------------------------------------------------------
    def get_all_states(self) -> dict[str, dict[str, Any]]:
        return {device_id: e.get_state() for device_id, e in self.devices.items()}

    def restore_states(self, states: dict[str, dict[str, Any]]) -> None:
        for device_id, state in states.items():
            if device_id in self.devices:
                self.devices[device_id].state.update(state)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _client_or_raise(self) -> Any:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "需要 paho-mqtt，请先安装: pip install paho-mqtt"
            ) from exc

        if self._client is None:
            try:  # paho-mqtt 2.x 需要指定 CallbackAPIVersion
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            except AttributeError:  # pragma: no cover
                client = mqtt.Client()
            client.on_connect = self._on_connect
            client.on_message = self._on_message
            if self.username is not None:
                client.username_pw_set(self.username, self.password)
            client.connect(self.host, self.port)
            client.loop_start()
            self._client = client

        return self._client
