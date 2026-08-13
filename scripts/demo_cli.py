#!/usr/bin/env python3
"""
Phase 1 交互演示 (demo_cli)

跑通完整闭环：说明书 → 编译设备 → 意图理解 → 运行期 → 虚拟设备。

用法：
    python scripts/demo_cli.py examples/sample_light.txt --id lamp-01

    # 无 LLM 环境也跑通（用预置示例设备 + 规则意图）
    python scripts/demo_cli.py --demo

    # 用你自己的说明书（需配置 LLM）
    python scripts/demo_cli.py path/to/manual.txt --id my-device --name "格力空调"

环境变量：
    DEVICEMIND_LLM_PROVIDER  openai / ollama
    DEEPSEEK_API_KEY / OPENAI_API_KEY
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.compiler import DeviceCompiler, load_cached  # noqa: E402
from devicemind.intent import IntentParser  # noqa: E402
from devicemind.llm import LLMClient  # noqa: E402
from devicemind.runtime import build_command  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402


# 预置示例设备（无 LLM 时的 fallback，对应 examples/sample_light.txt）
SAMPLE_DEVICE = {
    "id": "lamp-01",
    "type": "light",
    "name": "智能 LED 灯泡",
    "brand": "示例",
    "model": "SmartBulb-L5",
    "capabilities": [
        {
            "name": "power",
            "properties": {},
            "actions": [
                {"name": "turn_on", "params": {}},
                {"name": "turn_off", "params": {}},
            ],
        },
        {
            "name": "brightness",
            "properties": {"brightness": {"type": "number", "min": 1, "max": 100}},
            "actions": [{"name": "set_brightness", "params": {"brightness": {"type": "number"}}}],
        },
        {
            "name": "color_temp",
            "properties": {"color_temp": {"type": "number", "min": 2700, "max": 6500}},
            "actions": [{"name": "set_color_temp", "params": {"color_temp": {"type": "number"}}}],
        },
        {
            "name": "color",
            "properties": {},
            "actions": [{"name": "set_color", "params": {"color": {"type": "object"}}}],
        },
    ],
    "control": {
        "protocol": "mqtt",
        "commands": {
            "turn_on": {"topic": "smarthome/lamp01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/lamp01/set", "payload": {"power": "off"}},
            "set_brightness": {"topic": "smarthome/lamp01/set", "payload": {"brightness": 80}},
            "set_color_temp": {"topic": "smarthome/lamp01/set", "payload": {"color_temp": 4000}},
            "set_color": {"topic": "smarthome/lamp01/set", "payload": {"color": {"r": 255, "g": 0, "b": 0}}},
        },
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="DeviceMind Phase 1 交互演示")
    parser.add_argument("manual", nargs="?", default=None, help="设备说明书文件路径")
    parser.add_argument("--id", default="lamp-01", help="设备唯一标识")
    parser.add_argument("--name", default=None, help="设备名称提示")
    parser.add_argument("--demo", action="store_true", help="使用预置示例设备（无需 LLM）")
    args = parser.parse_args()

    # 1. 获取设备描述
    device = None
    if args.demo:
        device = SAMPLE_DEVICE
        print(f"[设备] 使用预置示例设备: {device['name']} ({device['id']})")
    elif args.manual:
        device = compile_device(args.manual, args.id, args.name)
    else:
        # 默认尝试编译，失败则用预置
        device = try_compile_or_fallback(args.id)

    if device is None:
        print("[失败] 无法加载设备")
        return 1

    # 2. 注册到虚拟 Hub
    hub = VirtualHub()
    vdev = VirtualDevice(device["id"], device["name"], state={"power": "off"})
    hub.register(vdev)

    actions = _collect_actions(device)
    print(f"[设备] {device['name']} ({device['id']})")
    print(f"[设备] 可用动作: {', '.join(actions)}")
    print("[提示] 输入指令（如：打开 / 关闭 / 调到50% / 调暗 / 调亮），输入 exit 退出\n")

    # 3. 交互循环
    intent_parser = IntentParser()
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text in ("exit", "quit", "退出", "q"):
            break
        if not text:
            continue

        try:
            # 意图理解
            intent = intent_parser.parse(text, [device])
            if intent.device_id is None:
                intent.device_id = device["id"]

            # 运行期：生成指令
            command = build_command(device, intent.action, intent.params)

            # 发到虚拟设备
            new_state = hub.send_command(intent.device_id, command)

            print(f"  [意图] action={intent.action}, params={intent.params}")
            print(f"  [指令] {command.protocol} {command.topic or command.endpoint} -> {command.payload}")
            print(f"  [状态] {new_state}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [错误] {exc}")

    print("\n[退出] 本次操作历史：")
    for i, h in enumerate(vdev.history, 1):
        print(f"  {i}. {h['protocol']} {h['topic']} -> {h['payload']}")
    return 0


def compile_device(manual: str, device_id: str, name_hint: str | None):
    path = Path(manual)
    if not path.exists():
        print(f"[错误] 说明书文件不存在: {path}")
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")

    client = LLMClient.from_env()
    print(f"[编译] 后端={client.provider}, 模型={client.model}")
    try:
        device = DeviceCompiler(client).compile(text, device_id, name_hint)
        print(f"[编译] 成功: {device.get('name')}")
        return device
    except Exception as exc:  # noqa: BLE001
        print(f"[编译] 失败: {exc}")
        print("[编译] 回退到预置示例设备")
        return SAMPLE_DEVICE


def try_compile_or_fallback(device_id: str):
    # 先查缓存
    cached = load_cached(device_id)
    if cached:
        print(f"[设备] 命中缓存: {cached.get('name')}")
        return cached
    print("[设备] 无说明书且无缓存，使用预置示例设备（--demo 模式）")
    return SAMPLE_DEVICE


def _collect_actions(device: dict) -> list[str]:
    result = []
    for cap in device.get("capabilities", []):
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                result.append(act["name"])
    return result


if __name__ == "__main__":
    raise SystemExit(main())
