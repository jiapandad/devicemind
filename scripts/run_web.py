#!/usr/bin/env python3
"""
启动 DeviceMind Web UI。

用法：
    python scripts/run_web.py [--port 5000]

环境变量：
    DEVICEMIND_LLM_PROVIDER  编译说明书用的 LLM 后端（openai / ollama）
    DEVICEMIND_LLM_MODEL     模型名（默认 qwen2.5:3b）
    DEVICEMIND_DATA          数据目录（默认 ~/.devicemind）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.webapp import app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="DeviceMind Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print("=" * 56)
    print("  DeviceMind · 设备世界的操作系统")
    print(f"  打开浏览器访问: http://{args.host}:{args.port}")
    print("  提示: 添加设备（读说明书）需要配置 LLM")
    print("=" * 56)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
