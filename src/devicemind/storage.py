"""
持久化存储 (Storage)

设备状态、场景配置落盘到 JSON 文件，重启不丢。

默认数据目录 ~/.devicemind，可用环境变量 DEVICEMIND_DATA 覆盖。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    """返回数据目录（自动创建）。"""
    base = os.getenv("DEVICEMIND_DATA", str(Path.home() / ".devicemind"))
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(name: str, data: Any) -> None:
    """保存 JSON 数据到数据目录。"""
    path = data_dir() / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(name: str, default: Any = None) -> Any:
    """从数据目录加载 JSON 数据，不存在则返回 default。"""
    path = data_dir() / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


# ---------------------------------------------------------------------------
# 设备状态
# ---------------------------------------------------------------------------
def save_states(states: dict[str, dict[str, Any]]) -> None:
    """保存设备状态 {device_id: {属性: 值}}。"""
    save_json("states.json", states)


def load_states() -> dict[str, dict[str, Any]]:
    """加载设备状态，无则返回空 dict。"""
    return load_json("states.json", {})


# ---------------------------------------------------------------------------
# 场景配置
# ---------------------------------------------------------------------------
def save_scenes(scenes: dict[str, Any]) -> None:
    """保存场景配置（scene.to_dict 的结果）。"""
    save_json("scenes.json", scenes)


def load_scenes() -> dict[str, Any]:
    """加载场景配置，无则返回空 dict。"""
    return load_json("scenes.json", {})
