"""
LLM 后端封装

支持两种后端：
1. OpenAI 兼容 API（OpenAI / DeepSeek / Moonshot / 本地 vLLM 等，均兼容 /v1/chat/completions）
2. Ollama 本地推理（隐私优先）

用法：
    from devicemind.llm import LLMClient

    client = LLMClient.from_env()   # 从环境变量自动配置
    resp = client.chat([{"role": "user", "content": "你好"}], json_mode=True)
"""

from __future__ import annotations

import json
import os
from typing import Any


class LLMError(Exception):
    """LLM 调用失败。"""


class LLMClient:
    """统一的 LLM 客户端，屏蔽不同后端的差异。"""

    def __init__(
        self,
        provider: str = "openai",
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
    ) -> None:
        self.provider = provider  # "openai" 或 "ollama"
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.temperature = temperature

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "LLMClient":
        """
        从环境变量自动配置，优先级：
        1. 显式设置了 DEVICEMIND_LLM_PROVIDER
        2. 有 OPENAI_API_KEY -> openai
        3. 有 DEEPSEEK_API_KEY -> openai 兼容 (deepseek)
        4. 否则默认 ollama 本地
        """
        provider = os.getenv("DEVICEMIND_LLM_PROVIDER", "").lower()

        if provider == "ollama":
            return cls(
                provider="ollama",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                model=os.getenv("DEVICEMIND_LLM_MODEL", "qwen2.5:3b"),
            )

        if provider == "openai":
            return cls(
                provider="openai",
                base_url=os.getenv("OPENAI_BASE_URL"),
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DEVICEMIND_LLM_MODEL", "gpt-4o-mini"),
            )

        # 自动探测
        if os.getenv("DEEPSEEK_API_KEY"):
            return cls(
                provider="openai",
                base_url="https://api.deepseek.com",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                model=os.getenv("DEVICEMIND_LLM_MODEL", "deepseek-chat"),
            )
        if os.getenv("OPENAI_API_KEY"):
            return cls(
                provider="openai",
                base_url=os.getenv("OPENAI_BASE_URL"),
                api_key=os.getenv("OPENAI_API_KEY"),
                model=os.getenv("DEVICEMIND_LLM_MODEL", "gpt-4o-mini"),
            )

        # 默认走本地 Ollama
        return cls(
            provider="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("DEVICEMIND_LLM_MODEL", "qwen2.5:7b"),
        )

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        max_tokens: int = 2048,
    ) -> str:
        """发送对话请求，返回文本内容。json_mode=True 时返回 JSON 字符串。"""
        if self.provider == "ollama":
            return self._chat_ollama(messages, json_mode)
        return self._chat_openai(messages, json_mode, max_tokens)

    # ------------------------------------------------------------------
    def _chat_openai(self, messages, json_mode: bool, max_tokens: int) -> str:
        if self.api_key is None:
            raise LLMError(
                "未配置 API Key。请设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量，"
                "或安装 Ollama 后使用本地推理。"
            )

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "缺少 openai 库，请先安装: pip install openai"
            ) from exc

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"OpenAI 兼容接口调用失败: {exc}") from exc

    # ------------------------------------------------------------------
    def _chat_ollama(self, messages, json_mode: bool) -> str:
        try:
            import requests
        except ImportError as exc:  # pragma: no cover
            raise LLMError("缺少 requests 库，请先安装: pip install requests") from exc

        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json" if json_mode else None,
            "options": {"temperature": self.temperature},
        }

        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except Exception as exc:  # noqa: BLE001
            raise LLMError(
                f"Ollama 调用失败: {exc}。请确认 Ollama 已启动且模型 {self.model} 已安装。"
            ) from exc


# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中稳健地提取 JSON 对象（容忍 ```json 包裹、前后杂讯）。"""
    text = text.strip()

    # 去掉 markdown 代码块包裹
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取第一个 { ... } 块
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise LLMError("无法从 LLM 输出中解析出合法 JSON")
