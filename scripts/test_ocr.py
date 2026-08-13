#!/usr/bin/env python3
"""验证扫描版 PDF 的 OCR 读取：生成图片型 PDF → OCR 识别 → 提取文本。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def find_cjk_font() -> str:
    for p in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"]:
        if Path(p).exists():
            return p
    return "C:/Windows/Fonts/arial.ttf"


def make_scanned_pdf(out: str) -> None:
    """生成一张中文说明书图片，再包成 PDF（模拟扫描件：图片型、无文字层）。"""
    import fitz  # pymupdf

    # 1. 用 PIL 画一张说明书图片
    img = Image.new("RGB", (1200, 600), "white")
    draw = ImageDraw.Draw(img)
    font_path = find_cjk_font()
    title_font = ImageFont.truetype(font_path, 40)
    body_font = ImageFont.truetype(font_path, 28)

    draw.text((60, 50), "智能空气净化器使用说明书", fill="black", font=title_font)
    lines = [
        "【功能说明】",
        "1. 开关控制：可通过 App 开启或关闭净化器",
        "2. 风速调节：支持低速、中速、高速三档",
        "3. 模式切换：支持自动、睡眠、手动三种模式",
        "4. 滤网寿命查询：可查询滤网剩余寿命",
        "【控制协议】MQTT topic: home/purifier/set",
    ]
    y = 130
    for line in lines:
        draw.text((60, y), line, fill="black", font=body_font)
        y += 45
    img.save("examples/_scanned_page.png")

    # 2. 用 pymupdf 把图片包成 PDF（无文字层，模拟扫描件）
    doc = fitz.open()
    page = doc.new_page(width=1200, height=600)
    page.insert_image(fitz.Rect(0, 0, 1200, 600), filename="examples/_scanned_page.png")
    doc.save(out)
    doc.close()
    print(f"已生成扫描版 PDF: {out}")


def main() -> int:
    out = "examples/sample_purifier_scanned.pdf"
    make_scanned_pdf(out)

    # 用 ocr 模块提取
    from devicemind.ocr import extract_pdf_text, is_scanned_pdf

    print(f"是否为扫描版: {is_scanned_pdf(out)}")
    print("=== OCR 提取的文本 ===")
    text = extract_pdf_text(out)
    print(text)
    print("=" * 30)

    checks = ["净化器", "开关", "风速", "模式", "滤网", "MQTT"]
    ok = all(k in text for k in checks)
    print(f"关键内容识别: {'成功' if ok else '部分缺失'}")
    for k in checks:
        print(f"  {'✓' if k in text else '✗'} {k}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
