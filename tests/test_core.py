"""离线单元测试：不依赖 LLM，验证核心逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.schema import validate_device  # noqa: E402
from devicemind.llm import extract_json  # noqa: E402
from devicemind.runtime import build_command, match_action, validate_params, ParamOutOfRangeError  # noqa: E402
from devicemind.intent import IntentParser  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402
from devicemind.scene import SceneManager, Scene, SceneStep  # noqa: E402
from devicemind.verify import verify_device, pick_verify_action  # noqa: E402
from devicemind import storage  # noqa: E402


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


# ---------------------------------------------------------------------------
# 参数边界校验（P0 安全）
# ---------------------------------------------------------------------------
def test_param_validation_in_range():
    device = _sample_device()
    cmd = build_command(device, "set_brightness", {"brightness": 50})
    assert cmd.payload == {"brightness": 50}


def test_param_validation_out_of_range():
    device = _sample_device()
    try:
        build_command(device, "set_brightness", {"brightness": 200})
        assert False, "应拦截越界参数"
    except ParamOutOfRangeError:
        pass


# ---------------------------------------------------------------------------
# 意图上下文记忆（P1）
# ---------------------------------------------------------------------------
def test_intent_context_relative():
    lamp = _sample_device()
    parser = IntentParser()
    # 有状态 brightness=70，"再暗一点" -> 50
    intent = parser._parse_with_rules("再暗一点", [lamp], {"lamp-01": {"brightness": 70}})
    assert intent.params == {"brightness": 50}


def test_intent_context_absolute_priority():
    lamp = _sample_device()
    parser = IntentParser()
    # 明确百分比优先于上下文
    intent = parser._parse_with_rules("调到80%", [lamp], {"lamp-01": {"brightness": 30}})
    assert intent.params == {"brightness": 80}


# ---------------------------------------------------------------------------
# 场景编排（P1）
# ---------------------------------------------------------------------------
def _climate_device():
    return {
        "id": "ac-01",
        "type": "climate",
        "name": "空调",
        "capabilities": [
            {"name": "power", "properties": {},
             "actions": [{"name": "turn_on", "params": {}}, {"name": "turn_off", "params": {}}]},
            {"name": "temperature", "properties": {"temperature": {"min": 16, "max": 30}},
             "actions": [{"name": "set_temperature", "params": {}}]},
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "t/ac", "payload": {"power": "on"}},
            "turn_off": {"topic": "t/ac", "payload": {"power": "off"}},
            "set_temperature": {"topic": "t/ac", "payload": {"temperature": 26}},
        }},
    }


def test_scene_trigger_multi_device():
    lamp = _sample_device()
    ac = _climate_device()
    hub = VirtualHub()
    hub.register(VirtualDevice("lamp-01", "灯", {"power": "off"}))
    hub.register(VirtualDevice("ac-01", "空调", {"power": "off"}))

    mgr = SceneManager()
    mgr.add(Scene(name="回家模式", steps=[
        SceneStep("lamp-01", "turn_on", {}),
        SceneStep("ac-01", "set_temperature", {"temperature": 26}),
    ]))

    results = mgr.trigger("回家模式", {"lamp-01": lamp, "ac-01": ac}, hub)
    assert len(results) == 2
    assert hub.get("lamp-01").get_state()["power"] == "on"
    assert hub.get("ac-01").get_state()["temperature"] == 26


def test_scene_missing_device_tolerated():
    lamp = _sample_device()
    hub = VirtualHub()
    hub.register(VirtualDevice("lamp-01", "灯", {"power": "off"}))

    mgr = SceneManager()
    mgr.add(Scene(name="测试", steps=[
        SceneStep("lamp-01", "turn_on", {}),
        SceneStep("ghost-01", "turn_off", {}),
    ]))

    results = mgr.trigger("测试", {"lamp-01": lamp}, hub)
    assert "error" in results[1]  # 第二个设备不存在，容错记录 error
    assert hub.get("lamp-01").get_state()["power"] == "on"


# ---------------------------------------------------------------------------
# 编译试运行验证闭环（P0）
# ---------------------------------------------------------------------------
def test_verify_correct_topic():
    device = _sample_device()
    hub = VirtualHub()
    hub.register(VirtualDevice("lamp-01", "灯", expected_topic="smarthome/lamp01/set"))

    ok, err = verify_device(device, hub, "lamp-01")
    assert ok, err


def test_verify_wrong_topic():
    device = _sample_device()
    device["control"]["commands"]["turn_on"]["topic"] = "wrong/topic"
    hub = VirtualHub()
    hub.register(VirtualDevice("lamp-01", "灯", expected_topic="smarthome/lamp01/set"))

    ok, err = verify_device(device, hub, "lamp-01")
    assert not ok
    assert "topic" in err


def test_pick_verify_action():
    device = _sample_device()
    # 无 get_state，应退回 turn_on
    assert pick_verify_action(device) == "turn_on"


# ---------------------------------------------------------------------------
# 持久化（P2）
# ---------------------------------------------------------------------------
def test_storage_states_roundtrip():
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_DATA"] = tmp
    storage.save_states({"lamp-01": {"power": "on", "brightness": 50}})
    loaded = storage.load_states()
    assert loaded["lamp-01"]["brightness"] == 50


def test_scene_save_load_roundtrip():
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    os.environ["DEVICEMIND_DATA"] = tmp
    mgr = SceneManager()
    mgr.add(Scene(name="回家模式", steps=[SceneStep("lamp-01", "turn_on", {})]))
    mgr.save()

    mgr2 = SceneManager()
    mgr2.load()
    assert "回家模式" in mgr2.list_scenes()
    assert mgr2.get("回家模式").steps[0].action == "turn_on"


# ---------------------------------------------------------------------------
# 熔断降级（P2）
# ---------------------------------------------------------------------------
class _FailingClient:
    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        raise Exception("LLM 挂了")


def test_intent_circuit_breaker():
    client = _FailingClient()
    parser = IntentParser(client=client, failure_threshold=2)
    lamp = _sample_device()

    # 第 1 次失败回退规则
    assert parser.parse("打开", [lamp]).action == "turn_on"
    # 第 2 次失败触发熔断
    parser.parse("关闭", [lamp])
    assert parser._llm_disabled is True
    # 熔断后不再调 LLM
    calls = client.calls
    parser.parse("调到50%", [lamp])
    assert client.calls == calls
