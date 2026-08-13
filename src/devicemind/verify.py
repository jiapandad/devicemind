"""
编译试运行验证闭环 (Verify)

LLM 编译出的设备 JSON，通过"试运行"验证是否正确：

  编译 → 发一条试探指令 → 设备有响应？→ 无响应则反馈错误、纠错重编译

这是让系统从"会编译"进化到"编译得对"的关键闭环。
真实设备上，发错 topic 设备不会响应；虚拟设备用 expected_topic 模拟同样的行为。
"""

from __future__ import annotations

from typing import Any

from devicemind.compiler import DeviceCompiler
from devicemind.runtime import build_command


def collect_actions(device: dict[str, Any]) -> list[str]:
    """收集设备声明的所有动作名。"""
    result = []
    for cap in device.get("capabilities", []):
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                result.append(act["name"])
    return result


def pick_verify_action(device: dict[str, Any]) -> str | None:
    """
    选一个用于试运行的动作。

    优先选"只读/安全"的动作（get_state），其次 turn_on/turn_off，
    最后退回第一个动作。试运行应避免破坏性操作。
    """
    actions = collect_actions(device)
    if not actions:
        return None
    norm = {a.lower(): a for a in actions}
    for preferred in ["get_state", "get_battery", "turn_on", "turn_off"]:
        for key, val in norm.items():
            if preferred in key or key in preferred:
                return val
    return actions[0]


def verify_device(
    device: dict[str, Any],
    hub: Any,
    device_id: str,
) -> tuple[bool, str]:
    """
    试运行验证：发一条试探指令，检查设备是否响应。

    返回:
        (是否通过, 错误信息)
    """
    action = pick_verify_action(device)
    if action is None:
        return True, ""  # 设备无动作，跳过验证

    command = build_command(device, action, {})
    if hub.probe(device_id, command):
        return True, ""

    return False, (
        f"指令 topic={command.topic} 未命中设备预期，"
        f"说明 control.commands 的 topic 编译错误，请重新核对说明书的控制协议部分"
    )


class CompileVerifyLoop:
    """编译 + 试运行验证 + 失败纠错重编译的闭环。"""

    def __init__(self, compiler: DeviceCompiler | None = None, max_attempts: int = 3) -> None:
        self.compiler = compiler or DeviceCompiler()
        self.max_attempts = max_attempts

    def compile_and_verify(
        self,
        manual_text: str,
        device_id: str,
        hub: Any,
        name_hint: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        """
        编译并试运行验证，失败时把错误反馈给 LLM 纠错重编译。

        返回:
            (设备 JSON, 尝试次数)
        """
        last_feedback: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            device = self.compiler.compile(
                manual_text, device_id, name_hint, feedback=last_feedback
            )
            ok, err = verify_device(device, hub, device_id)
            if ok:
                return device, attempt
            last_feedback = err

        raise RuntimeError(
            f"编译验证失败（重试 {self.max_attempts} 次仍无法通过试运行）: {last_feedback}"
        )
