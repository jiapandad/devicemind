"""
OCR 支持（扫描版 PDF）

厂商说明书 PDF 分两种：
1. 文本型：Word/排版软件导出，文字可选中 —— pypdf 直接提取
2. 扫描型：纸质扫描成图片 —— 需要 OCR 识别

本模块自动判断：pypdf 提取为空时，回退到 OCR（pymupdf 转图 + RapidOCR 识别）。

RapidOCR 基于 onnxruntime，用的是 PaddleOCR 同款模型，但无需 paddlepaddle 框架，
轻量、CPU 即可、中文效果好。
"""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(pdf_path: str | Path) -> str:
    """
    从 PDF 提取文本，自动判断文本型/扫描型。

    返回:
        提取出的文本（文本型直接用 pypdf，扫描型走 OCR）
    """
    pdf_path = str(pdf_path)

    # 1. 先尝试 pypdf 直接提取（文本型 PDF）
    text = _extract_with_pypdf(pdf_path)
    if text.strip():
        return text

    # 2. 无文本 → 扫描型，回退到 OCR
    return _extract_with_ocr(pdf_path)


def _extract_with_pypdf(pdf_path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_with_ocr(pdf_path: str) -> str:
    import fitz  # pymupdf
    from rapidocr_onnxruntime import RapidOCR

    ocr = RapidOCR()
    doc = fitz.open(pdf_path)
    page_texts: list[str] = []

    for page in doc:
        # PDF 页转图片（200 dpi 平衡清晰度与速度）
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")

        # OCR 识别（RapidOCR 接受 bytes/numpy/path）
        result, _ = ocr(img_bytes)
        if result:
            # result 是 [[box, text, score], ...]
            page_texts.append("\n".join(line[1] for line in result))

    doc.close()
    return "\n".join(page_texts)


def is_scanned_pdf(pdf_path: str | Path) -> bool:
    """判断 PDF 是否为扫描版（pypdf 提取不到文本）。"""
    return not _extract_with_pypdf(str(pdf_path)).strip()
