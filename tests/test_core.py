"""离线单元测试：不依赖 LLM，验证核心逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.schema import validate_device  # noqa: E402
from devicemind.llm import extract_json  # noqa: E402
from devicemind.runtime import build_command, match_action  # noqa: E402
from devicemind.intent import IntentParser  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402


# 预置测试设备
def _sample_device():
    return {
        "id": "lamp-01",
        "type": "light",
        "name": "智能LED灯泡",
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
        ],
        "control": {
            "protocol": "mqtt",
            "commands": {
                "turn_on": {"topic": "smarthome/lamp01/set", "payload": {"power": "on"}},
                "turn_off": {"topic": "smarthome/lamp01/set", "payload": {"power": "off"}},
                "set_brightness": {"topic": "smarthome/lamp01/set", "payload": {"brightness": 80}},
            },
        },
    }


# ---------------------------------------------------------------------------
# schema 校验
# ---------------------------------------------------------------------------
def test_validate_legal_device():
    device = _sample_device()
    assert validate_device(device) == []


def test_validate_missing_field():
    device = {"id": "lamp-01", "type": "light"}
    errors = validate_device(device)
    assert any("name" in e or "capabilities" in e or "control" in e for e in errors)


def test_validate_unknown_type():
    device = {
        "id": "x",
        "type": "spaceship",
        "name": "飞船",
        "capabilities": [],
        "control": {"protocol": "unknown", "commands": {}},
    }
    assert any("未知设备类型" in e for e in validate_device(device))


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------
def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_block():
    raw = '```json\n{"a": 1}\n```'
    assert extract_json(raw) == {"a": 1}


def test_extract_json_with_noise():
    raw = '好的，以下是结果：\n{"a": 1}\n希望有帮助'
    assert extract_json(raw) == {"a": 1}


# ---------------------------------------------------------------------------
# runtime：动作匹配 + 指令生成
# ---------------------------------------------------------------------------
def test_match_action_exact():
    assert match_action(_sample_device(), "set_brightness") == "set_brightness"


def test_match_action_fuzzy():
    # 模糊匹配：intent 用 "brightness"，设备声明 "set_brightness"
    assert match_action(_sample_device(), "brightness") == "set_brightness"


def test_build_command_params_override():
    device = _sample_device()
    cmd = build_command(device, "set_brightness", {"brightness": 50})
    assert cmd.topic == "smarthome/lamp01/set"
    assert cmd.payload == {"brightness": 50}  # 覆盖默认 80


# ---------------------------------------------------------------------------
# intent：规则模式
# ---------------------------------------------------------------------------
def test_intent_rules_brightness():
    intent = IntentParser()._parse_with_rules("把灯调到50%", [_sample_device()])
    assert intent.action == "set_brightness"
    assert intent.params == {"brightness": 50}


def test_intent_rules_turn_on():
    intent = IntentParser()._parse_with_rules("打开", [_sample_device()])
    assert intent.action == "turn_on"


# ---------------------------------------------------------------------------
# simulator：状态更新
# ---------------------------------------------------------------------------
def test_simulator_state_update():
    device = _sample_device()
    hub = VirtualHub()
    vdev = VirtualDevice("lamp-01", "客厅灯", state={"power": "off"})
    hub.register(vdev)

    state = hub.send_command("lamp-01", build_command(device, "set_brightness", {"brightness": 50}))
    assert state["brightness"] == 50

    state = hub.send_command("lamp-01", build_command(device, "turn_on", {}))
    assert state["power"] == "on"
    assert len(vdev.history) == 2
