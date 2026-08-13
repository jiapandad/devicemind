"""测试设备协议值 <-> HA 语义的双向映射（mapping.py 纯函数，零依赖）。

mapping.py 位于 custom_components/devicemind/，该包的 __init__.py 依赖
homeassistant，故用 importlib 直接加载 mapping.py 文件本身，绕过包入口。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "devicemind" / "mapping.py"

_spec = importlib.util.spec_from_file_location("devicemind_mapping", _MAPPING_PATH)
_mapping = importlib.util.module_from_spec(_spec)
sys.modules["devicemind_mapping"] = _mapping
_spec.loader.exec_module(_mapping)

map_fan_speed = _mapping.map_fan_speed
normalize_hvac_key = _mapping.normalize_hvac_key
reverse_hvac_value = _mapping.reverse_hvac_value


# ---------------------------------------------------------------------------
# normalize_hvac_key：设备模式值 -> 语义 key
# ---------------------------------------------------------------------------
def test_normalize_chinese_modes():
    assert normalize_hvac_key("制冷") == "cool"
    assert normalize_hvac_key("制热") == "heat"
    assert normalize_hvac_key("自动") == "auto"
    assert normalize_hvac_key("除湿") == "dry"
    assert normalize_hvac_key("送风") == "fan_only"


def test_normalize_english_modes():
    assert normalize_hvac_key("cool") == "cool"
    assert normalize_hvac_key("heating") == "heat"
    assert normalize_hvac_key("AUTO") == "auto"
    assert normalize_hvac_key("dehumidify") == "dry"


# ---------------------------------------------------------------------------
# reverse_hvac_value：语义 key -> 设备协议原始值（保留原文）
# ---------------------------------------------------------------------------
def test_reverse_preserves_chinese_original():
    # 设备 enum 是中文，反向映射应返回中文原文而非英文
    modes = ["制冷", "制热", "自动"]
    assert reverse_hvac_value("cool", modes) == "制冷"
    assert reverse_hvac_value("heat", modes) == "制热"
    assert reverse_hvac_value("auto", modes) == "自动"


def test_reverse_english_original():
    modes = ["cool", "heat"]
    assert reverse_hvac_value("cool", modes) == "cool"
    assert reverse_hvac_value("heat", modes) == "heat"


def test_reverse_fallback_to_key():
    # enum 为空时回退返回 key 本身
    assert reverse_hvac_value("cool", []) == "cool"


# ---------------------------------------------------------------------------
# map_fan_speed：HA 百分比 -> 设备 fan_speed 值
# ---------------------------------------------------------------------------
def test_map_fan_speed_enum_levels():
    # 档位型：百分比映射到 enum 里的档位
    spec = {"enum": [1, 2, 3, 4, 5]}
    assert map_fan_speed(0, spec) == 1
    assert map_fan_speed(50, spec) == 3
    assert map_fan_speed(100, spec) == 5


def test_map_fan_speed_range():
    # 连续范围型：百分比映射到 min-max 范围
    spec = {"min": 1, "max": 100}
    assert map_fan_speed(0, spec) == 1
    assert map_fan_speed(100, spec) == 100
    assert map_fan_speed(25, spec) == 26  # 1 + 25/100*99 = 25.75 -> 26


def test_map_fan_speed_string_enum():
    # 字符串档位（低/中/高）
    spec = {"enum": ["低", "中", "高"]}
    assert map_fan_speed(0, spec) == "低"
    assert map_fan_speed(50, spec) == "中"
    assert map_fan_speed(100, spec) == "高"
