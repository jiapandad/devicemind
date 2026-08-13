"""
DeviceMind Web UI 后端 (WebApp)

用 Flask 把 DeviceMind 的各个模块串成 REST API，让普通用户通过浏览器使用。

启动：
    python -m devicemind.webapp
    # 或
    python scripts/run_web.py

然后浏览器打开 http://127.0.0.1:5000

API 一览：
    GET  /api/state                     整体状态（设备/场景/自动化/联动）
    GET  /api/devices                   设备列表 + 实时状态
    POST /api/devices/compile           说明书 -> 编译成设备 JSON（预览）
    POST /api/devices                   添加设备（编译好的 JSON 或说明书文本）
    POST /api/devices/<id>/command      控制设备（自然语言 或 结构化动作）
    POST /api/scenes/<name>/trigger     触发场景
    POST /api/automation/tick           模拟环境变化，触发自动化
    POST /api/automation/add            添加自动化规则
    POST /api/automation/reset          重置自动化边沿触发状态
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from devicemind import storage
from devicemind.automation import AutomationEngine, AutomationRule, weather, time
from devicemind.compiler import DeviceCompiler
from devicemind.intent import IntentParser
from devicemind.linkage import integrate_new_device
from devicemind.runtime import build_command
from devicemind.scene import SceneManager, SceneStep, demo_scenes
from devicemind.simulator import VirtualDevice, VirtualHub

# 前端静态文件目录（devicemind/web/）
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"


# ---------------------------------------------------------------------------
# 预置示例设备（让 Web UI 开箱即用，无需 LLM 也能演示完整功能）
# ---------------------------------------------------------------------------
def _cap(name: str, props: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "properties": props, "actions": actions}


def _act(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "params": params or {}}


PRESET_DEVICES: list[dict[str, Any]] = [
    {
        "id": "lamp-01", "type": "light", "name": "客厅灯",
        "brand": "示例", "model": "L1", "description": "智能 LED 灯，可调亮度与色温",
        "capabilities": [
            _cap("power", {}, [_act("turn_on"), _act("turn_off")]),
            _cap("brightness", {"brightness": {"type": "integer", "min": 1, "max": 100}},
                 [_act("set_brightness", {"brightness": {"type": "integer"}})]),
            _cap("color_temp", {"color_temp": {"type": "integer", "min": 2700, "max": 6500}},
                 [_act("set_color_temp", {"color_temp": {"type": "integer"}})]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "smarthome/lamp01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/lamp01/set", "payload": {"power": "off"}},
            "set_brightness": {"topic": "smarthome/lamp01/set", "payload": {"brightness": 80}},
            "set_color_temp": {"topic": "smarthome/lamp01/set", "payload": {"color_temp": 4000}},
        }},
    },
    {
        "id": "ac-01", "type": "climate", "name": "客厅空调",
        "brand": "示例", "model": "A2", "description": "变频空调，制冷制热",
        "capabilities": [
            _cap("power", {}, [_act("turn_on"), _act("turn_off")]),
            _cap("temperature", {"temperature": {"type": "integer", "min": 16, "max": 30}},
                 [_act("set_temperature", {"temperature": {"type": "integer"}})]),
            _cap("mode", {}, [_act("set_mode", {"mode": {"type": "string"}})]),
            _cap("fan_speed", {"fan_speed": {"type": "integer", "min": 1, "max": 5}},
                 [_act("set_fan_speed", {"fan_speed": {"type": "integer"}})]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "smarthome/ac01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/ac01/set", "payload": {"power": "off"}},
            "set_temperature": {"topic": "smarthome/ac01/set", "payload": {"temperature": 26}},
            "set_mode": {"topic": "smarthome/ac01/set", "payload": {"mode": "cool"}},
            "set_fan_speed": {"topic": "smarthome/ac01/set", "payload": {"fan_speed": 3}},
        }},
    },
    {
        "id": "curtain-01", "type": "switch", "name": "客厅窗帘",
        "brand": "示例", "model": "C1", "description": "电动窗帘",
        "capabilities": [
            _cap("power", {}, [_act("turn_on"), _act("turn_off")]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "smarthome/curtain01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/curtain01/set", "payload": {"power": "off"}},
        }},
    },
    {
        "id": "purifier-01", "type": "other", "name": "空气净化器",
        "brand": "示例", "model": "P1", "description": "空气净化器",
        "capabilities": [
            _cap("power", {}, [_act("turn_on"), _act("turn_off")]),
            _cap("mode", {}, [_act("set_mode", {"mode": {"type": "string"}})]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "smarthome/purifier01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/purifier01/set", "payload": {"power": "off"}},
            "set_mode": {"topic": "smarthome/purifier01/set", "payload": {"mode": "auto"}},
        }},
    },
    {
        "id": "heater-01", "type": "climate", "name": "暖气",
        "brand": "示例", "model": "H1", "description": "电暖器",
        "capabilities": [
            _cap("power", {}, [_act("turn_on"), _act("turn_off")]),
            _cap("temperature", {"temperature": {"type": "integer", "min": 10, "max": 30}},
                 [_act("set_temperature", {"temperature": {"type": "integer"}})]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "turn_on": {"topic": "smarthome/heater01/set", "payload": {"power": "on"}},
            "turn_off": {"topic": "smarthome/heater01/set", "payload": {"power": "off"}},
            "set_temperature": {"topic": "smarthome/heater01/set", "payload": {"temperature": 22}},
        }},
    },
    {
        "id": "sensor-temp", "type": "sensor", "name": "温湿度传感器",
        "brand": "示例", "model": "T1", "description": "环境温湿度检测",
        "capabilities": [
            _cap("temperature", {"temperature": {"type": "integer", "min": -20, "max": 60}},
                 [_act("get_state")]),
            _cap("humidity", {"humidity": {"type": "integer", "min": 0, "max": 100}},
                 [_act("get_state")]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "get_state": {"topic": "smarthome/temp01/get", "payload": {}},
        }},
    },
    {
        "id": "sensor-rain", "type": "sensor", "name": "雨水传感器",
        "brand": "示例", "model": "R1", "description": "检测是否下雨",
        "capabilities": [
            _cap("rain", {"rain": {"type": "boolean"}}, [_act("get_state")]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "get_state": {"topic": "smarthome/rain01/get", "payload": {}},
        }},
    },
    {
        "id": "sensor-motion", "type": "sensor", "name": "人体传感器",
        "brand": "示例", "model": "M1", "description": "检测人体移动",
        "capabilities": [
            _cap("motion", {"motion": {"type": "boolean"}}, [_act("get_state")]),
        ],
        "control": {"protocol": "mqtt", "commands": {
            "get_state": {"topic": "smarthome/motion01/get", "payload": {}},
        }},
    },
]

# 预置设备的初始状态
PRESET_STATES: dict[str, dict[str, Any]] = {
    "lamp-01": {"power": "off", "brightness": 80, "color_temp": 4000},
    "ac-01": {"power": "off", "temperature": 26, "mode": "cool", "fan_speed": 3},
    "curtain-01": {"power": "on"},
    "purifier-01": {"power": "off", "mode": "auto"},
    "heater-01": {"power": "off", "temperature": 22},
    "sensor-temp": {"temperature": 24, "humidity": 55},
    "sensor-rain": {"rain": False},
    "sensor-motion": {"motion": False},
}


# ---------------------------------------------------------------------------
# 应用状态（单例，持有所有运行时对象）
# ---------------------------------------------------------------------------
class AppState:
    """DeviceMind 运行时状态：设备、场景、自动化、联动。"""

    def __init__(self) -> None:
        self.devices: dict[str, dict[str, Any]] = {}
        self.hub = VirtualHub()
        self.scenes = SceneManager()
        self.automation = AutomationEngine()
        self.compiler = DeviceCompiler()
        self.intent = IntentParser()
        self.linkages: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    def init(self) -> None:
        """初始化：加载持久化数据或预置示例，注册设备、场景、自动化。"""
        self._load_devices()
        self._load_scenes()
        self._load_automations()

    def _load_devices(self) -> None:
        saved = storage.load_json("devices.json", None)
        if saved:
            self.devices = {d["id"]: d for d in saved}
        else:
            self.devices = {d["id"]: d for d in PRESET_DEVICES}

        states = storage.load_states()
        if not states:
            states = PRESET_STATES

        for device_id, device in self.devices.items():
            state = states.get(device_id, {})
            self.hub.register(VirtualDevice(device_id, device.get("name", device_id), state))

    def _load_scenes(self) -> None:
        saved = storage.load_scenes()
        if saved:
            self.scenes.scenes = {name: _scene_from_dict(s) for name, s in saved.items()}
        else:
            self.scenes = demo_scenes()

    def _load_automations(self) -> None:
        saved = storage.load_json("automations.json", None)
        if saved:
            for r in saved:
                self.automation.add_rule(_rule_from_dict(r))
            return

        # 预置自动化规则（边沿触发）
        presets = [
            ("下雨自动关窗", weather("rain", "==", True),
             [SceneStep("curtain-01", "turn_off", {})], "检测到下雨时关闭窗帘"),
            ("低温自动开暖气", weather("temp", "<", 10),
             [SceneStep("heater-01", "turn_on", {})], "温度低于 10 度时开启暖气"),
            ("雾霾自动开净化器", weather("aqi", ">", 150),
             [SceneStep("purifier-01", "turn_on", {})], "空气质量指数超过 150 时开启净化器"),
            ("有人移动自动开灯", weather("motion", "==", True),
             [SceneStep("lamp-01", "turn_on", {})], "检测到人体移动时开灯"),
            ("深夜自动关灯", time("hour", "==", 23),
             [SceneStep("lamp-01", "turn_off", {})], "晚上 11 点自动关灯"),
        ]
        for name, trigger, actions, desc in presets:
            self.automation.add_rule(AutomationRule(name, trigger, actions, desc))

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def devices_with_state(self) -> list[dict[str, Any]]:
        result = []
        for device_id, device in self.devices.items():
            item = dict(device)
            item["state"] = self.hub.get(device_id).get_state() if device_id in self.hub.devices else {}
            item["actions"] = _collect_actions(device)
            result.append(item)
        return result

    def scenes_data(self) -> list[dict[str, Any]]:
        return [self.scenes.get(n).to_dict() for n in self.scenes.list_scenes()]

    def automations_data(self) -> list[dict[str, Any]]:
        return [
            {
                "name": r.name,
                "description": r.description,
                "trigger": repr(r.trigger),
                "actions": [s.to_dict() for s in r.actions],
            }
            for r in self.automation.rules
        ]

    def persist(self) -> None:
        storage.save_json("devices.json", [self.devices[d] for d in self.devices])
        storage.save_states(self.hub.get_all_states())
        self.scenes.save()
        storage.save_json(
            "automations.json",
            [
                {"name": r.name, "trigger": repr(r.trigger),
                 "actions": [s.to_dict() for s in r.actions], "description": r.description}
                for r in self.automation.rules
            ],
        )


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------
def _scene_from_dict(data: dict[str, Any]):
    from devicemind.scene import Scene
    return Scene.from_dict(data)


def _rule_from_dict(data: dict[str, Any]) -> AutomationRule:
    """从持久化数据恢复自动化规则（简化：trigger 用 repr 字符串无法精确还原，降级为空触发）。"""
    from devicemind.automation import Trigger

    class _AlwaysFalse(Trigger):
        def evaluate(self, context):
            return False

    steps = [SceneStep(s["device_id"], s["action"], s.get("params", {})) for s in data.get("actions", [])]
    return AutomationRule(
        name=data["name"],
        trigger=_AlwaysFalse(),
        actions=steps,
        description=data.get("description", ""),
    )


def _collect_actions(device: dict[str, Any]) -> list[str]:
    result = []
    for cap in device.get("capabilities", []):
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                result.append(act["name"])
    return result


# ---------------------------------------------------------------------------
# Flask 应用
# ---------------------------------------------------------------------------
STATE = AppState()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    STATE.init()

    # ---- 前端页面 ----
    @app.route("/")
    def index():
        return send_from_directory(str(WEB_DIR), "index.html")

    @app.route("/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(str(WEB_DIR), filename)

    # ---- 状态总览 ----
    @app.route("/api/state", methods=["GET"])
    def api_state():
        return jsonify({"ok": True, "data": {
            "devices": STATE.devices_with_state(),
            "scenes": STATE.scenes_data(),
            "automations": STATE.automations_data(),
            "linkages": STATE.linkages,
        }})

    # ---- 设备 ----
    @app.route("/api/devices", methods=["GET"])
    def api_devices():
        return jsonify({"ok": True, "data": STATE.devices_with_state()})

    @app.route("/api/devices/compile", methods=["POST"])
    def api_compile():
        """说明书 -> 设备 JSON（预览，不加入系统）。"""
        body = request.get_json(silent=True) or {}
        manual_text = body.get("manual") or ""
        device_id = body.get("device_id") or ""
        name_hint = body.get("name_hint")

        if not manual_text.strip():
            return jsonify({"ok": False, "error": "说明书内容为空"}), 400

        try:
            device = STATE.compiler.compile(manual_text, device_id or "preview", name_hint)
            return jsonify({"ok": True, "data": device})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"编译失败：{exc}"}), 500

    @app.route("/api/devices", methods=["POST"])
    def api_add_device():
        """
        添加设备。支持两种 body：
        1. {"manual": "...", "device_id": "...", "name_hint": "..."}  说明书文本，走 LLM 编译
        2. {"device": {...}}                                         已编译好的设备 JSON
        """
        body = request.get_json(silent=True) or {}

        if "device" in body:
            device = body["device"]
        else:
            manual_text = body.get("manual", "")
            device_id = body.get("device_id", "")
            name_hint = body.get("name_hint")
            if not manual_text.strip():
                return jsonify({"ok": False, "error": "请提供说明书内容或设备 JSON"}), 400
            try:
                device = STATE.compiler.compile(manual_text, device_id or f"device-{len(STATE.devices)+1}", name_hint)
            except Exception as exc:  # noqa: BLE001
                return jsonify({"ok": False, "error": f"编译失败：{exc}"}), 500

        device_id = device.get("id")
        if not device_id:
            return jsonify({"ok": False, "error": "设备缺少 id"}), 400

        is_new = device_id not in STATE.devices
        STATE.devices[device_id] = device
        if device_id not in STATE.hub.devices:
            STATE.hub.register(VirtualDevice(device_id, device.get("name", device_id), {}))

        # 自动联动发现
        new_linkages: list[str] = []
        if is_new:
            other_devices = {k: v for k, v in STATE.devices.items() if k != device_id}
            new_linkages = integrate_new_device(device, other_devices, STATE.automation)
            for name in new_linkages:
                STATE.linkages.append({
                    "device": device.get("name", device_id),
                    "rule": name,
                })

        STATE.persist()
        return jsonify({
            "ok": True,
            "data": device,
            "linkages": new_linkages,
            "message": f"设备 {device.get('name', device_id)} 已接入，自动生成 {len(new_linkages)} 条联动",
        })

    @app.route("/api/devices/<device_id>/command", methods=["POST"])
    def api_command(device_id: str):
        """
        控制设备。body 二选一：
        1. {"text": "调到50%"}                    自然语言（LLM/规则解析）
        2. {"action": "set_brightness", "params": {"brightness": 50}}
        """
        device = STATE.devices.get(device_id)
        if device is None:
            return jsonify({"ok": False, "error": f"设备不存在: {device_id}"}), 404

        body = request.get_json(silent=True) or {}

        if "text" in body:
            text = body["text"]
            try:
                intent = STATE.intent.parse(text, [device], STATE.hub.get_all_states())
                action = intent.action
                params = intent.params
                if intent.device_id and intent.device_id != device_id:
                    return jsonify({"ok": False, "error": f"指令指向其他设备: {intent.device_id}"}), 400
            except Exception as exc:  # noqa: BLE001
                return jsonify({"ok": False, "error": f"无法理解指令：{exc}"}), 400
        else:
            action = body.get("action", "")
            params = body.get("params") or {}
            if not action:
                return jsonify({"ok": False, "error": "缺少 action 或 text"}), 400

        try:
            command = build_command(device, action, params)
            state = STATE.hub.send_command(device_id, command)
            STATE.persist()
            return jsonify({
                "ok": True,
                "data": {
                    "device_id": device_id,
                    "action": action,
                    "payload": command.payload,
                    "topic": command.topic,
                    "state": state,
                },
            })
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "error": f"执行失败：{exc}"}), 400

    # ---- 场景 ----
    @app.route("/api/scenes/<name>/trigger", methods=["POST"])
    def api_trigger_scene(name: str):
        try:
            results = STATE.scenes.trigger(name, STATE.devices, STATE.hub)
            STATE.persist()
            return jsonify({"ok": True, "data": results})
        except KeyError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404

    # ---- 自动化 ----
    @app.route("/api/automation/tick", methods=["POST"])
    def api_automation_tick():
        """模拟环境变化，触发自动化规则。body: {"weather": {...}, "time": {...}}"""
        context = request.get_json(silent=True) or {}
        results = STATE.automation.tick(context, STATE.devices, STATE.hub)
        STATE.persist()
        return jsonify({"ok": True, "data": results})

    @app.route("/api/automation/add", methods=["POST"])
    def api_automation_add():
        body = request.get_json(silent=True) or {}
        name = body.get("name", "")
        trigger_spec = body.get("trigger", {})  # {namespace, field, operator, value}
        actions_spec = body.get("actions", [])   # [{device_id, action, params}]

        if not name or not trigger_spec or not actions_spec:
            return jsonify({"ok": False, "error": "缺少 name/trigger/actions"}), 400

        from devicemind.automation import FieldTrigger
        trigger = FieldTrigger(
            trigger_spec.get("namespace", "weather"),
            trigger_spec.get("field"),
            trigger_spec.get("operator", "=="),
            trigger_spec.get("value"),
        )
        steps = [SceneStep(a["device_id"], a["action"], a.get("params", {})) for a in actions_spec]
        STATE.automation.add_rule(AutomationRule(name, trigger, steps, body.get("description", "")))
        STATE.persist()
        return jsonify({"ok": True, "data": {"name": name}})

    @app.route("/api/automation/reset", methods=["POST"])
    def api_automation_reset():
        STATE.automation.reset()
        return jsonify({"ok": True})

    return app


app = create_app()


def main() -> None:
    print("=" * 60)
    print("  DeviceMind Web UI 已启动")
    print("  请在浏览器打开: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
