#!/usr/bin/env python3
"""验证 PDF 说明书的读取能力：生成中文 PDF → pypdf 提取文本 → 检查。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent


def find_cjk_font() -> str | None:
    """在 Windows 字体目录里找一个中文字体。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑
        "C:/Windows/Fonts/simhei.ttf",   # 黑体
        "C:/Windows/Fonts/simsun.ttc",   # 宋体
        "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑粗体
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def main() -> int:
    font_path = find_cjk_font()
    print(f"中文字体: {font_path or '未找到，用默认字体'}")

    out = str(ROOT / "examples" / "test_manual.pdf")

    # 生成中文 PDF
    c = canvas.Canvas(out)
    if font_path:
        pdfmetrics.registerFont(TTFont("CJK", font_path))
        font_name = "CJK"
    else:
        font_name = "Helvetica"

    c.setFont(font_name, 12)
    lines = [
        "智能台灯使用说明书",
        "",
        "【产品概述】支持亮度调节和色温调节。",
        "【功能说明】",
        "1. 开关控制",
        "2. 亮度调节（1%-100%）",
        "3. 色温调节（2700K-6500K）",
        "【控制协议】MQTT topic: smarthome/lamp/set",
    ]
    y = 800
    for line in lines:
        c.drawString(50, y, line)
        y -= 25
    c.save()
    print(f"已生成测试 PDF: {out}")

    # 用 pypdf 读取（这正是 phase0_demo.py 的 read_pdf 逻辑）
    reader = PdfReader(out)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    print("\n=== pypdf 提取的文本 ===")
    print(extracted)
    print("=" * 30)

    # 简单验证：关键内容是否提取出来
    checks = ["智能台灯", "亮度调节", "色温", "MQTT", "smarthome"]
    ok = all(k in extracted for k in checks)
    print(f"关键内容提取: {'成功' if ok else '部分缺失'}")
    for k in checks:
        print(f"  {'✓' if k in extracted else '✗'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
