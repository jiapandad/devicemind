"""
自动化规则引擎 (Automation)

环境感知 + 自动执行 —— DeviceMind 从"被动控制"进化到"主动服务"：

  触发条件（天气/时间/设备事件）→ 自动化规则 → 动作序列（复用 SceneStep）

触发源设计成可模拟的（MockWeather / 任意 context dict），
这样下雨关窗、降温开暖气、定时关灯等场景都能在虚拟环境验证，无需实机。

将来接真实数据源（和风天气 API 等）时，只需替换 context 的提供方。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from devicemind.scene import SceneStep


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """比较操作。"""
    if operator == "==":
        return actual == expected
    if operator == "!=":
        return actual != expected
    if operator == "<":
        return actual < expected
    if operator == ">":
        return actual > expected
    if operator == "<=":
        return actual <= expected
    if operator == ">=":
        return actual >= expected
    raise ValueError(f"不支持的比较操作符: {operator}")


# ---------------------------------------------------------------------------
# 触发条件抽象
# ---------------------------------------------------------------------------
class Trigger(ABC):
    """触发条件抽象：给定环境上下文，判断是否触发。"""

    @abstractmethod
    def evaluate(self, context: dict[str, Any]) -> bool:
        """根据 context 判断是否满足触发条件。"""


class FieldTrigger(Trigger):
    """
    通用字段触发：从 context 的某个命名空间取字段值，做比较。

    例：
        WeatherTrigger = FieldTrigger("weather", "rain", "==", True)
        TimeTrigger    = FieldTrigger("time", "hour", "==", 22)
        DeviceTrigger  = FieldTrigger("device", "motion", "==", True)
    """

    def __init__(self, namespace: str, field: str, operator: str, value: Any) -> None:
        self.namespace = namespace
        self.field = field
        self.operator = operator
        self.value = value

    def evaluate(self, context: dict[str, Any]) -> bool:
        ns = context.get(self.namespace, {})
        if not isinstance(ns, dict):
            return False
        actual = ns.get(self.field)
        if actual is None:
            return False
        return _compare(actual, self.operator, self.value)

    def __repr__(self) -> str:
        return f"{self.namespace}.{self.field} {self.operator} {self.value}"


# 便捷构造器
def weather(field: str, operator: str, value: Any) -> FieldTrigger:
    return FieldTrigger("weather", field, operator, value)


def time(field: str, operator: str, value: Any) -> FieldTrigger:
    return FieldTrigger("time", field, operator, value)


def device(field: str, operator: str, value: Any) -> FieldTrigger:
    return FieldTrigger("device", field, operator, value)


# ---------------------------------------------------------------------------
# 自动化规则
# ---------------------------------------------------------------------------
@dataclass
class AutomationRule:
    """一条自动化规则：触发条件 + 动作序列。"""
    name: str
    trigger: Trigger
    actions: list[SceneStep]
    description: str = ""


# ---------------------------------------------------------------------------
# 自动化引擎
# ---------------------------------------------------------------------------
class AutomationEngine:
    """
    自动化引擎：轮询检查规则，边沿触发（条件从 False 变 True 时执行一次）。

    用法：
        engine = AutomationEngine()
        engine.add_rule(AutomationRule("下雨关窗", weather("rain", "==", True),
                                        [SceneStep("curtain-01", "turn_off", {})]))
        # 每个轮询周期：
        fired = engine.tick(context, devices, hub)
    """

    def __init__(self) -> None:
        self.rules: list[AutomationRule] = []
        self._last_state: dict[str, bool] = {}

    def add_rule(self, rule: AutomationRule) -> None:
        self.rules.append(rule)

    def tick(
        self,
        context: dict[str, Any],
        devices: dict[str, dict[str, Any]],
        hub: Any,
    ) -> list[dict[str, Any]]:
        """
        检查所有规则，返回本轮触发的动作结果。

        边沿触发：只在条件从 False 变为 True 时执行，避免持续下雨时重复关窗。
        """
        fired_results: list[dict[str, Any]] = []

        for rule in self.rules:
            now = rule.trigger.evaluate(context)
            prev = self._last_state.get(rule.name, False)

            if now and not prev:
                # 边沿触发，执行动作序列
                for step in rule.actions:
                    device = devices.get(step.device_id)
                    if device is None:
                        fired_results.append({
                            "rule": rule.name,
                            "device_id": step.device_id,
                            "action": step.action,
                            "error": f"设备不存在: {step.device_id}",
                        })
                        continue

                    from devicemind.runtime import build_command
                    command = build_command(device, step.action, step.params)
                    state = hub.send_command(step.device_id, command)
                    fired_results.append({
                        "rule": rule.name,
                        "device_id": step.device_id,
                        "action": step.action,
                        "payload": command.payload,
                        "state": state,
                    })

            self._last_state[rule.name] = now

        return fired_results

    def reset(self) -> None:
        """重置触发状态（用于测试）。"""
        self._last_state.clear()
