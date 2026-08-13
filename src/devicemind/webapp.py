"""
DeviceMind Web UI（方向 A：HA 设备接入增强层）

定位：把设备说明书编译成设备协议 JSON，供 Home Assistant 集成使用。

不再包含设备控制、场景、自动化等能力（这些 HA 已经做得更好），
只保留"贴说明书 → 编译 → 导出设备协议 JSON"这一条核心链路。

启动：
    python scripts/run_web.py
    # 或
    python -m devicemind.webapp

API 一览：
    POST /api/compile             说明书文本 -> 编译成设备协议 JSON（并缓存）
    GET  /api/devices             列出已编译的设备
    GET  /api/devices/<id>        获取单个设备协议 JSON
    DELETE /api/devices/<id>      删除某个设备的编译缓存
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from devicemind.compiler import DeviceCompiler, delete_cached, list_cached, load_cached

# 前端静态文件目录（devicemind/web/）
WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

# 可选鉴权：设置环境变量 DEVICEMIND_API_TOKEN 后，所有 /api/* 请求需携带该 token。
API_TOKEN = os.getenv("DEVICEMIND_API_TOKEN", "").strip()

logger = logging.getLogger("devicemind")

# 编译器单例（compile 内部带缓存，重复编译相同说明书不重复调 LLM）
compiler = DeviceCompiler()


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # ---- 可选 token 鉴权（仅保护 /api/*）----
    @app.before_request
    def _auth():
        if not API_TOKEN or not request.path.startswith("/api/"):
            return None
        token = request.headers.get("X-API-Token", "")
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
        if token != API_TOKEN:
            return jsonify({"ok": False, "error": "未授权：缺少或错误的 API Token"}), 401
        return None

    # ---- 前端页面 ----
    @app.route("/")
    def index():
        return send_from_directory(str(WEB_DIR), "index.html")

    @app.route("/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(str(WEB_DIR), filename)

    # ---- 编译 ----
    @app.route("/api/compile", methods=["POST"])
    def api_compile():
        """说明书文本 -> 设备协议 JSON（预览，不写入缓存）。"""
        body = request.get_json(silent=True) or {}
        manual_text = body.get("manual") or ""
        device_id = body.get("device_id") or ""
        name_hint = body.get("name_hint")

        if not manual_text.strip():
            return jsonify({"ok": False, "error": "说明书内容为空"}), 400

        try:
            device = compiler.compile(
                manual_text,
                device_id or f"device-{uuid.uuid4().hex[:8]}",
                name_hint,
                use_cache=False,  # 预览不落缓存，确认后再保存
            )
            return jsonify({"ok": True, "data": device})
        except Exception as exc:  # noqa: BLE001
            logger.warning("说明书编译失败: %s", exc)
            return jsonify({"ok": False, "error": f"编译失败：{exc}"}), 500

    @app.route("/api/devices", methods=["POST"])
    def api_add_device():
        """编译说明书并保存到缓存（body: {manual, device_id?, name_hint?}）。"""
        body = request.get_json(silent=True) or {}
        manual_text = body.get("manual") or ""
        device_id = body.get("device_id") or f"device-{uuid.uuid4().hex[:8]}"
        name_hint = body.get("name_hint")

        if not manual_text.strip():
            return jsonify({"ok": False, "error": "说明书内容为空"}), 400

        try:
            device = compiler.compile(manual_text, device_id, name_hint)
            return jsonify({
                "ok": True,
                "data": device,
                "message": f"设备 {device.get('name', device_id)} 已编译并缓存",
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("添加设备编译失败 device_id=%s: %s", device_id, exc)
            return jsonify({"ok": False, "error": f"编译失败：{exc}"}), 500

    # ---- 已编译设备 ----
    @app.route("/api/devices", methods=["GET"])
    def api_devices():
        return jsonify({"ok": True, "data": list_cached()})

    @app.route("/api/devices/<device_id>", methods=["GET"])
    def api_get_device(device_id: str):
        device = load_cached(device_id)
        if device is None:
            return jsonify({"ok": False, "error": f"设备不存在: {device_id}"}), 404
        return jsonify({"ok": True, "data": device})

    @app.route("/api/devices/<device_id>", methods=["DELETE"])
    def api_delete_device(device_id: str):
        if not delete_cached(device_id):
            return jsonify({"ok": False, "error": f"设备不存在: {device_id}"}), 404
        logger.info("设备编译缓存已删除: %s", device_id)
        return jsonify({"ok": True, "message": f"设备 {device_id} 已删除"})

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("DeviceMind 编译工具已启动，请打开 http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
