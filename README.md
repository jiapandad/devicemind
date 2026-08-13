# DeviceMind

> 设备世界的操作系统 —— 让任何设备"会自我介绍"，让用户"说人话就能控制"。

DeviceMind 是一个跑在本地 Hub 上的 **AI 设备运行时**。它解决一个困扰智能家居多年的问题：**设备碎片化**。

核心创新：**用 LLM 读设备说明书，自动把设备"编译"成结构化协议，从此不需要人工写 adapter。**

## 为什么做这个

现在的智能家居有三大痛点：

| 痛点 | 现状 |
|------|------|
| 设备不互通 | 米家、涂鸦、HomeKit 各自为政 |
| 接入要写代码 | Home Assistant 要写 YAML，Matter 要厂商配合 |
| 规则要人写 | "回家模式"要手动配置每一条联动 |

DeviceMind 的思路是：**让 AI 自己读说明书、自己理解设备、自己编排控制。** 用户只需要说一句"我回家了"。

## 核心思路

```
设备说明书 ──编译期(一次)──▶ LLM 理解 ──▶ 编译成 JSON 缓存
                                       ▲            │
                                       │            ▼
                           执行出错/用户纠正   运行期(一万次) 直接查 JSON
```

- **编译期**：新设备接入时，LLM 读一次说明书，生成设备描述 JSON，缓存起来
- **运行期**：每次控制设备，直接查 JSON，毫秒级响应，不再调用 LLM
- **自我纠错**：执行出错或用户纠正时，回读说明书重新编译

## 快速开始

### 1. 安装依赖

```bash
pip install openai pypdf
```

### 2. 配置 LLM 后端（二选一）

**方案 A：本地 Ollama（隐私优先，推荐 qwen2.5:3b）**

```bash
# 安装 Ollama 后（3b 仅 1.9GB，实测能力提取 100%，7b 更重无必要）
ollama pull qwen2.5:3b
export DEVICEMIND_LLM_PROVIDER=ollama
```

**方案 B：云端 API（推荐 DeepSeek，便宜）**

```bash
export DEEPSEEK_API_KEY=你的key
```

### 3. 运行 Phase 1 交互演示（无需 LLM 也能跑）

```bash
# 完整闭环：意图 → 控制虚拟设备（用预置示例设备，无需 LLM）
python scripts/demo_cli.py --demo
```

进入交互后，输入自然语言指令即可：

```
> 打开
  [意图] action=turn_on, params={'power': 'on'}
  [指令] mqtt smarthome/lamp01/set -> {'power': 'on'}
  [状态] {'power': 'on'}

> 调到50%
  [意图] action=set_brightness, params={'brightness': 50}
  [指令] mqtt smarthome/lamp01/set -> {'brightness': 50}
  [状态] {'power': 'on', 'brightness': 50}
```

### 4. 运行 Phase 0 验证（编译期，需 LLM）

```bash
python scripts/phase0_demo.py examples/sample_light.txt --id lamp-01
```

输出示例（编译后的设备 JSON）：

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
      "actions": [{"name": "set_brightness", "params": {"brightness": {"type": "number"}}}],
      "properties": {"brightness": {"type": "number", "min": 1, "max": 100}}
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

## 项目结构

```
devicemind/
├── src/devicemind/
│   ├── __init__.py
│   ├── schema.py       # 统一设备模型（核心 Schema）
│   ├── llm.py          # LLM 后端封装（OpenAI 兼容 + Ollama）
│   ├── compiler.py     # 编译期核心：说明书 -> 设备 JSON
│   ├── intent.py       # 意图理解：自然语言 -> 结构化意图
│   ├── runtime.py      # 运行期核心：动作 -> 控制指令
│   ├── simulator.py    # 虚拟设备模拟器（无硬件也能跑）
│   └── ocr.py          # 扫描版 PDF 识别（pymupdf + RapidOCR）
├── scripts/
│   ├── phase0_demo.py  # Phase 0 验证脚本（编译期，支持 txt/pdf）
│   ├── demo_cli.py     # Phase 1 交互演示（完整闭环）
│   └── batch_test.py   # 泛化批量测试（多设备类型）
├── examples/
│   └── sample_*.txt    # 8 类设备说明书样例
└── tests/
```

## 支持的说明书格式

| 格式 | 支持 | 说明 |
|------|:---:|------|
| 文本文件（.txt） | ✅ | 直接读取 |
| 文本型 PDF | ✅ | pypdf 提取文字（Word 导出的） |
| 扫描型 PDF | ✅ | OCR 识别（需安装 `rapidocr-onnxruntime pymupdf`） |

扫描版 PDF 的处理链路：`PDF → 转图片 → RapidOCR 识别中文 → LLM 编译成设备 JSON`。

## 路线图

- [x] **Phase 0**：LLM 读说明书生成设备 JSON（验证核心假设）
- [x] **Phase 1**：MVP 闭环 —— 用户意图 → 控制虚拟设备
- [ ] **Phase 2**：接入真实设备（MQTT）
- [ ] **Phase 3**：开源社区 + 设备知识库
- [ ] **Phase 4**：世界模型（预测式智能）

## 许可证

Apache License 2.0
