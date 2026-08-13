"""设备协议命令构建（HA 集成侧的运行时模块）。

把「动作名 + 参数」映射成一条可发布的控制指令（topic + payload）。

注意：本文件是 src/devicemind/runtime.py 的 HA 侧镜像，接口保持对齐
（match_action / build_command / Command）。与 src 版本的区别是：
- 零 homeassistant 依赖、零 devicemind 依赖，可被 HA 集成直接 import
- 不包含参数边界校验（validate_params），HA 端参数已由前端 UI 约束

修改任一侧时，请同步检查另一侧是否也需要更新。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    """一条控制指令。"""

    protocol: str
    topic: str | None = None
    payload: Any = None
    endpoint: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _normalize(name: str) -> str:
    """规范化名称：小写 + 去下划线/连字符，用于模糊匹配。"""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def match_action(device: dict[str, Any], action: str) -> str:
    """
    在设备声明的能力里查找匹配的动作名，返回规范的动作名。

    匹配策略：
    1. 精确匹配
    2. 模糊匹配（忽略大小写、下划线、连字符）
    3. 若动作带前缀（如 set_brightness），尝试匹配后缀（brightness）
    """
    candidates: list[str] = []
    for cap in device.get("capabilities", []):
        if not isinstance(cap, dict):
            continue
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                candidates.append(act["name"])

    if not candidates:
        raise ValueError(f"设备 {device.get('id')} 未声明任何动作")

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

    raise ValueError(
        f"设备不支持动作 '{action}'，可用动作: {candidates}"
    )


def _find_command(commands: Any, action: str) -> dict[str, Any] | None:
    """在 control.commands 里查找动作对应的命令模板（支持模糊匹配）。"""
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


def _fill_payload(template: Any, params: dict[str, Any]) -> Any:
    """
    用 params 填充 payload 模板。

    支持两种模板：
    1. dict：{"brightness": 80} —— 用 params 同名键覆盖
    2. str："{brightness}" 或 "SET brightness=80" —— 替换占位符
    """
    if template is None:
        return None

    if isinstance(template, dict):
        result = dict(template)
        for k, v in params.items():
            result[k] = v
        return result

    if isinstance(template, str):
        s = template
        for k, v in params.items():
            s = s.replace(f"{{{k}}}", str(v))
        return s

    return template


def build_command(
    device: dict[str, Any],
    action: str,
    params: dict[str, Any] | None = None,
) -> Command:
    """
    根据设备协议 JSON 和动作，生成控制指令。

    参数:
        device: 编译后的设备描述 JSON
        action: 动作名（如 set_brightness）
        params: 动作参数（如 {"brightness": 50}）
    """
    params = params or {}

    canonical_action = match_action(device, action)

    control = device.get("control", {}) or {}
    commands = control.get("commands", {})
    protocol = control.get("protocol", "unknown")

    template = _find_command(commands, canonical_action)
    if template is None:
        return Command(protocol=protocol, topic=None, payload=None)

    topic = template.get("topic")
    endpoint = template.get("endpoint")
    payload = _fill_payload(template.get("payload", {}), params)

    return Command(
        protocol=protocol,
        topic=topic,
        endpoint=endpoint,
        payload=payload,
        extra=template.get("extra", {}),
    )


def command_payload_str(command: Command) -> str:
    """把指令的 payload 转成可发布的字符串（dict/list 序列化为 JSON）。"""
    if command.payload is None:
        return ""
    if isinstance(command.payload, str):
        return command.payload
    return json.dumps(command.payload, ensure_ascii=False)
