# DeviceMind

> 贴一份设备说明书，生成 Home Assistant 设备协议。

DeviceMind 是 **Home Assistant 的设备接入增强层**。它解决 HA 生态一个长期痛点：**接入新设备要写 integration、写 YAML**。

核心创新：**用 LLM 读设备说明书，自动把设备"编译"成结构化协议 JSON**，由 HA 集成直接消费 —— 从此接入一个设备，只需要一份说明书，不再需要人工写 adapter。

## 为什么做这个

Home Assistant 有 1000+ 个 integration，但每一个都是人肉写的；Matter 统一了协议，但要厂商配合认证。现实中大量设备（尤其是国产智能设备）HA 根本不支持，用户只能在论坛发帖求"XX 设备怎么接入"。

DeviceMind 的思路是：**让 AI 读说明书，把"人肉写 adapter"变成"丢说明书"**。

## 工作流

```
设备说明书 ──(一次)──▶ LLM 编译 ──▶ 设备协议 JSON ──▶ 放入 HA 配置目录 ──▶ HA 自动识别设备
                        │
                        └─ 试运行验证出错 / 用户纠正时，回读说明书重编译
```

- **编译期**：LLM 读一次说明书，生成设备协议 JSON，缓存复用
- **运行期**：HA 集成直接消费 JSON 发控制指令，不碰 LLM
- **自我纠错**：试运行验证 topic 错误时，反馈给 LLM 纠错重编译

## 核心特性

| 特性 | 说明 |
|------|------|
| 说明书编译 | LLM 读说明书 → 结构化设备协议 JSON（3B 模型即可） |
| 试运行验证 | 编译后发试探指令验证 topic，错误则反馈纠错重编译 |
| 参数边界校验 | 用设备 min/max/enum 拦截越界指令（如"空调 100 度"） |
| PDF/OCR | 文本型 + 扫描型说明书都能读 |
| 编译缓存 | 相同说明书不重复编译，按内容 hash 自动失效 |
| HA 集成 | 通用集成读取协议 JSON，覆盖 11 类设备（灯/开关/空调/门锁/扫地机/影音/窗帘/风扇/加湿器/摄像头/传感器），支持 UI 配置（config flow） |
| 状态回传 | 订阅 MQTT 状态主题，传感器读数/设备真实状态实时更新 |
| 多协议 | 支持 MQTT 与 HTTP 两种控制协议 |
| HACS 分发 | 可通过 HACS 一键安装 |
| Web UI | 浏览器贴说明书，编译并查看/复制协议 JSON |
| CI | GitHub Actions 自动跑 pytest + ruff（Python 3.10/3.11/3.12） |

## 快速开始

### 1. 配置 LLM 后端（二选一）

**方案 A：本地 Ollama（隐私优先）**

```bash
ollama pull qwen2.5:3b
export DEVICEMIND_LLM_PROVIDER=ollama
```

**方案 B：云端 API（DeepSeek 便宜）**

```bash
export DEEPSEEK_API_KEY=你的key
```

### 2. 编译设备说明书

**方式 A：Web UI**

```bash
pip install -r requirements.txt
python scripts/run_web.py
```

浏览器打开 http://127.0.0.1:5000，粘贴说明书，编译并查看/复制设备协议 JSON。

**方式 B：命令行**

```bash
python scripts/phase0_demo.py examples/sample_light.txt --id lamp-01
```

编译输出的设备协议 JSON：

```json
{
  "id": "lamp-01",
  "type": "light",
  "name": "智能 LED 灯泡",
  "capabilities": [
    {
      "name": "power",
      "actions": [{"name": "turn_on", "params": {}}],
      "properties": {}
    },
    {
      "name": "brightness",
      "actions": [{"name": "set_brightness", "params": {"brightness": {"type": "integer"}}}],
      "properties": {"brightness": {"type": "integer", "min": 1, "max": 100}}
    }
  ],
  "control": {
    "protocol": "mqtt",
    "commands": {
      "turn_on": {"topic": "smarthome/lamp01/set", "payload": {"power": "on"}}
    }
  }
}
```

### 3. 导入 Home Assistant

1. 把 `custom_components/devicemind/` 复制到 HA 的 `config/custom_components/` 目录
2. 重启 HA
3. 在「设置 → 设备与服务 → 添加集成」里搜索 **DeviceMind**，配置设备协议 JSON 目录（默认 `config/devicemind/`）
4. 把编译好的设备协议 JSON 放进该目录
5. 重载集成，设备自动成为 HA entity

> 也可以走 YAML 配置（兼容旧方式）：在 `configuration.yaml` 里写 `devicemind: {devices_dir: devicemind}`

### 4. 本地端到端验证（无需真实设备）

项目自带 Docker Compose 验证环境（HA + Mosquitto），可一键起本地 HA 并用脚本模拟设备，验证「控制 → 状态回传」完整闭环。

```bash
# 1. 启动 Home Assistant + MQTT Broker
docker compose up -d

# 2. 浏览器打开 http://localhost:8123 完成 HA 初始化
# 3. 在 HA「设置 → 设备与服务」添加 MQTT 集成，broker 地址填 mosquitto（端口 1883）
# 4. 添加 DeviceMind 集成（config flow），设备目录用默认 devicemind

# 5. 编译一个设备并放入 HA 配置目录
python scripts/phase0_demo.py examples/sample_light.txt --id lamp-01
cp .devicemind_cache/lamp-01.json ha-config/devicemind/lamp-01.json

# 6. 用脚本模拟一台 MQTT 设备（订阅指令 + 回传状态）
pip install paho-mqtt
python scripts/mock_device.py \
    --control-topic smarthome/lamp01/set \
    --state-topic smarthome/lamp01/state \
    --initial '{"power":"off","brightness":50}'

# 7. 回到 HA，重载 DeviceMind 集成，设备出现在实体列表，可控制并看到状态回传
```

## 项目结构

```
devicemind/
├── src/devicemind/           # 编译器（生成设备协议 JSON）
│   ├── schema.py             # 统一设备模型（核心 Schema）
│   ├── llm.py                # LLM 后端封装（OpenAI 兼容 + Ollama）
│   ├── compiler.py           # 说明书 -> 设备协议 JSON（含缓存）
│   ├── verify.py             # 编译试运行验证闭环
│   ├── ocr.py                # 扫描版 PDF 识别
│   ├── runtime.py            # 动作 -> 控制指令（供 HA 集成复用）
│   └── webapp.py             # Web UI 后端（编译工具）
├── custom_components/devicemind/  # Home Assistant 集成
│   ├── manifest.json
│   ├── config_flow.py        # UI 配置流（添加集成）
│   ├── const.py              # 类型 -> 平台映射
│   ├── runtime.py            # 协议命令构建（runtime 的 HA 侧镜像）
│   ├── base.py               # 平台公共基类（命令构建/发布/状态订阅）
│   ├── mapping.py            # 设备值 <-> HA 枚举双向映射
│   ├── __init__.py           # 扫描协议 JSON，分发到平台
│   ├── light.py              # 灯（开关/亮度/颜色/色温）
│   ├── switch.py             # 开关
│   ├── climate.py            # 空调（HVAC 模式/温度/风速）
│   ├── lock.py               # 门锁
│   ├── vacuum.py             # 扫地机
│   ├── cover.py              # 窗帘/卷帘
│   ├── fan.py                # 风扇
│   ├── humidifier.py         # 加湿器
│   ├── media_player.py       # 影音（音量/开关）
│   ├── camera.py             # 摄像头
│   └── sensor.py             # 传感器
├── hacs.json                 # HACS 分发元数据
├── web/                      # Web UI 前端
├── scripts/
│   ├── run_web.py            # 启动 Web UI
│   ├── phase0_demo.py        # 命令行编译（支持 txt/pdf）
│   ├── batch_test.py         # 泛化批量测试
│   ├── test_ocr.py           # 扫描版 PDF 识别测试
│   └── test_pdf.py           # 文本型 PDF 提取测试
├── examples/
│   ├── sample_*.txt          # 各品类设备说明书样例
│   └── *.pdf                 # 文本型 / 扫描型 PDF 样例
├── tests/                    # 单元测试
└── .github/workflows/ci.yml  # CI（pytest + ruff）
```

## 支持的说明书格式

| 格式 | 支持 | 说明 |
|------|:---:|------|
| 文本文件（.txt） | ✅ | 直接读取 |
| 文本型 PDF | ✅ | pypdf 提取文字 |
| 扫描型 PDF | ✅ | OCR 识别（`pip install rapidocr-onnxruntime pymupdf`） |

## 路线图

- [x] **说明书编译**：LLM 读说明书生成设备协议 JSON
- [x] **试运行验证**：编译纠错闭环 + 参数边界校验
- [x] **Web UI**：浏览器编译并查看协议 JSON
- [x] **HA 集成**：11 类设备平台 + UI 配置（config flow）
- [x] **状态回传闭环**：传感器读数、设备真实状态（MQTT 订阅）
- [x] **HTTP 协议适配**：支持走 HTTP 的设备
- [x] **HACS 分发**：支持 HACS 一键安装
- [ ] **设备知识库共享**：社区共建"说明书 → 协议"映射库

## 许可证

Apache License 2.0
