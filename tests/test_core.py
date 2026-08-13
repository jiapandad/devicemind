"""离线单元测试：不依赖 LLM，验证核心逻辑。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.schema import validate_device  # noqa: E402
from devicemind.llm import extract_json  # noqa: E402
from devicemind.runtime import build_command, match_action, validate_params, ParamOutOfRangeError  # noqa: E402
from devicemind.intent import IntentParser  # noqa: E402
from devicemind.simulator import VirtualDevice, VirtualHub  # noqa: E402
from devicemind.scene import SceneManager, Scene, SceneStep  # noqa: E402
from devicemind.verify import verify_device, pick_verify_action  # noqa: E402
from devicemind.automation import AutomationEngine, AutomationRule, weather, time, trigger_to_dict, trigger_from_dict  # noqa: E402
from devicemind.linkage import discover_linkages  # noqa: E402
from devicemind.compiler import DeviceCompiler, load_cached, save_cache  # noqa: E402
from devicemind.mqtt_hub import MqttHub  # noqa: E402
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
# 枚举参数校验（P0 安全）
# ---------------------------------------------------------------------------
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
    device = _mode_device()
    cmd = build_command(device, "set_mode", {"mode": "cool"})
    assert cmd.payload == {"mode": "cool"}


def test_param_validation_enum_invalid():
    device = _mode_device()
    try:
        build_command(device, "set_mode", {"mode": "烧烤"})
        assert False, "应拦截非法枚举值"
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


# ---------------------------------------------------------------------------
# 自动化规则引擎（环境感知）
# ---------------------------------------------------------------------------
def test_automation_edge_trigger():
    """边沿触发：条件从 False 变 True 只触发一次，持续满足不重复触发。"""
    lamp = _sample_device()
    hub = VirtualHub()
    hub.register(VirtualDevice("lamp-01", "灯", {"power": "off"}))

    engine = AutomationEngine()
    engine.add_rule(AutomationRule("深夜关灯", time("hour", "==", 23),
                                   [SceneStep("lamp-01", "turn_off", {})]))

    devices = {"lamp-01": lamp}

    # 白天不触发
    assert engine.tick({"time": {"hour": 9}}, devices, hub) == []
    # 23 点触发一次
    fired = engine.tick({"time": {"hour": 23}}, devices, hub)
    assert len(fired) == 1
    # 还是 23 点，不重复触发（边沿）
    assert engine.tick({"time": {"hour": 23}}, devices, hub) == []
    # 回到白天再触发才重新计数
    engine.tick({"time": {"hour": 9}}, devices, hub)
    assert len(engine.tick({"time": {"hour": 23}}, devices, hub)) == 1


def test_automation_weather_trigger():
    heater = {
        "id": "heater-01", "type": "other", "name": "暖气",
        "capabilities": [{"name": "power", "properties": {},
                          "actions": [{"name": "turn_on", "params": {}}]}],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "t/h", "payload": {"power": "on"}}}},
    }
    hub = VirtualHub()
    hub.register(VirtualDevice("heater-01", "暖气", {"power": "off"}))

    engine = AutomationEngine()
    engine.add_rule(AutomationRule("降温开暖气", weather("temp", "<", 10),
                                   [SceneStep("heater-01", "turn_on", {})]))

    devices = {"heater-01": heater}
    # 温度 15 不触发
    assert engine.tick({"weather": {"temp": 15}}, devices, hub) == []
    # 温度 5 触发
    assert len(engine.tick({"weather": {"temp": 5}}, devices, hub)) == 1
    assert hub.get("heater-01").get_state()["power"] == "on"


# ---------------------------------------------------------------------------
# 自动化规则持久化（trigger 无损序列化）
# ---------------------------------------------------------------------------
def test_trigger_roundtrip():
    """trigger 序列化后能无损还原，重启后规则仍可触发。"""
    trigger = weather("rain", "==", True)
    restored = trigger_from_dict(trigger_to_dict(trigger))
    assert restored.namespace == "weather"
    assert restored.field == "rain"
    assert restored.operator == "=="
    assert restored.value is True
    assert restored.evaluate({"weather": {"rain": True}}) is True
    assert restored.evaluate({"weather": {"rain": False}}) is False


def test_trigger_from_legacy_string_degraded():
    """旧格式（repr 字符串）无法还原，降级为永不触发，不应抛异常。"""
    restored = trigger_from_dict("weather.rain == True")
    assert restored.evaluate({"weather": {"rain": True}}) is False


# ---------------------------------------------------------------------------
# 设备联动自动发现
# ---------------------------------------------------------------------------
def test_discover_linkages():
    """新设备接入，根据能力自动发现联动。"""
    existing = {
        "curtain-01": {"id": "curtain-01", "type": "other", "name": "智能窗帘",
                       "capabilities": [], "control": {}},
        "heater-01": {"id": "heater-01", "type": "other", "name": "地暖暖气",
                      "capabilities": [], "control": {}},
    }
    # 雨水传感器 → 应发现"下雨关窗"
    rain_sensor = {"id": "rs-01", "type": "sensor", "name": "雨水传感器",
                   "capabilities": [{"name": "rain", "properties": {}, "actions": []}],
                   "control": {}}
    rules = discover_linkages(rain_sensor, existing)
    assert len(rules) == 1
    assert rules[0].name == "下雨自动关窗"
    assert rules[0].actions[0].device_id == "curtain-01"

    # 温湿度传感器 → 应发现"低温开暖气"（窗帘已有，但空气净化器没有所以只有暖气）
    th_sensor = {"id": "th-01", "type": "sensor", "name": "温湿度传感器",
                 "capabilities": [
                     {"name": "temperature", "properties": {}, "actions": []},
                     {"name": "air_quality", "properties": {}, "actions": []},
                 ],
                 "control": {}}
    rules2 = discover_linkages(th_sensor, existing)
    assert any(r.name == "低温自动开暖气" for r in rules2)
    # 空气净化器不存在，不应生成雾霾联动
    assert not any(r.name == "雾霾自动开净化器" for r in rules2)


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


# ---------------------------------------------------------------------------
# MQTT 适配层（纯内存接口，不连真实 Broker）
# ---------------------------------------------------------------------------
def test_mqtt_hub_register_and_state():
    hub = MqttHub()
    hub.register_device("lamp-01", "客厅灯", {"power": "off"})
    assert hub.list_devices() == ["lamp-01"]
    assert hub.get("lamp-01").get_state() == {"power": "off"}
    assert hub.get_all_states() == {"lamp-01": {"power": "off"}}


def test_mqtt_hub_restore_and_remove():
    hub = MqttHub()
    hub.register_device("lamp-01", "客厅灯", {})
    hub.restore_states({"lamp-01": {"brightness": 50}})
    assert hub.get("lamp-01").get_state()["brightness"] == 50

    hub.remove("lamp-01")
    assert hub.list_devices() == []
    assert hub.get_all_states() == {}


def test_mqtt_hub_probe_skips_verification():
    hub = MqttHub()
    hub.register_device("lamp-01", "客厅灯", {})
    # 真实设备无 expected_topic，试运行验证先跳过（返回 True）
    assert hub.probe("lamp-01", build_command(_sample_device(), "turn_on", {})) is True
