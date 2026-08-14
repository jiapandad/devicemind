"""离线单元测试：不依赖 LLM 和真实硬件，验证核心编译链路。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.schema import validate_device  # noqa: E402
from devicemind.llm import extract_json  # noqa: E402
from devicemind.runtime import build_command, match_action, ParamOutOfRangeError  # noqa: E402
from devicemind.verify import verify_device, pick_verify_action  # noqa: E402
from devicemind.compiler import DeviceCompiler, load_cached, save_cache  # noqa: E402


# ---------------------------------------------------------------------------
# 预置测试设备
# ---------------------------------------------------------------------------
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
    assert validate_device(_sample_device()) == []


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


def test_validate_unknown_capability():
    device = {
        "id": "x",
        "type": "light",
        "name": "灯",
        "capabilities": [{"name": "laser", "properties": {}, "actions": []}],
        "control": {"protocol": "unknown", "commands": {}},
    }
    assert any("能力名" in e for e in validate_device(device))


def test_validate_unknown_action():
    device = {
        "id": "x",
        "type": "lock",
        "name": "门锁",
        "capabilities": [
            {
                "name": "lock_state",
                "properties": {},
                "actions": [{"name": "set_lock_state", "params": {}}],
            }
        ],
        "control": {"protocol": "unknown", "commands": {}},
    }
    assert any("动作名" in e for e in validate_device(device))


def test_validate_unknown_protocol():
    device = {
        "id": "x",
        "type": "light",
        "name": "灯",
        "capabilities": [],
        "control": {"protocol": "carrier_pigeon", "commands": {}},
    }
    assert any("未知协议" in e for e in validate_device(device))


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
    assert match_action(_sample_device(), "brightness") == "set_brightness"


def test_build_command_params_override():
    cmd = build_command(_sample_device(), "set_brightness", {"brightness": 50})
    assert cmd.topic == "smarthome/lamp01/set"
    assert cmd.payload == {"brightness": 50}


# ---------------------------------------------------------------------------
# 参数边界校验（P0 安全）
# ---------------------------------------------------------------------------
def test_param_validation_in_range():
    cmd = build_command(_sample_device(), "set_brightness", {"brightness": 50})
    assert cmd.payload == {"brightness": 50}


def test_param_validation_out_of_range():
    try:
        build_command(_sample_device(), "set_brightness", {"brightness": 200})
        assert False, "应拦截越界参数"
    except ParamOutOfRangeError:
        pass


def _mode_device():
    return {
        "id": "ac-01",
        "type": "climate",
        "name": "空调",
        "capabilities": [
            {"name": "power", "properties": {},
             "actions": [{"name": "turn_on", "params": {}}]},
            {"name": "mode", "properties": {"mode": {"type": "string", "enum": ["cool", "heat", "auto"]}},
             "actions": [{"name": "set_mode", "params": {"mode": {"type": "string"}}}]},
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "t/ac", "payload": {"power": "on"}},
            "set_mode": {"topic": "t/ac", "payload": {"mode": "auto"}},
        }},
    }


def test_param_validation_enum_valid():
    cmd = build_command(_mode_device(), "set_mode", {"mode": "cool"})
    assert cmd.payload == {"mode": "cool"}


def test_param_validation_enum_invalid():
    try:
        build_command(_mode_device(), "set_mode", {"mode": "烧烤"})
        assert False, "应拦截非法枚举值"
    except ParamOutOfRangeError:
        pass


# ---------------------------------------------------------------------------
# 编译试运行验证闭环（P0）
# ---------------------------------------------------------------------------
class _FakeHub:
    """模拟设备执行器：根据 expected_topic 判断 probe 是否命中。"""

    def __init__(self, expected_topic: str | None):
        self.expected_topic = expected_topic

    def probe(self, device_id: str, command) -> bool:
        if self.expected_topic is None:
            return True
        return command.topic == self.expected_topic


def test_verify_correct_topic():
    hub = _FakeHub("smarthome/lamp01/set")
    ok, err = verify_device(_sample_device(), hub, "lamp-01")
    assert ok, err


def test_verify_wrong_topic():
    device = _sample_device()
    device["control"]["commands"]["turn_on"]["topic"] = "wrong/topic"
    hub = _FakeHub("smarthome/lamp01/set")
    ok, err = verify_device(device, hub, "lamp-01")
    assert not ok
    assert "topic" in err


def test_pick_verify_action():
    # 无 get_state，应退回 turn_on
    assert pick_verify_action(_sample_device()) == "turn_on"


# ---------------------------------------------------------------------------
# 编译缓存（P2）
# ---------------------------------------------------------------------------
class _MockLLMClient:
    """记录调用次数，返回合法设备 JSON，用于验证缓存命中不重复调 LLM。"""

    def __init__(self):
        self.calls = 0

    def chat(self, messages, json_mode=False, max_tokens=2048):
        self.calls += 1
        return json.dumps(_sample_device())


def test_cache_save_load_hash_match():
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_CACHE"] = tmp
    save_cache("lamp-01", _sample_device(), "abc123")
    cached = load_cached("lamp-01", "abc123")
    assert cached is not None
    assert cached["id"] == "lamp-01"


def test_cache_hash_mismatch_invalidates():
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_CACHE"] = tmp
    save_cache("lamp-01", _sample_device(), "abc123")
    assert load_cached("lamp-01", "different-hash") is None


def test_compile_uses_cache():
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_CACHE"] = tmp
    client = _MockLLMClient()
    compiler = DeviceCompiler(client=client)

    manual = "产品：智能灯，支持开关和亮度调节"
    d1 = compiler.compile(manual, "lamp-01")
    assert client.calls == 1
    # 相同说明书第二次编译命中缓存，不再调 LLM
    d2 = compiler.compile(manual, "lamp-01")
    assert client.calls == 1
    assert d2 == d1
    # 说明书变更（hash 不同）重新编译
    compiler.compile(manual + "，另有色温调节", "lamp-01")
    assert client.calls == 2


def test_compile_feedback_skips_cache():
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_CACHE"] = tmp
    client = _MockLLMClient()
    compiler = DeviceCompiler(client=client)

    manual = "产品：智能灯"
    compiler.compile(manual, "lamp-01")
    assert client.calls == 1
    # 纠错重编译（feedback 非空）必须重新走 LLM，不能吃缓存
    compiler.compile(manual, "lamp-01", feedback="topic 错误")
    assert client.calls == 2
