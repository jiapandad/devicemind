"""DeviceMind Home Assistant 集成入口。

职责：扫描配置目录下的「设备协议 JSON」，按设备类型分发到对应平台，
把每个设备注册成一个 HA entity。

设备协议 JSON 由 devicemind 编译器（src/devicemind/compiler.py）生成，
结构见 src/devicemind/schema.py 的 DEVICE_SCHEMA。

A2 模式：用户装一次本集成，之后每个设备只需把编译好的 JSON 放进
config/devicemind/ 目录（或 UI 里配置的自定义目录），重启或重载集成后
自动成为 HA 设备。

支持两种配置方式：
- config flow（推荐）：UI 里「添加集成」配置设备目录
- YAML（兼容）：在 configuration.yaml 里写 devicemind: {devices_dir: devicemind}
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_DEVICES_DIR, DOMAIN, TYPE_TO_PLATFORM

_LOGGER = logging.getLogger(__name__)

# 当前已实现的平台
SUPPORTED_PLATFORMS = {
    "light",
    "switch",
    "sensor",
    "climate",
    "lock",
    "camera",
    "vacuum",
    "media_player",
    "cover",
    "fan",
    "humidifier",
}


def _resolve_devices_dir(config_dir: str, devices_dir: str) -> str:
    """把设备目录解析为绝对路径（相对路径基于 HA 配置目录）。"""
    if os.path.isabs(devices_dir):
        return devices_dir
    return os.path.join(config_dir, devices_dir)


def _load_devices(config_dir: str, devices_dir: str) -> dict[str, list[dict[str, Any]]]:
    """扫描设备目录，返回 {platform: [device_json, ...]}。"""
    devices_path = _resolve_devices_dir(config_dir, devices_dir)
    by_platform: dict[str, list[dict[str, Any]]] = {}

    if not os.path.isdir(devices_path):
        _LOGGER.info("设备目录不存在，跳过扫描: %s", devices_path)
        return by_platform

    for filename in sorted(os.listdir(devices_path)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(devices_path, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                device = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            _LOGGER.warning("读取设备文件失败 %s: %s", filename, exc)
            continue

        platform = TYPE_TO_PLATFORM.get(device.get("type"), "switch")
        by_platform.setdefault(platform, []).append(device)

    return by_platform


async def _setup_devices(hass: HomeAssistant, devices_dir: str) -> None:
    """扫描设备 JSON，按平台分发加载 entity。"""
    devices_by_platform = _load_devices(hass.config.config_dir, devices_dir)
    hass.data.setdefault(DOMAIN, {})["devices"] = devices_by_platform

    for platform in sorted(devices_by_platform):
        if platform not in SUPPORTED_PLATFORMS:
            _LOGGER.warning("暂未实现的平台类型: %s，相关设备将被跳过", platform)
            continue
        await discovery.async_load_platform(hass, platform, DOMAIN, None, {})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """YAML 配置入口（兼容旧方式）。

    注意：config entry 模式下 HA 也会用空配置调用本函数做 domain 初始化，
    此时不做任何事，实际扫描由 async_setup_entry 完成，避免设备重复加载。
    """
    if DOMAIN not in config:
        return True
    devices_dir = config[DOMAIN].get("devices_dir", DEFAULT_DEVICES_DIR)
    await _setup_devices(hass, devices_dir)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config flow 配置入口（推荐）。"""
    devices_dir = entry.data.get("devices_dir", DEFAULT_DEVICES_DIR)
    await _setup_devices(hass, devices_dir)
    return True
