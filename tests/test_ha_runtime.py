"""测试 HA 集成侧的指令构建模块（custom_components/devicemind/runtime.py）。

该模块是「设备协议 JSON → 控制指令」的核心逻辑，零依赖纯函数，
是 HA 集成里最值得用单元测试锁定的部分。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_RUNTIME_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "devicemind" / "runtime.py"
)

_spec = importlib.util.spec_from_file_location("devicemind_runtime", _RUNTIME_PATH)
_runtime = importlib.util.module_from_spec(_spec)
sys.modules["devicemind_runtime"] = _runtime
_spec.loader.exec_module(_runtime)

build_command = _runtime.build_command
match_action = _runtime.match_action
command_payload_str = _runtime.command_payload_str


# 一个带 power + brightness 能力的灯设备
def _light_device() -> dict:
    return {
        "id": "lamp-01",
        "type": "light",
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
                "properties": {"brightness": {"type": "integer", "min": 1, "max": 100}},
                "actions": [
                    {"name": "set_brightness", "params": {"brightness": {"type": "integer"}}}
                ],
            },
        ],
        "control": {
            "protocol": "mqtt",
            "commands": {
                "turn_on": {"topic": "smarthome/lamp/set", "payload": {"power": "on"}},
                "turn_off": {"topic": "smarthome/lamp/set", "payload": {"power": "off"}},
                "set_brightness": {
                    "topic": "smarthome/lamp/set",
                    "payload": {"brightness": "{brightness}"},
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# match_action：动作名模糊匹配
# ---------------------------------------------------------------------------
def test_match_action_exact():
    assert match_action(_light_device(), "turn_on") == "turn_on"


def test_match_action_case_and_separator_insensitive():
    # 忽略大小写和下划线
    assert match_action(_light_device(), "TurnOn") == "turn_on"
    assert match_action(_light_device(), "set-brightness") == "set_brightness"


def test_match_action_suffix_match():
    # 动作带额外前缀时，回退匹配后缀
    device = _light_device()
    device["capabilities"][1]["actions"] = [{"name": "brightness", "params": {}}]
    assert match_action(device, "set_brightness") == "brightness"


def test_match_action_unknown_raises():
    with pytest.raises(ValueError):
        match_action(_light_device(), "start_cleaning")


# ---------------------------------------------------------------------------
# build_command：指令构建
# ---------------------------------------------------------------------------
def test_build_command_dict_payload():
    cmd = build_command(_light_device(), "turn_on")
    assert cmd.protocol == "mqtt"
    assert cmd.topic == "smarthome/lamp/set"
    assert cmd.payload == {"power": "on"}


def test_build_command_string_placeholder():
    cmd = build_command(_light_device(), "set_brightness", {"brightness": 50})
    assert cmd.payload == {"brightness": 50}


def test_build_command_missing_command_returns_no_topic():
    # 设备声明了动作但 control.commands 里没有对应模板
    device = _light_device()
    device["control"]["commands"] = {}
    cmd = build_command(device, "turn_on")
    assert cmd.topic is None


def test_build_command_http_endpoint():
    device = {
        "id": "h1",
        "type": "switch",
        "capabilities": [
            {"name": "power", "properties": {}, "actions": [{"name": "turn_on", "params": {}}]}
        ],
        "control": {
            "protocol": "http",
            "commands": {
                "turn_on": {"endpoint": "http://192.168.1.10/on", "payload": {"cmd": "on"}}
            },
        },
    }
    cmd = build_command(device, "turn_on")
    assert cmd.protocol == "http"
    assert cmd.endpoint == "http://192.168.1.10/on"
    assert cmd.topic is None


# ---------------------------------------------------------------------------
# command_payload_str：payload 序列化
# ---------------------------------------------------------------------------
def test_command_payload_str_dict():
    cmd = build_command(_light_device(), "turn_on")
    assert command_payload_str(cmd) == '{"power": "on"}'


def test_command_payload_str_none():
    cmd = build_command(_light_device(), "turn_on")
    cmd.payload = None
    assert command_payload_str(cmd) == ""
