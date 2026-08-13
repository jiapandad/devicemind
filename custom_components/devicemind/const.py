"""DeviceMind Home Assistant 集成常量。

A2 模式：用户装一次本集成，之后每个设备只需把编译好的「设备协议 JSON」
放进配置目录，集成会自动扫描并把它们注册成 HA entity。
"""

DOMAIN = "devicemind"

# 设备协议 JSON 存放目录（相对于 HA 配置目录，如 config/devicemind/）
DEFAULT_DEVICES_DIR = "devicemind"

# devicemind 设备类型 -> HA 平台
TYPE_TO_PLATFORM = {
    "light": "light",
    "switch": "switch",
    "climate": "climate",
    "sensor": "sensor",
    "lock": "lock",
    "camera": "camera",
    "vacuum": "vacuum",
    "media": "media_player",
    "cover": "cover",
    "fan": "fan",
    "humidifier": "humidifier",
    "other": "switch",  # 兜底：无明确类型时按开关处理
}
