"""DeviceMind 的 UI 配置流（Config Flow）。

让用户在「设置 → 设备与服务 → 添加集成 → DeviceMind」里配置
「设备协议 JSON 目录」路径，之后集成会扫描该目录并注册设备。
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries

from .const import DEFAULT_DEVICES_DIR, DOMAIN


class DeviceMindConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """处理 DeviceMind 的配置流。"""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """用户从 UI 添加集成时进入的第一步。"""
        if user_input is not None:
            return self.async_create_entry(
                title="DeviceMind",
                data={"devices_dir": user_input.get("devices_dir", DEFAULT_DEVICES_DIR)},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "devices_dir", default=DEFAULT_DEVICES_DIR
                    ): str,
                }
            ),
            description_placeholders={
                "default_dir": DEFAULT_DEVICES_DIR,
            },
        )
