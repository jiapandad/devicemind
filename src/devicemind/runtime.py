"""
运行期核心 (Runtime)

把"动作 (action)"映射成"控制指令 (command)"。

流程：
  结构化意图 {device_id, action, params}
        │
        ▼
  查设备 JSON 的 control.commands
        │
        ▼
  生成控制指令 {protocol, topic/payload 或 endpoint}
        │
        ▼
  交给适配层（Phase 2 接真实设备，现在交给虚拟设备模拟器）

这是"运行期直接查 JSON、不碰 LLM"的关键实现。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    """一条控制指令。"""
    protocol: str
    topic: str | None = None
    payload: dict[str, Any] | None = None
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ActionNotFoundError(Exception):
    """设备不支持该动作。"""


class ParamOutOfRangeError(Exception):
    """参数超出设备允许范围。"""


def _normalize(name: str) -> str:
    """规范化名称：小写 + 去下划线/连字符，用于模糊匹配。"""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def match_action(device: dict[str, Any], action: str) -> str:
    """
    在设备声明的能力里查找匹配的动作名，返回规范的动作名。

    匹配策略：
    1. 精确匹配
    2. 模糊匹配（忽略大小写、下划线、连字符）
    3. 若 intent 的动作带前缀（如 set_brightness），尝试匹配后缀（brightness）
    """
    if not isinstance(device.get("capabilities"), list):
        raise ActionNotFoundError(f"设备 {device.get('id')} 无 capabilities 定义")

    candidates: list[str] = []
    for cap in device["capabilities"]:
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                candidates.append(act["name"])

    if not candidates:
        raise ActionNotFoundError(f"设备 {device.get('id')} 未声明任何动作")

    target = _normalize(action)

    # 1. 精确匹配
    for c in candidates:
        if _normalize(c) == target:
            return c

    # 2. 模糊匹配：候选包含目标 或 目标包含候选
    for c in candidates:
        nc = _normalize(c)
        if target and (nc in target or target in nc):
            return c

    raise ActionNotFoundError(
        f"设备不支持动作 '{action}'，可用动作: {candidates}"
    )


def validate_params(
    device: dict[str, Any],
    action: str,
    params: dict[str, Any],
) -> None:
    """
    校验参数是否在设备允许范围内，越界抛 ParamOutOfRangeError。

    用设备 capabilities 里 properties 的 min/max 做边界校验，
    拦截危险指令（如"空调调到 100 度"而范围是 16-30）。
    """
    if not params:
        return

    canonical_action = match_action(device, action)

    # 找到包含该动作的 capability
    for cap in device.get("capabilities", []):
        if not isinstance(cap, dict):
            continue
        action_names = [
            a.get("name") for a in cap.get("actions", []) if isinstance(a, dict)
        ]
        if canonical_action not in action_names:
            continue

        props = cap.get("properties", {})
        if not isinstance(props, dict):
            return

        for key, value in params.items():
            spec = props.get(key)
            if not isinstance(spec, dict):
                continue

            # 枚举校验：拦截非法取值（如 mode 传入说明书里没有的模式）
            enum_values = spec.get("enum")
            if isinstance(enum_values, list) and enum_values:
                if value not in enum_values:
                    raise ParamOutOfRangeError(
                        f"参数 {key}={value} 不在允许的枚举值内: {enum_values}"
                    )

            if "min" not in spec and "max" not in spec:
                continue

            # 尝试数值比较（非数值参数跳过）
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue

            if "min" in spec and v < float(spec["min"]):
                raise ParamOutOfRangeError(
                    f"参数 {key}={value} 低于下限 {spec['min']}"
                )
            if "max" in spec and v > float(spec["max"]):
                raise ParamOutOfRangeError(
                    f"参数 {key}={value} 超过上限 {spec['max']}"
                )
        return


def build_command(
    device: dict[str, Any],
    action: str,
    params: dict[str, Any] | None = None,
) -> Command:
    """
    根据设备 JSON 和动作，生成控制指令。

    参数:
        device: 编译后的设备描述 JSON
        action: 动作名（如 set_brightness）
        params: 动作参数（如 {"brightness": 50}）

    返回:
        Command 对象
    """
    params = params or {}

    # 规范化动作名（匹配设备声明）
    canonical_action = match_action(device, action)

    # 参数边界校验（拦截越界指令）
    validate_params(device, canonical_action, params)

    control = device.get("control", {})
    commands = control.get("commands", {})
    protocol = control.get("protocol", "unknown")

    # 查找命令模板
    template = _find_command(commands, canonical_action)
    if template is None:
        # 没有命令模板也能继续，protocol=unknown 时返回空指令
        return Command(protocol=protocol, topic=None, payload=None)

    topic = template.get("topic")
    endpoint = template.get("endpoint")
    payload_template = template.get("payload", {})

    # 用 params 填充 payload
    payload = _fill_payload(payload_template, params)

    return Command(
        protocol=protocol,
        topic=topic,
        endpoint=endpoint,
        payload=payload,
        extra=template.get("extra", {}),
    )


def _find_command(commands: dict[str, Any], action: str) -> dict[str, Any] | None:
    """在 commands 里查找动作对应的命令模板（支持模糊匹配）。"""
    if not isinstance(commands, dict):
        return None

    target = _normalize(action)
    for key, value in commands.items():
        if _normalize(key) == target:
            return value if isinstance(value, dict) else {}
    for key, value in commands.items():
        nk = _normalize(key)
        if target and (nk in target or target in nk):
            return value if isinstance(value, dict) else {}
    return None


def _fill_payload(
    template: dict[str, Any] | str | None,
    params: dict[str, Any],
) -> dict[str, Any] | str | None:
    """
    用 params 填充 payload 模板。

    支持两种模板：
    1. dict：{ "brightness": 80 } —— 用 params 同名键覆盖
    2. str："{brightness}" 或 "SET brightness=80" —— 替换占位符
    """
    if template is None:
        return None

    if isinstance(template, dict):
        result = dict(template)
        # 用 params 覆盖同名键
        for k, v in params.items():
            result[k] = v
        return result

    if isinstance(template, str):
        s = template
        # 替换 {param} 占位符
        for k, v in params.items():
            s = s.replace(f"{{{k}}}", str(v))
        return s

    return template
