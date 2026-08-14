#!/usr/bin/env python3
"""
批量编译测试 (batch_test)

用多种不同品类的设备说明书，验证"LLM 读说明书 → 生成设备 JSON"的泛化能力。

用法：
    DEVICEMIND_LLM_PROVIDER=ollama DEVICEMIND_LLM_MODEL=qwen2.5:3b \
        python scripts/batch_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.compiler import DeviceCompiler  # noqa: E402
from devicemind.llm import LLMClient  # noqa: E402
from devicemind.schema import ACTIONS  # noqa: E402

# 测试用例：设备ID -> (说明书路径, 期望类型, 期望能力)
CASES = [
    ("light-01", "examples/sample_light.txt", "light", ["power", "brightness"]),
    ("ac-01", "examples/sample_aircon.txt", "climate", ["power", "temperature", "mode", "fan_speed"]),
    ("vacuum-01", "examples/sample_vacuum.txt", "vacuum", ["power", "mode", "fan_speed"]),
    ("lock-01", "examples/sample_lock.txt", "lock", ["lock_state", "battery"]),
    ("sensor-01", "examples/sample_sensor.txt", "sensor", ["temperature", "humidity", "battery"]),
    ("heater-01", "examples/sample_heater.txt", "climate", ["power", "temperature", "mode"]),
    ("curtain-01", "examples/sample_curtain.txt", "other", ["power"]),
    ("speaker-01", "examples/sample_speaker.txt", "media", ["power", "volume", "mode"]),
]


def collect_capabilities(device: dict) -> list[str]:
    return [cap.get("name", "?") for cap in device.get("capabilities", [])]


def collect_actions(device: dict) -> list[str]:
    result = []
    for cap in device.get("capabilities", []):
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                result.append(act["name"])
    return result


def main() -> int:
    compiler = DeviceCompiler(LLMClient.from_env())
    print(f"后端: {compiler.client.provider}, 模型: {compiler.client.model}\n")

    total_caps = 0
    hit_caps = 0
    type_correct = 0

    for device_id, path, expected_type, expected_caps in CASES:
        text = Path(path).read_text(encoding="utf-8")
        print(f"=== {path} -> {device_id} ===")

        try:
            device = compiler.compile(text, device_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  [失败] {exc}\n")
            continue

        actual_type = device.get("type")
        caps = collect_capabilities(device)
        actions = collect_actions(device)

        # 类型是否正确
        type_ok = actual_type == expected_type
        if type_ok:
            type_correct += 1

        # 能力命中率
        hit = [c for c in expected_caps if c in caps]
        hit_caps += len(hit)
        total_caps += len(expected_caps)

        print(f"  类型: {actual_type} {'✓' if type_ok else '✗(期望 ' + expected_type + ')'}")
        print(f"  能力: {caps}")
        print(f"  期望能力命中: {len(hit)}/{len(expected_caps)} {hit}")
        print(f"  动作: {actions}")

        # 动作命名是否规范（在 ACTIONS 枚举内）
        bad_actions = [a for a in actions if a not in ACTIONS]
        if bad_actions:
            print(f"  ⚠ 不规范动作名: {bad_actions}")
        print()

    print("=" * 50)
    print(f"类型正确率: {type_correct}/{len(CASES)}")
    print(f"能力命中率: {hit_caps}/{total_caps} ({100*hit_caps//total_caps if total_caps else 0}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
