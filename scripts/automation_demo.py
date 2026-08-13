#!/usr/bin/env python3
"""
多场景自动化模拟 (automation_demo)

用虚拟设备 + 模拟环境数据，演示多种自动化场景，无需实机：

  下雨关窗 · 降温开暖气 · 雾霾开净化器 · 深夜关灯

用法：
    python scripts/automation_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.automation import AutomationEngine, AutomationRule, weather, time  # noqa: E402
from devicemind.scene import SceneStep  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402


# ---------------------------------------------------------------------------
# 设备定义（简化）
# ---------------------------------------------------------------------------
def _simple_device(device_id: str, name: str, action: str, topic: str, payload: dict) -> dict:
    return {
        "id": device_id,
        "type": "other",
        "name": name,
        "capabilities": [
            {"name": "power", "properties": {},
             "actions": [{"name": action, "params": {}}]},
        ],
        "control": {"protocol": "mqtt", "commands": {
            action: {"topic": topic, "payload": payload},
        }},
    }


def main() -> int:
    # 1. 虚拟设备
    curtain = _simple_device("curtain-01", "窗帘", "turn_off", "home/curtain/set", {"action": "close"})
    heater = _simple_device("heater-01", "暖气", "turn_on", "home/heater/set", {"power": "on"})
    lamp = _simple_device("lamp-01", "客厅灯", "turn_off", "home/lamp/set", {"power": "off"})
    purifier = _simple_device("purifier-01", "净化器", "turn_on", "home/purifier/set", {"power": "on"})

    devices = {
        "curtain-01": curtain, "heater-01": heater,
        "lamp-01": lamp, "purifier-01": purifier,
    }

    hub = VirtualHub()
    hub.register(VirtualDevice("curtain-01", "窗帘", {"state": "open"}))
    hub.register(VirtualDevice("heater-01", "暖气", {"power": "off"}))
    hub.register(VirtualDevice("lamp-01", "客厅灯", {"power": "on"}))
    hub.register(VirtualDevice("purifier-01", "净化器", {"power": "off"}))

    # 2. 自动化规则
    engine = AutomationEngine()
    engine.add_rule(AutomationRule("下雨关窗", weather("rain", "==", True),
                                   [SceneStep("curtain-01", "turn_off", {})], "下雨时自动关窗"))
    engine.add_rule(AutomationRule("降温开暖气", weather("temp", "<", 10),
                                   [SceneStep("heater-01", "turn_on", {})], "气温低于10度开暖气"))
    engine.add_rule(AutomationRule("雾霾开净化器", weather("aqi", ">", 150),
                                   [SceneStep("purifier-01", "turn_on", {})], "空气质量差开净化器"))
    engine.add_rule(AutomationRule("深夜关灯", time("hour", "==", 23),
                                   [SceneStep("lamp-01", "turn_off", {})], "23点自动关灯"))

    # 3. 模拟一天的时间线
    timeline = [
        (9, {"weather": {"rain": False, "temp": 22, "aqi": 80}, "time": {"hour": 9}}, "早上 9 点 · 晴天 22°C"),
        (12, {"weather": {"rain": True, "temp": 21, "aqi": 85}, "time": {"hour": 12}}, "中午 12 点 · 开始下雨"),
        (15, {"weather": {"rain": True, "temp": 8, "aqi": 200}, "time": {"hour": 15}}, "下午 15 点 · 降温 + 雾霾"),
        (23, {"weather": {"rain": False, "temp": 8, "aqi": 180}, "time": {"hour": 23}}, "深夜 23 点"),
    ]

    print("DeviceMind 自动化演示：模拟一天的自动化响应\n")
    for hour, context, desc in timeline:
        print(f"=== {desc} ===")
        fired = engine.tick(context, devices, hub)
        if fired:
            for f in fired:
                if "error" in f:
                    print(f"  [容错] {f['rule']}: {f['error']}")
                else:
                    print(f"  [触发] {f['rule']}: {f['device_id']} {f['action']} -> {f['payload']}")
        else:
            print("  （无规则触发）")
        print()

    # 4. 展示最终状态
    print("=== 最终设备状态 ===")
    for device_id, state in hub.get_all_states().items():
        print(f"  {device_id}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
