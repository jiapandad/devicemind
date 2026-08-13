"""
意图理解 (Intent)

把自然语言翻译成结构化意图：{device_id, action, params}。

两种模式：
1. LLM 模式（默认）：用 LLM 理解自然语言的歧义、上下文
2. 规则模式（fallback）：无 LLM 时的简单关键词匹配（用于离线测试）

这是"说人话就能控制"的关键。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from devicemind.llm import LLMClient, extract_json


@dataclass
class Intent:
    """结构化意图。"""
    device_id: str | None
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


INTENT_SYSTEM_PROMPT = """你是 DeviceMind 的意图理解器。把用户的自然语言指令翻译成结构化的设备操作。

规则：
1. 只输出一个合法的 JSON 对象，不要输出解释文字
2. JSON 格式：{"device_id": "...", "action": "...", "params": {...}}
3. device_id 必须从"可用设备列表"里选（如果用户没明确说哪个设备，选最匹配的那个，找不到则填 null）
4. action 必须从设备的可用动作里选
5. params 填入动作需要的参数（如亮度值、开关状态）
6. 理解模糊表达："调暗" = 降低亮度；"调到50%" = brightness=50；"打开" = power on
"""


class IntentParser:
    """意图解析器。"""

    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient.from_env()

    # ------------------------------------------------------------------
    def parse(self, text: str, devices: list[dict[str, Any]]) -> Intent:
        """
        解析用户意图。

        参数:
            text: 用户自然语言指令
            devices: 可用设备列表（每个含 id/name/type/actions）

        返回:
            Intent 对象
        """
        text = text.strip()
        if not text:
            raise ValueError("指令为空")

        # 先尝试 LLM
        try:
            return self._parse_with_llm(text, devices)
        except Exception:
            # LLM 不可用（未配置 key / 未装 Ollama），回退到规则
            return self._parse_with_rules(text, devices)

    # ------------------------------------------------------------------
    def _parse_with_llm(
        self, text: str, devices: list[dict[str, Any]]
    ) -> Intent:
        device_desc = _describe_devices(devices)
        user_prompt = f"""可用设备列表：
{device_desc}

用户指令：{text}

请输出 JSON（device_id / action / params）："""

        raw = self.client.chat(
            [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
        )
        data = extract_json(raw)

        device_id = data.get("device_id")
        action = data.get("action", "")
        params = data.get("params", {}) or {}

        if not action:
            raise ValueError("LLM 未解析出有效 action")

        return Intent(device_id=device_id, action=action, params=params, raw_text=text)

    # ------------------------------------------------------------------
    def _parse_with_rules(
        self, text: str, devices: list[dict[str, Any]]
    ) -> Intent:
        """
        规则 fallback：针对常见指令做关键词匹配。
        用于无 LLM 环境下的离线测试，能力有限但能跑通闭环。
        """
        target = _pick_device(text, devices)
        device_id = target.get("id") if target else None

        # 收集该设备的可用动作名
        actions = _collect_actions(target) if target else []

        # 亮度百分比
        m = re.search(r"(\d{1,3})\s*%", text)
        percent = int(m.group(1)) if m else None

        # 开关
        if _has_any(text, ["打开", "开灯", "启动", "on"]):
            return Intent(device_id, _first_match(actions, ["turn_on", "on", "power_on"]),
                          {"power": "on"}, text)
        if _has_any(text, ["关闭", "关灯", "停止", "off"]):
            return Intent(device_id, _first_match(actions, ["turn_off", "off", "power_off"]),
                          {"power": "off"}, text)

        # 亮度
        if percent is not None or _has_any(text, ["亮度", "调亮", "调暗", "变亮", "变暗"]):
            value = percent if percent is not None else 50
            if _has_any(text, ["调暗", "变暗"]):
                value = max(1, min(100, value - 20))
            elif _has_any(text, ["调亮", "变亮"]):
                value = max(1, min(100, value + 20))
            return Intent(device_id, _first_match(actions, ["set_brightness", "brightness", "dim"]),
                          {"brightness": value}, text)

        # 色温
        if _has_any(text, ["色温", "暖", "冷光", "白光", "暖光"]):
            return Intent(device_id, _first_match(actions, ["set_color_temp", "color_temp"]),
                          {}, text)

        # 颜色
        if _has_any(text, ["颜色", "红色", "蓝色", "绿色", "彩色"]):
            return Intent(device_id, _first_match(actions, ["set_color", "color"]),
                          {}, text)

        # 无法识别
        raise ValueError(f"无法识别的指令: {text}（可尝试：打开/关闭/调到50%）")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _describe_devices(devices: list[dict[str, Any]]) -> str:
    lines = []
    for d in devices:
        actions = _collect_actions(d)
        lines.append(f"- id={d.get('id')}, name={d.get('name')}, type={d.get('type')}, actions={actions}")
    return "\n".join(lines) if lines else "（无设备）"


def _collect_actions(device: dict[str, Any] | None) -> list[str]:
    if not device:
        return []
    result = []
    for cap in device.get("capabilities", []):
        for act in cap.get("actions", []):
            if isinstance(act, dict) and act.get("name"):
                result.append(act["name"])
    return result


def _pick_device(text: str, devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """根据指令里的关键词选设备。"""
    if not devices:
        return None
    if len(devices) == 1:
        return devices[0]
    for d in devices:
        name = d.get("name", "")
        if name and name in text:
            return d
    return devices[0]


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)


def _first_match(actions: list[str], preferred: list[str]) -> str:
    """从可用动作里找第一个匹配的（按 preferred 顺序）。"""
    norm = {_norm(a): a for a in actions}
    for p in preferred:
        np = _norm(p)
        for k, v in norm.items():
            if np in k or k in np:
                return v
    return actions[0] if actions else ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
