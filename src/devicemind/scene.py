"""
场景编排 (Scene)

一个场景 = 一个自然语言意图触发多设备的动作序列。

例如"回家模式"：
    开玄关灯 → 开客厅空调 26°C → 关窗帘 → 开音箱

这是"说人话就能控制"的产品价值核心：用户不用逐条下指令，
一个场景名就能联动整个家。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from devicemind.runtime import build_command


@dataclass
class SceneStep:
    """场景中的一个动作步骤。"""
    device_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"device_id": self.device_id, "action": self.action, "params": self.params}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SceneStep":
        return cls(data["device_id"], data["action"], data.get("params", {}))


@dataclass
class Scene:
    """一个场景（多设备动作序列）。"""
    name: str
    steps: list[SceneStep]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=[SceneStep.from_dict(s) for s in data.get("steps", [])],
        )


class SceneManager:
    """管理场景定义与触发。"""

    def __init__(self) -> None:
        self.scenes: dict[str, Scene] = {}

    # ------------------------------------------------------------------
    def add(self, scene: Scene) -> None:
        self.scenes[scene.name] = scene

    def get(self, name: str) -> Scene:
        if name not in self.scenes:
            raise KeyError(f"场景不存在: {name}，可用场景: {list(self.scenes.keys())}")
        return self.scenes[name]

    def list_scenes(self) -> list[str]:
        return list(self.scenes.keys())

    # ------------------------------------------------------------------
    def save(self, path: str | None = None) -> None:
        """保存场景配置到磁盘（默认用 storage 模块的数据目录）。"""
        from devicemind.storage import save_scenes

        data = {name: s.to_dict() for name, s in self.scenes.items()}
        if path:
            from devicemind.storage import save_json
            save_json(path, data)
        else:
            save_scenes(data)

    def load(self, path: str | None = None) -> None:
        """从磁盘加载场景配置（覆盖当前场景）。"""
        from devicemind.storage import load_scenes, load_json

        data = load_json(path) if path else load_scenes()
        self.scenes = {name: Scene.from_dict(s) for name, s in data.items()}

    # ------------------------------------------------------------------
    def trigger(
        self,
        scene_name: str,
        devices: dict[str, dict[str, Any]],
        hub: Any,
    ) -> list[dict[str, Any]]:
        """
        触发场景：依次执行所有步骤，返回每步的执行结果。

        参数:
            scene_name: 场景名
            devices: {device_id: 设备 JSON}
            hub: 设备执行器（VirtualHub 或未来的真实 MQTT hub），需有 send_command 方法

        返回:
            每步结果列表 [{device_id, action, payload, state}]
        """
        scene = self.get(scene_name)
        results: list[dict[str, Any]] = []

        for step in scene.steps:
            device = devices.get(step.device_id)
            if device is None:
                results.append({
                    "device_id": step.device_id,
                    "action": step.action,
                    "error": f"设备不存在: {step.device_id}",
                })
                continue

            command = build_command(device, step.action, step.params)
            state = hub.send_command(step.device_id, command)
            results.append({
                "device_id": step.device_id,
                "action": step.action,
                "payload": command.payload,
                "state": state,
            })

        return results


# ---------------------------------------------------------------------------
# 预置示例场景
# ---------------------------------------------------------------------------
def demo_scenes() -> SceneManager:
    """返回一个带示例场景的 SceneManager，用于演示和测试。"""
    mgr = SceneManager()

    mgr.add(Scene(
        name="回家模式",
        description="回到家：开灯 + 开空调 26 度",
        steps=[
            SceneStep("lamp-01", "turn_on", {}),
            SceneStep("ac-01", "turn_on", {}),
            SceneStep("ac-01", "set_temperature", {"temperature": 26}),
        ],
    ))

    mgr.add(Scene(
        name="离家模式",
        description="离开家：关灯 + 关空调 + 关窗帘",
        steps=[
            SceneStep("lamp-01", "turn_off", {}),
            SceneStep("ac-01", "turn_off", {}),
            SceneStep("curtain-01", "turn_off", {}),
        ],
    ))

    mgr.add(Scene(
        name="睡眠模式",
        description="睡觉：关灯 + 空调调到 24 度",
        steps=[
            SceneStep("lamp-01", "turn_off", {}),
            SceneStep("ac-01", "set_temperature", {"temperature": 24}),
        ],
    ))

    return mgr
