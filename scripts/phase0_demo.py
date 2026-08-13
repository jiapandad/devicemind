#!/usr/bin/env python3
"""
Phase 0 验证脚本

验证核心假设：LLM 能否读懂设备说明书，并生成可执行的结构化 JSON。

用法：
    # 用示例说明书
    python scripts/phase0_demo.py examples/sample_light.txt --id lamp-01

    # 用你自己的说明书文件
    python scripts/phase0_demo.py path/to/manual.txt --id my-device --name "格力空调"

环境变量：
    DEVICEMIND_LLM_PROVIDER  openai / ollama（默认自动探测）
    OPENAI_API_KEY            OpenAI 兼容 API 的 Key
    DEEPSEEK_API_KEY          DeepSeek 的 Key（推荐，便宜）
    DEVICEMIND_LLM_MODEL      指定模型名
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本能直接 import src 下的包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devicemind.compiler import DeviceCompiler, load_cached, save_cache  # noqa: E402
from devicemind.llm import LLMClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="DeviceMind Phase 0 验证脚本")
    parser.add_argument("manual", help="设备说明书文件路径（txt 或 pdf）")
    parser.add_argument("--id", required=True, help="设备唯一标识")
    parser.add_argument("--name", default=None, help="设备名称提示")
    parser.add_argument("--no-cache", action="store_true", help="忽略缓存，强制重新编译")
    args = parser.parse_args()

    # 读取说明书
    manual_path = Path(args.manual)
    if not manual_path.exists():
        print(f"[错误] 说明书文件不存在: {manual_path}")
        return 1

    manual_text = read_manual(manual_path)
    print(f"[信息] 说明书长度: {len(manual_text)} 字符")

    # 尝试读缓存
    if not args.no_cache:
        cached = load_cached(args.id)
        if cached:
            print("[信息] 命中缓存，直接返回")
            print(json_pretty(cached))
            return 0

    # 编译
    print("[信息] 调用 LLM 编译（首次可能较慢）...")
    client = LLMClient.from_env()
    print(f"[信息] 后端: {client.provider}, 模型: {client.model}")

    compiler = DeviceCompiler(client)
    try:
        device = compiler.compile(manual_text, args.id, args.name)
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 编译出错: {exc}")
        return 1

    # 缓存
    save_cache(args.id, device)
    print("[成功] 编译完成，已缓存\n")
    print(json_pretty(device))
    return 0


def read_manual(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf(path: Path) -> str:
    """从 PDF 提取文本，自动判断文本型/扫描型（扫描型走 OCR）。"""
    try:
        from devicemind.ocr import extract_pdf_text
    except ImportError as exc:
        print("[提示] 缺少 OCR 依赖。请先: pip install rapidocr-onnxruntime pymupdf")
        raise SystemExit(1) from exc
    return extract_pdf_text(str(path))


def json_pretty(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
