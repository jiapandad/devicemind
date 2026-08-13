"""
编译期核心 (Compiler)

把设备说明书"编译"成结构化设备描述 JSON。

流程：
  设备说明书 ──▶ LLM 理解 ──▶ 设备 JSON ──▶ 校验 ──▶ 缓存
                                          │
                                          └─ 失败则重试

这是 DeviceMind 的"冷启动"关键：任何设备，只要丢进说明书，就能被系统理解。
"""

from __future__ import annotations

import json
import os
from typing import Any

from devicemind.llm import LLMClient, extract_json
from devicemind.schema import DEVICE_TYPES, dump_schema_prompt, dump_example_prompt, validate_device


SYSTEM_PROMPT = """你是 DeviceMind 的设备编译器。你的任务是把设备说明书转换为结构化的设备描述 JSON。

规则：
1. 只输出一个合法的 JSON 对象，不要输出任何解释文字
2. 严格遵守给定的 JSON Schema
3. 从说明书中提取：设备类型(type)、能力(capabilities)、如何发指令(control)
4. 【关键】逐条对照说明书的"功能说明"，每一条功能都要对应一个 capability，不得遗漏（尤其注意颜色、色温、亮度、电量/电池 battery 等易漏项）
5. 能力要拆解成原子单元。例如"可调亮度+可调色温+可变颜色" -> power + brightness + color_temp + color
6. 动作(action)命名必须用标准动词（见 Schema 的 enum）：turn_on / turn_off / set_brightness / set_color / set_color_temp / set_temperature / set_mode / get_state / get_battery
7. control.commands 必须是 {动作名: {topic, payload}} 结构化对象。payload 是 JSON 对象，参数值用字符串占位符如 "{brightness}"。禁止把 topic 和 payload 拼成一个字符串
8. 如果说明书没提到控制协议，control.protocol 填 "unknown"，commands 填 {}
9. 不要编造说明书里没有的功能
10. 只读型设备（如传感器）可以没有 actions，用 properties 描述可读数据即可
"""


class DeviceCompiler:
    """把说明书编译成设备 JSON。"""

    def __init__(self, client: LLMClient | None = None, max_retries: int = 3) -> None:
        self.client = client or LLMClient.from_env()
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    def compile(
        self,
        manual_text: str,
        device_id: str,
        name_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        将说明书文本编译为设备描述 JSON。

        参数:
            manual_text: 说明书全文（文本形式，PDF 需先转文本）
            device_id: 设备唯一标识
            name_hint: 可选，设备名提示（帮助 LLM 定位）

        返回:
            设备描述 dict
        """
        if not manual_text or not manual_text.strip():
            raise ValueError("说明书内容为空")

        user_prompt = self._build_prompt(manual_text, device_id, name_hint)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self.client.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    json_mode=True,
                )
                device = extract_json(raw)

                errors = validate_device(device)
                if errors:
                    raise ValueError("; ".join(errors))

                # 保证 id 正确
                device["id"] = device_id
                return device

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < self.max_retries:
                    continue

        raise RuntimeError(
            f"编译失败（重试 {self.max_retries} 次）: {last_error}"
        )

    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        manual_text: str,
        device_id: str,
        name_hint: str | None,
    ) -> str:
        schema = dump_schema_prompt()
        example = dump_example_prompt()
        hint = f"\n设备名称提示：{name_hint}" if name_hint else ""
        return f"""请将下面的设备说明书编译成设备描述 JSON。

设备 ID：{device_id}
{hint}

参考示例（输出格式必须和它完全一致）：
{example}

JSON Schema（必须严格遵守）：
{schema}

设备说明书全文：
--- 开始 ---
{manual_text.strip()}
--- 结束 ---

请输出 JSON："""


# ---------------------------------------------------------------------------
# 缓存：编译结果落盘，避免重复编译
# ---------------------------------------------------------------------------
def cache_dir() -> str:
    base = os.getenv("DEVICEMIND_CACHE", os.path.join(os.getcwd(), ".devicemind_cache"))
    os.makedirs(base, exist_ok=True)
    return base


def load_cached(device_id: str) -> dict[str, Any] | None:
    path = os.path.join(cache_dir(), f"{device_id}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(device_id: str, device: dict[str, Any]) -> None:
    path = os.path.join(cache_dir(), f"{device_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(device, f, ensure_ascii=False, indent=2)
