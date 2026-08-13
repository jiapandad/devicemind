"""
设备联动自动发现 (Linkage)

新设备接入时，根据它的能力自动发现与现有设备的联动关系，生成自动化规则。

例：
  新接入雨水传感器 → 自动发现"下雨 → 关窗帘"
  新接入温湿度传感器 → 自动发现"低温 → 开暖气"、"雾霾 → 开净化器"

核心思想：设备能力 → 联动知识库匹配 → 自动生成规则，让系统"自动组网"，
而不是让用户手动配置每一条联动。
"""

from __future__ import annotations

from typing import Any

from devicemind.automation import AutomationRule, weather
from devicemind.scene import SceneStep


# ---------------------------------------------------------------------------
# 联动知识库：新设备的感知能力 → 触发已有设备的动作
# 这是智能家居的"常识"，可扩展（社区贡献、LLM 生成）
# ---------------------------------------------------------------------------
LINK_KNOWLEDGE: list[dict[str, Any]] = [
    {
        "desc": "下雨自动关窗",
        "sensor_capability": "rain",
        "condition": weather("rain", "==", True),
        "target_hint": "窗帘",
        "target_action": "turn_off",
    },
    {
        "desc": "低温自动开暖气",
        "sensor_capability": "temperature",
        "condition": weather("temp", "<", 10),
        "target_hint": "暖气",
        "target_action": "turn_on",
    },
    {
        "desc": "雾霾自动开净化器",
        "sensor_capability": "air_quality",
        "condition": weather("aqi", ">", 150),
        "target_hint": "净化器",
        "target_action": "turn_on",
    },
    {
        "desc": "有人移动自动开灯",
        "sensor_capability": "motion",
        "condition": weather("motion", "==", True),
        "target_hint": "灯",
        "target_action": "turn_on",
    },
]


def collect_capabilities(device: dict[str, Any]) -> list[str]:
    """收集设备的能力名列表。"""
    caps = []
    for cap in device.get("capabilities", []):
        if isinstance(cap, dict) and cap.get("name"):
            caps.append(cap["name"])
    return caps


def find_target(
    devices: dict[str, dict[str, Any]], hint: str
) -> tuple[str, dict[str, Any]] | None:
    """在现有设备里找名称含 hint 的目标设备。"""
    for device_id, device in devices.items():
        if hint in device.get("name", ""):
            return device_id, device
    return None


def discover_linkages(
    new_device: dict[str, Any],
    existing_devices: dict[str, dict[str, Any]],
) -> list[AutomationRule]:
    """
    新设备接入，自动发现联动关系，生成自动化规则。

    参数:
        new_device: 新接入的设备 JSON（编译后）
        existing_devices: 已有设备 {device_id: 设备 JSON}

    返回:
        自动生成的自动化规则列表
    """
    new_caps = collect_capabilities(new_device)
    rules: list[AutomationRule] = []

    for knowledge in LINK_KNOWLEDGE:
        # 1. 新设备能感知这个能力吗？
        if knowledge["sensor_capability"] not in new_caps:
            continue
        # 2. 系统里有没有对应的执行设备？
        target = find_target(existing_devices, knowledge["target_hint"])
        if target is None:
            continue

        target_id, _ = target
        rules.append(AutomationRule(
            name=knowledge["desc"],
            trigger=knowledge["condition"],
            actions=[SceneStep(target_id, knowledge["target_action"], {})],
            description=f"自动发现：{new_device.get('name', '新设备')} 触发 {knowledge['target_hint']}",
        ))

    return rules


def integrate_new_device(
    new_device: dict[str, Any],
    existing_devices: dict[str, dict[str, Any]],
    engine: Any,
) -> list[str]:
    """
    接入新设备并自动加入现有设备的联动。

    返回:
        自动生成的联动规则名列表
    """
    rules = discover_linkages(new_device, existing_devices)
    for rule in rules:
        engine.add_rule(rule)
    return [r.name for r in rules]
