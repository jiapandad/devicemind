"""
DeviceMind 统一设备模型 (Unified Device Model)

这是整个项目的地基：一套足够通用、又不失精确的设备描述协议。
LLM 从设备说明书中提取信息，编译成符合本 Schema 的 JSON。

设计原则：
1. 能力 (capability) 是原子单元，可组合 —— 灯 = power + brightness + color
2. 每个能力有 properties(可读) 和 actions(可写)
3. control 描述如何物理发指令（运行期使用）
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# 设备类型枚举
# ---------------------------------------------------------------------------
DEVICE_TYPES = [
    "light",      # 灯
    "switch",     # 开关/插座
    "climate",    # 空调/暖通
    "sensor",     # 传感器
    "lock",       # 门锁
    "camera",     # 摄像头
    "vacuum",     # 扫地机器人
    "media",      # 影音设备
    "cover",      # 窗帘/卷帘/百叶
    "fan",        # 风扇
    "humidifier", # 加湿器
    "other",      # 其他
]

# ---------------------------------------------------------------------------
# 原子能力单元（可组合）
# ---------------------------------------------------------------------------
CAPABILITIES = [
    "power",           # 开关
    "brightness",      # 亮度 0-100
    "color",           # 颜色 RGB
    "color_temp",      # 色温
    "temperature",     # 温度（空调/热水器）
    "humidity",        # 湿度
    "fan_speed",       # 风速/档位
    "mode",            # 模式（制冷/制热/自动）
    "motion",          # 运动检测
    "lock_state",      # 锁状态
    "power_meter",     # 功率/电量
    "battery",         # 电池
    "volume",          # 音量
    "position",        # 开合度（窗帘 0-100）
    "target_humidity", # 目标湿度（加湿器）
    "other",
]

# ---------------------------------------------------------------------------
# 标准动作名（规范命名，LLM 应从中选择，避免随意命名）
# ---------------------------------------------------------------------------
ACTIONS = [
    "turn_on",          # 打开
    "turn_off",         # 关闭
    "set_brightness",   # 设置亮度
    "set_color",        # 设置颜色
    "set_color_temp",   # 设置色温
    "set_temperature",  # 设置温度
    "set_mode",         # 设置模式
    "set_fan_speed",    # 设置风速
    "lock",             # 上锁
    "unlock",           # 解锁
    "set_volume",       # 设置音量
    "open",             # 打开（窗帘/卷帘）
    "close",            # 关闭（窗帘/卷帘）
    "stop",             # 停止（窗帘/扫地机）
    "set_position",     # 设置开合度
    "set_humidity",     # 设置目标湿度
    "get_state",        # 查询状态（只读）
    "get_battery",      # 查询电量（只读）
    "other",            # 其他
]

# ---------------------------------------------------------------------------
# 供 LLM 输出的 JSON Schema（用于校验 + 引导结构化输出）
# ---------------------------------------------------------------------------
DEVICE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["id", "type", "name", "capabilities", "control"],
    "properties": {
        "id": {
            "type": "string",
            "description": "设备唯一标识，如 geli-ac-01",
        },
        "type": {
            "type": "string",
            "enum": DEVICE_TYPES,
            "description": "设备类型",
        },
        "name": {
            "type": "string",
            "description": "人类可读名称，如 格力空调",
        },
        "brand": {"type": "string", "description": "品牌"},
        "model": {"type": "string", "description": "型号"},
        "description": {"type": "string", "description": "一句话描述"},
        "capabilities": {
            "type": "array",
            "description": "设备能力列表",
            "items": {
                "type": "object",
                "required": ["name", "properties", "actions"],
                "properties": {
                    "name": {
                        "type": "string",
                        "enum": CAPABILITIES,
                        "description": "能力名（原子单元）",
                    },
                    "properties": {
                        "type": "object",
                        "description": "可读属性，键为属性名，值为 {type, unit, min, max, enum, description}",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "unit": {"type": "string"},
                                "min": {},
                                "max": {},
                                "enum": {"type": "array", "description": "允许的枚举取值"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "actions": {
                        "type": "array",
                        "description": "可执行动作",
                        "items": {
                            "type": "object",
                            "required": ["name", "params"],
                            "properties": {
                                "name": {"type": "string", "enum": ACTIONS},
                                "params": {
                                    "type": "object",
                                    "description": "动作参数，键为参数名，值为 {type, unit, required}",
                                },
                            },
                        },
                    },
                },
            },
        },
        "control": {
            "type": "object",
            "description": "如何物理发指令（运行期使用）",
            "required": ["protocol", "commands"],
            "properties": {
                "protocol": {
                    "type": "string",
                    "enum": ["mqtt", "http", "serial", "ble", "unknown"],
                },
                "commands": {
                    "type": "object",
                    "description": "动作名 -> 指令模板。每个模板是 {topic, payload}（MQTT）或 {endpoint, payload}（HTTP）。payload 是 JSON 对象，参数值用占位符字符串如 \"{brightness}\" 表示",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "MQTT topic"},
                            "endpoint": {"type": "string", "description": "HTTP endpoint"},
                            "payload": {"type": "object", "description": "JSON 载荷，参数用占位符"},
                        },
                    },
                },
                "state_topic": {
                    "type": "string",
                    "description": "设备状态回传的 MQTT 主题（可选）。设备通过该主题上报状态，集成订阅后更新实体状态",
                },
                "state_map": {
                    "type": "object",
                    "description": "状态 payload 字段名 -> 设备能力名 的映射（可选）。如 {\"power\": \"power\", \"temp\": \"temperature\"}，用于解析状态回传 payload",
                },
            },
        },
    },
}

# ---------------------------------------------------------------------------
# 校验函数
# ---------------------------------------------------------------------------
def validate_device(device: dict[str, Any]) -> list[str]:
    """校验设备 JSON 是否符合模型，返回错误列表（空列表 = 通过）。"""
    errors: list[str] = []

    if not isinstance(device, dict):
        return ["设备描述必须是 JSON 对象"]

    for field in ["id", "type", "name", "capabilities", "control"]:
        if field not in device:
            errors.append(f"缺少必需字段: {field}")

    if "type" in device and device["type"] not in DEVICE_TYPES:
        errors.append(f"未知设备类型: {device['type']}，应为 {DEVICE_TYPES} 之一")

    # capabilities 校验：能力名 + 动作名必须落在标准枚举内
    if "capabilities" in device and not isinstance(device["capabilities"], list):
        errors.append("capabilities 必须是数组")
    elif "capabilities" in device:
        for i, cap in enumerate(device["capabilities"]):
            if not isinstance(cap, dict):
                errors.append(f"capabilities[{i}] 必须是对象")
                continue

            name = cap.get("name")
            if name is None:
                errors.append(f"capabilities[{i}] 缺少 name")
            elif name not in CAPABILITIES:
                errors.append(
                    f"capabilities[{i}] 能力名 '{name}' 不在标准集合 {CAPABILITIES} 中"
                )

            actions = cap.get("actions")
            if not isinstance(actions, list):
                errors.append(f"capabilities[{i}] 缺少 actions 数组")
                continue
            for j, act in enumerate(actions):
                if not isinstance(act, dict):
                    errors.append(f"capabilities[{i}].actions[{j}] 必须是对象")
                    continue
                act_name = act.get("name")
                if act_name is None:
                    errors.append(f"capabilities[{i}].actions[{j}] 缺少 name")
                elif act_name not in ACTIONS:
                    errors.append(
                        f"capabilities[{i}].actions[{j}] 动作名 '{act_name}' "
                        f"不在标准集合 {ACTIONS} 中"
                    )

    # control 校验：协议名枚举
    control = device.get("control")
    if isinstance(control, dict):
        protocol = control.get("protocol")
        if protocol is not None and protocol not in (
            "mqtt", "http", "serial", "ble", "unknown",
        ):
            errors.append(
                f"未知协议: {protocol}，应为 mqtt/http/serial/ble/unknown 之一"
            )

    return errors


def dump_schema_prompt() -> str:
    """生成给 LLM 看的 Schema 提示文本（精简版，节省 token）。"""
    return json.dumps(DEVICE_SCHEMA, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 参考示例（few-shot，帮助 LLM 输出正确格式）
# ---------------------------------------------------------------------------
EXAMPLE_DEVICE: dict[str, Any] = {
    "id": "example-lamp",
    "type": "light",
    "name": "示例智能灯泡",
    "brand": "示例",
    "model": "L5",
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
            "properties": {"brightness": {"type": "integer", "unit": "%", "min": 1, "max": 100}},
            "actions": [{"name": "set_brightness", "params": {"brightness": {"type": "integer", "unit": "%"}}}],
        },
        {
            "name": "color",
            "properties": {"color": {"type": "object", "description": "RGB 颜色"}},
            "actions": [{"name": "set_color", "params": {"color": {"type": "object"}}}],
        },
    ],
    "control": {
        "protocol": "mqtt",
        "commands": {
            "turn_on": {"topic": "smarthome/lamp/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/lamp/set", "payload": {"power": "off"}},
            "set_brightness": {"topic": "smarthome/lamp/set", "payload": {"brightness": "{brightness}"}},
            "set_color": {"topic": "smarthome/lamp/set", "payload": {"color": "{color}"}},
        },
    },
}


def dump_example_prompt() -> str:
    """生成给 LLM 看的参考示例（few-shot）。"""
    return json.dumps(EXAMPLE_DEVICE, ensure_ascii=False, indent=2)
