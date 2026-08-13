"""
虚拟设备模拟器 (Simulator)

在内存中模拟 MQTT 设备，让系统无需真实硬件也能跑通端到端闭环。

设计要点：
- 接口对齐真实适配器（Phase 2 会接真实 MQTT），方便替换
- 每个虚拟设备维护自己的状态，接收指令并更新
- 记录操作历史，便于演示和调试
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devicemind.runtime import Command


@dataclass
class VirtualDevice:
    """模拟一个设备。"""
    device_id: str
    name: str
    state: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def apply_command(self, command: Command) -> dict[str, Any]:
        """接收控制指令，更新状态，返回最新状态。"""
        if command.payload and isinstance(command.payload, dict):
            self.state.update(command.payload)

        record = {
            "protocol": command.protocol,
            "topic": command.topic,
            "payload": command.payload,
        }
        self.history.append(record)
        return dict(self.state)

    def get_state(self) -> dict[str, Any]:
        return dict(self.state)


class VirtualHub:
    """
    模拟 MQTT Broker，管理多个虚拟设备。

    用法：
        hub = VirtualHub()
        hub.register(VirtualDevice("lamp-01", "客厅灯"))
        hub.send_command("lamp-01", command)  # 模拟向设备发指令
    """

    def __init__(self) -> None:
        self.devices: dict[str, VirtualDevice] = {}

    def register(self, device: VirtualDevice) -> None:
        self.devices[device.device_id] = device

    def get(self, device_id: str) -> VirtualDevice:
        if device_id not in self.devices:
            raise KeyError(f"虚拟设备不存在: {device_id}")
        return self.devices[device_id]

    def send_command(self, device_id: str, command: Command) -> dict[str, Any]:
        """模拟向设备发送控制指令，返回最新状态。"""
        return self.get(device_id).apply_command(command)

    def list_devices(self) -> list[str]:
        return list(self.devices.keys())
