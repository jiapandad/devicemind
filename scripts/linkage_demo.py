#!/usr/bin/env python3
"""
新设备自动联动演示 (linkage_demo)

演示：新设备接入后，系统自动理解它的能力，自动与现有设备组网联动。

  已有设备：窗帘、暖气、净化器、灯
  新接入雨水传感器 → 自动发现"下雨关窗"
  新接入温湿度传感器 → 自动发现"低温开暖气" + "雾霾开净化器"
  新接入人体传感器 → 自动发现"有人移动开灯"

用法：
    python scripts/linkage_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.automation import AutomationEngine  # noqa: E402
from devicemind.linkage import integrate_new_device  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402


def _exec_device(device_id: str, name: str, action: str, payload: dict) -> dict:
    """构造一个执行设备（窗帘/暖气/灯等）。"""
    return {
        "id": device_id, "type": "other", "name": name,
        "capabilities": [{"name": "power", "properties": {},
                          "actions": [{"name": action, "params": {}}]}],
        "control": {"protocol": "mqtt", "commands": {
            action: {"topic": f"home/{device_id}/set", "payload": payload}}},
    }


def _sensor(device_id: str, name: str, caps: list[str]) -> dict:
    """构造一个传感器设备（感知设备）。"""
    return {
        "id": device_id, "type": "sensor", "name": name,
        "capabilities": [{"name": c, "properties": {}, "actions": []} for c in caps],
        "control": {"protocol": "mqtt", "commands": {}},
    }


def main() -> int:
    # 1. 已有执行设备
    devices = {
        "curtain-01": _exec_device("curtain-01", "智能窗帘", "turn_off", {"action": "close"}),
        "heater-01": _exec_device("heater-01", "地暖暖气", "turn_on", {"power": "on"}),
        "purifier-01": _exec_device("purifier-01", "空气净化器", "turn_on", {"power": "on"}),
        "lamp-01": _exec_device("lamp-01", "客厅灯", "turn_on", {"power": "on"}),
    }
    hub = VirtualHub()
    for device_id, device in devices.items():
        hub.register(VirtualDevice(device_id, device["name"], {}))

    engine = AutomationEngine()
    print("DeviceMind 联动演示：新设备自动组网\n")
    print("已有设备：窗帘、暖气、净化器、灯\n")

    # 2. 新设备接入，自动发现联动
    new_sensors = [
        _sensor("rain-sensor-01", "雨水传感器", ["rain"]),
        _sensor("th-sensor-01", "温湿度传感器", ["temperature", "humidity", "air_quality"]),
        _sensor("motion-sensor-01", "人体传感器", ["motion"]),
    ]

    all_devices = dict(devices)
    for sensor in new_sensors:
        print(f"=== 新设备接入：{sensor['name']}（能力: {[c['name'] for c in sensor['capabilities']]}）===")
        found = integrate_new_device(sensor, all_devices, engine)
        if found:
            for name in found:
                print(f"  ✓ 自动生成联动：{name}")
        else:
            print("  （无匹配联动）")
        all_devices[sensor["id"]] = sensor
        print()

    # 3. 模拟环境变化，触发自动联动
    print("=== 模拟环境变化，触发联动 ===\n")

    print("【下雨了】")
    fired = engine.tick({"weather": {"rain": True}}, devices, hub)
    for f in fired:
        print(f"  → {f['rule']}: {f['device_id']} {f['action']} -> {f['payload']}")

    print("\n【降温到 5 度 + 雾霾 AQI 200】")
    fired = engine.tick({"weather": {"temp": 5, "aqi": 200}}, devices, hub)
    for f in fired:
        print(f"  → {f['rule']}: {f['device_id']} {f['action']} -> {f['payload']}")

    print("\n【有人移动】")
    fired = engine.tick({"weather": {"motion": True}}, devices, hub)
    for f in fired:
        print(f"  → {f['rule']}: {f['device_id']} {f['action']} -> {f['payload']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
