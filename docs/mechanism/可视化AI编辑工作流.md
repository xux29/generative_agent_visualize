# 可视化平台：AI 改机制 / 改参数工作流

专家在可视化页面对话，由独立的「编辑模型」按两份 Cursor Skill 改**参数 JSON** 或 **机制代码**。默认只写提案，批准后才进 live。

仿真用的小镇 LLM（`data/config.json`）与编辑 LLM **分开配置**。

## 1. 流程

```text
可视化 /editor 对话
        │
        ▼
编辑 LLM（OpenAI 兼容 API + tool calling）
        │  系统提示 = 两份 Skill
        ▼
propose → edit_config / replace_in_file / edit_code → validate → promote
        │
        ▼
专家点「批准落地」→ 写入 active.json 与白名单代码
（可选：只落地 JSON）
```

| 用户说法 | 走哪条 Skill | 工具 |
|----------|--------------|------|
| 概率太大、权重拧一下、阈值 | `edit-mechanism-config` | `edit_config` |
| 改公式、新状态、新机制 | `edit-health-mechanisms` | `replace_in_file` / `edit_code` |
| 斯坦福基座 / 日循环 / 密钥 / 前端 | 拒绝 | 无 |

硬性约束：

- 不自动 `approve`。模型只能 `promote`，落地必须人点按钮。
- 代码白名单：`modules/health_mechanisms/**`、`data/mechanism/prompts/`、`registry.json`。
- 编辑器自身（`editor_*.py`、`ai_edit.py`、`model_version.py`、`sandbox.py`）冻结，防止自我改权。

## 2. 怎么开

1. 复制配置并填 Key：

```bash
cd generative_agents
cp data/mechanism/editor_llm.example.json data/mechanism/editor_llm.json
# 编辑 api_key、model、base_url
```

或环境变量：`EDITOR_LLM_API_KEY`、`EDITOR_LLM_MODEL`、`EDITOR_LLM_BASE_URL`。

2. 启动可视化（默认 `http://127.0.0.1:5001`）：

```bash
cd generative_agents
python visualize_health.py
```

打开 [http://127.0.0.1:5001/editor](http://127.0.0.1:5001/editor)。首页也有入口。

3. 对话改完后，右侧「待批准模型」点批准。CLI 仍可用：`python tools/model_cli.py`。

## 3. 接口（给前端 / 调试）

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/editor` | 对话页 |
| GET | `/api/editor/status` | 是否已配 Key、当前模型 |
| GET | `/api/editor/state` | 提案 / 模型列表 |
| POST | `/api/editor/chat` | `{message, session_id}` |
| POST | `/api/editor/approve` | `{model_id, config_only?}` |
| POST | `/api/editor/rollback` | `{model_id, config_only?}` |

## 4. 界面可调范围（22 项）

可视化 `/editor` 滑杆与 AI `set_ui_param` / `edit_config` **仅**允许 [`界面可调参数.md`](./界面可调参数.md) 中的 22 个 UI 键。  
其余 JSON 字段（主体属性、潮汐、行为扣分表等）不在界面暴露；改它们需走机制代码 Skill，或由开发者直接改 `active.json`。

映射实现：`generative_agents/modules/mechanism_config/ui_tunable.py`

## 5. 模型怎么配（OpenAI 兼容）

`editor_llm.json` 示例：

```json
{
  "model": "deepseek-v4-flash",
  "base_url": "https://api.deepseek.com",
  "api_key": "sk-...",
  "temperature": 0.2,
  "max_tokens": 8192,
  "max_tool_rounds": 8,
  "thinking": false
}
```

| 厂商 | `base_url` | 推荐 `model` |
|------|------------|----------------|
| DeepSeek 官方 | `https://api.deepseek.com` | `deepseek-v4-flash` |
| 阿里云百炼（国内） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.5-flash` 或 `qwen3-coder-plus` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.7-flashx` 或 `glm-4.7` |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.6-luna` |

`thinking: false` 可关掉 DeepSeek 默认思考，压低输出费用；难改代码时可改为 `true`。

## 5. 性价比推荐（2026-08-18 核对）

工作负载特点：系统提示含两份 Skill（可缓存）、多轮 tool calling、偶发整文件代码。看的是「能稳定调工具 + 会改 Python」的单位成本，不是纯聊天单价。

价格会变，落地前请再对官网：

- [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/)
- [阿里云百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)
- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)

### 首选组合

1. **默认：DeepSeek V4 Flash**（`deepseek-v4-flash`）  
   官方标明 Tool Calls、1M 上下文。忙时（UTC 01:00–04:00 与 06:00–10:00，约北京 09:00–12:00 与 14:00–18:00）cache miss **$0.44 / $1.32** /百万 tokens；闲时减半 **$0.22 / $0.66**；缓存命中约 miss 的 1/30。Skill 前缀几乎不变，缓存很值。适合本工作流的默认编辑模型。

2. **升级：DeepSeek V4 Pro**（`deepseek-v4-pro`）  
   同样官方支持工具调用。闲时 miss **$0.66 / $1.98**，忙时 **$1.32 / $3.96**。只在 Flash 改砸公式、多文件机制时换。

3. **国内极便宜备选：Qwen3.5 Flash**（百炼 `qwen3.5-flash`）  
   华北2 文档：≤128K 约 **¥0.20 / ¥2.00** /百万 tokens。输入极便宜，适合分流/简单改参。复杂代码与多步工具不如 Flash/Pro 稳，不建议作为唯一代码编辑模型。

4. **国内代码备选：Qwen3 Coder Plus**（`qwen3-coder-plus`）  
   百炼华北约 **¥4 / ¥16**（短上下文档）。代码专项更强，但比 DeepSeek Flash 贵一个数量级，适合偶发难题，不适合每句对话都跑。

5. **海外备选：GPT-5.6 Luna**  
   官方短上下文 **$0.20 / $1.20**（缓存读 $0.02）。工具生态成熟，单价高于 DeepSeek 闲时 Flash，国内延迟和发票通常不如前几家。

### 不太建议当默认

| 模型 | 原因 |
|------|------|
| Claude Sonnet / Opus | 质量高，本工作流对话轮次多，账单上得快 |
| GPT-5.6 Terra / Sol | Luna 已够用时溢价明显 |
| 仅免费限流档（如部分 GLM Flash） | 可试用，不适合专家改机制的稳定工具循环 |

### 一句话

国内专家改机制：**先配 DeepSeek V4 Flash**；改参试水可用 Qwen3.5 Flash；Flash 搞不定公式再升 V4 Pro 或 Qwen Coder Plus。
