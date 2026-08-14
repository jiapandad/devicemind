"""测试 HA 集成各平台的状态回传映射（update_from_state）。

各平台文件 import 了大量 homeassistant 类，本测试用轻量 mock 替代，
聚焦验证「设备回传 payload → 实体状态」的映射逻辑是否正确。
"""

from __future__ import annotations

import enum
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# mock homeassistant（放在 import 平台模块之前）
# ---------------------------------------------------------------------------
ha = types.ModuleType("homeassistant")
ha_core = types.ModuleType("homeassistant.core")
ha_core.callback = lambda f: f


class FakeHass:
    def __init__(self):
        self.calls = []

    class services:
        @staticmethod
        async def async_call(domain, service, data):
            pass


ha_core.HomeAssistant = FakeHass

ha_const = types.ModuleType("homeassistant.const")


class UnitOfTemperature:
    CELSIUS = "°C"


ha_const.UnitOfTemperature = UnitOfTemperature
ha_const.STATE_OFF = "off"
ha_const.STATE_ON = "on"

HVACMode = enum.Enum(
    "HVACMode",
    {"OFF": "off", "COOL": "cool", "HEAT": "heat", "AUTO": "auto",
     "DRY": "dry", "FAN_ONLY": "fan_only", "HEAT_COOL": "heat_cool"},
)


class ClimateEntityFeature(enum.IntFlag):
    TARGET_TEMPERATURE = 1
    FAN_MODE = 2


class CoverEntityFeature(enum.IntFlag):
    OPEN = 1
    CLOSE = 2
    STOP = 4
    SET_POSITION = 8


class FanEntityFeature(enum.IntFlag):
    SET_SPEED = 1


class MediaPlayerEntityFeature(enum.IntFlag):
    TURN_ON = 1
    TURN_OFF = 2
    VOLUME_SET = 4
    VOLUME_STEP = 8


class VacuumEntityFeature(enum.IntFlag):
    START = 1
    STOP = 2
    PAUSE = 4
    RETURN_HOME = 8


class ColorMode:
    ONOFF = "onoff"
    BRIGHTNESS = "brightness"
    COLOR_TEMP = "color_temp"
    RGB = "rgb"


def _base_entity(name):
    return type(name, (), {})


components = types.ModuleType("homeassistant.components")

_platform_attrs = {
    "light": {"LightEntity": _base_entity("L"), "ColorMode": ColorMode},
    "switch": {"SwitchEntity": _base_entity("S")},
    "sensor": {"SensorEntity": _base_entity("S")},
    "climate": {"ClimateEntity": _base_entity("C"), "HVACMode": HVACMode},
    "lock": {"LockEntity": _base_entity("L")},
    "vacuum": {
        "VacuumEntity": _base_entity("V"),
        "VacuumEntityFeature": VacuumEntityFeature,
        "STATE_CLEANING": "cleaning",
        "STATE_DOCKED": "docked",
        "STATE_PAUSED": "paused",
    },
    "cover": {"CoverEntity": _base_entity("C"), "CoverEntityFeature": CoverEntityFeature},
    "fan": {"FanEntity": _base_entity("F"), "FanEntityFeature": FanEntityFeature},
    "humidifier": {"HumidifierEntity": _base_entity("H")},
    "media_player": {
        "MediaPlayerEntity": _base_entity("M"),
        "MediaPlayerEntityFeature": MediaPlayerEntityFeature,
    },
    "camera": {"Camera": _base_entity("C")},
}

for _modname, _attrs in _platform_attrs.items():
    _m = types.ModuleType("homeassistant.components." + _modname)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
    sys.modules["homeassistant.components." + _modname] = _m
    setattr(components, _modname, _m)

_climate_const = types.ModuleType("homeassistant.components.climate.const")
_climate_const.ClimateEntityFeature = ClimateEntityFeature
sys.modules["homeassistant.components.climate.const"] = _climate_const

ha_ce = types.ModuleType("homeassistant.config_entries")


class ConfigFlow:
    def __init_subclass__(cls, domain=None, **kw):
        super().__init_subclass__()
        cls.domain = domain


class ConfigEntry:
    pass


ha_ce.ConfigFlow = ConfigFlow
ha_ce.ConfigEntry = ConfigEntry

ha_helpers = types.ModuleType("homeassistant.helpers")
ha_discovery = types.ModuleType("homeassistant.helpers.discovery")


async def _alp(*a, **k):
    pass


ha_discovery.async_load_platform = _alp
ha_helpers.discovery = ha_discovery
ha_typing = types.ModuleType("homeassistant.helpers.typing")


class ConfigType:
    pass


ha_typing.ConfigType = ConfigType
ha_helpers.typing = ha_typing

vol = types.ModuleType("voluptuous")


class _Schema:
    def __init__(self, *a, **k):
        pass


class _Optional:
    def __init__(self, *a, **k):
        pass


vol.Schema = _Schema
vol.Optional = _Optional

sys.modules.update(
    {
        "homeassistant": ha,
        "homeassistant.core": ha_core,
        "homeassistant.const": ha_const,
        "homeassistant.components": components,
        "homeassistant.config_entries": ha_ce,
        "homeassistant.helpers": ha_helpers,
        "homeassistant.helpers.discovery": ha_discovery,
        "homeassistant.helpers.typing": ha_typing,
        "voluptuous": vol,
    }
)

# ---------------------------------------------------------------------------
# 加载平台模块（用独立包名 dm_ha 避免与 src 的 devicemind 包冲突）
# ---------------------------------------------------------------------------
import importlib.util  # noqa: E402

_COMPONENTS_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "devicemind"
)


def _load_module(pkg_name: str, filename: str):
    path = _COMPONENTS_DIR / filename
    spec = importlib.util.spec_from_file_location(pkg_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = mod
    spec.loader.exec_module(mod)
    return mod


_pkg = types.ModuleType("dm_ha")
_pkg.__path__ = [str(_COMPONENTS_DIR)]
sys.modules["dm_ha"] = _pkg

_load_module("dm_ha.const", "const.py")
_load_module("dm_ha.runtime", "runtime.py")
_load_module("dm_ha.mapping", "mapping.py")
_load_module("dm_ha.base", "base.py")

climate = _load_module("dm_ha.climate", "climate.py")
cover = _load_module("dm_ha.cover", "cover.py")
light = _load_module("dm_ha.light", "light.py")
lock = _load_module("dm_ha.lock", "lock.py")
sensor = _load_module("dm_ha.sensor", "sensor.py")
switch = _load_module("dm_ha.switch", "switch.py")

_hass = FakeHass()


# ---------------------------------------------------------------------------
# 状态回传映射测试
# ---------------------------------------------------------------------------
def _device(type_: str, capabilities: list, extra_control: dict | None = None) -> dict:
    control = {"protocol": "mqtt", "commands": {}}
    if extra_control:
        control.update(extra_control)
    return {
        "id": f"{type_}-01",
        "type": type_,
        "name": "测试设备",
        "capabilities": capabilities,
        "control": control,
    }


def test_switch_power_state():
    dev = _device(
        "switch",
        [{"name": "power", "properties": {}, "actions": []}],
    )
    e = switch.DeviceMindSwitch(_hass, dev)
    e.update_from_state({"power": "on"})
    assert e.is_on is True


def test_light_brightness_state():
    dev = _device(
        "light",
        [
            {"name": "power", "properties": {}, "actions": []},
            {
                "name": "brightness",
                "properties": {"brightness": {"min": 1, "max": 100}},
                "actions": [],
            },
        ],
    )
    e = light.DeviceMindLight(_hass, dev)
    e.update_from_state({"power": "on", "brightness": 81})
    assert e.is_on is True
    assert e._attr_brightness == 207  # 81/100*255 = 206.55 -> 207


def test_sensor_value_state():
    dev = _device(
        "sensor",
        [{"name": "temperature", "properties": {}, "actions": []}],
        extra_control={"state_map": {"temp": "temperature"}},
    )
    e = sensor.DeviceMindSensor(_hass, dev)
    e.update_from_state({"temp": 25.5})
    assert e.native_value == 25.5


def test_climate_temperature_state():
    dev = _device(
        "climate",
        [
            {"name": "power", "properties": {}, "actions": []},
            {
                "name": "temperature",
                "properties": {"temperature": {"min": 16, "max": 30}},
                "actions": [],
            },
        ],
    )
    e = climate.DeviceMindClimate(_hass, dev)
    e.update_from_state({"temperature": 26})
    assert e.current_temperature == 26


def test_lock_state():
    dev = _device(
        "lock",
        [{"name": "power", "properties": {}, "actions": []}],
    )
    e = lock.DeviceMindLock(_hass, dev)
    e.update_from_state({"lock_state": "locked"})
    assert e.is_locked is True


def test_cover_position_state():
    dev = _device(
        "cover",
        [{"name": "position", "properties": {}, "actions": []}],
    )
    e = cover.DeviceMindCover(_hass, dev)
    e.update_from_state({"position": 0})
    assert e.is_closed is True
