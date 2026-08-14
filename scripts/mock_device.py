#!/usr/bin/env python3
"""模拟一台 MQTT 设备：订阅控制指令，收到后回传状态。

用于在没有真实设备时端到端验证 DeviceMind 集成的「控制 → 状态回传」闭环。

用法：
    pip install paho-mqtt
    python scripts/mock_device.py \
        --control-topic smarthome/lamp01/set \
        --state-topic smarthome/lamp01/state \
        --initial '{"power":"off","brightness":50}'

收到 HA 发来的指令（如 {"power":"on"}）后，脚本把指令字段合并进状态，
并回传到 state-topic，模拟真实设备的行为。
"""

from __future__ import annotations

import argparse
import json

import paho.mqtt.client as mqtt


def main() -> None:
    parser = argparse.ArgumentParser(description="模拟一台 MQTT 设备")
    parser.add_argument("--broker", default="localhost", help="MQTT broker 地址")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--control-topic", required=True, help="设备接收指令的主题")
    parser.add_argument("--state-topic", required=True, help="设备回传状态的主题")
    parser.add_argument("--initial", default='{"power":"off"}', help="初始状态 JSON")
    args = parser.parse_args()

    state = json.loads(args.initial)

    def on_connect(client, _userdata, _flags, rc) -> None:
        if rc != 0:
            print(f"[错误] 连接失败，返回码 {rc}")
            return
        print(f"[已连接] {args.broker}:{args.port}")
        client.subscribe(args.control_topic)
        print(f"[已订阅] 控制主题 {args.control_topic}")

    def on_message(client, _userdata, msg) -> None:
        raw = msg.payload.decode("utf-8", errors="ignore")
        print(f"[收到指令] {msg.topic}: {raw}")
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError:
            cmd = {}
        if isinstance(cmd, dict):
            state.update(cmd)
        client.publish(args.state_topic, json.dumps(state, ensure_ascii=False))
        print(f"[回传状态] {args.state_topic}: {json.dumps(state, ensure_ascii=False)}")

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port, 60)
    print(f"[模拟设备] 控制={args.control_topic}  状态={args.state_topic}")
    print("按 Ctrl+C 退出")
    client.loop_forever()


if __name__ == "__main__":
    main()
