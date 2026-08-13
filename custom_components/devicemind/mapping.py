"""设备协议值 <-> HA 语义的双向映射（纯函数，零 homeassistant 依赖）。

解决设备协议里的取值（可能是中文/英文/档位）与 HA 枚举之间的转换问题。
核心原则：设备 -> HA 时做归一化；HA -> 设备时优先保留设备协议里的原始值。
"""

from __future__ import annotations

from typing import Any


# 语义 key 集合（与 HA 的 HVACMode 对应）
HVAC_KEYS = ("cool", "heat", "auto", "dry", "fan_only", "heat_cool")


def normalize_hvac_key(value: Any) -> str:
    """把设备协议里的模式值归一化为语义 key（cool/heat/auto/dry/fan_only/heat_cool）。"""
    v = str(value).strip().lower()
    if v in ("cool", "cooling", "制冷", "冷"):
        return "cool"
    if v in ("heat", "heating", "制热", "热", "暖"):
        return "heat"
    if v in ("auto", "自动"):
        return "auto"
    if v in ("dry", "dehumidify", "除湿"):
        return "dry"
    if v in ("fan", "fan_only", "送风"):
        return "fan_only"
    if v in ("heat_cool", "heatcool", "冷暖"):
        return "heat_cool"
    return "auto"


def reverse_hvac_value(key: str, device_modes: list[Any]) -> Any:
    """
    语义 key -> 设备协议里对应的原始模式值。

    优先在设备声明的 enum 里找语义匹配的原始值（保留中文/英文原文），
    找不到时回退返回 key 本身。
    """
    for dv in device_modes:
        if normalize_hvac_key(dv) == key:
            return dv
    return key


def map_fan_speed(percentage: int, fan_spec: dict[str, Any] | None) -> Any:
    """
    HA 百分比（0-100）-> 设备协议的 fan_speed 值。

    设备协议里 fan_speed 可能是档位（enum: [1,2,3,4,5]）或连续范围
    （min:1, max:100），按声明分派映射。
    """
    fan_spec = fan_spec or {}

    enum = fan_spec.get("enum")
    if isinstance(enum, list) and enum:
        idx = round((percentage / 100) * (len(enum) - 1))
        idx = max(0, min(len(enum) - 1, idx))
        return enum[idx]

    lo = float(fan_spec.get("min", 1))
    hi = float(fan_spec.get("max", 100))
    return round(lo + (percentage / 100) * (hi - lo))
