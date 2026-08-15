# 参数升降验参产物

本目录存放对 `generative_agents/data/mechanism/active.json` 的机制层对照实测结果（无 LLM）。

| 文件 | 说明 |
|------|------|
| `sweep_results.json` | 全量叶子参数 ↑/↓ 探针指标与中文名/说明 |
| 人读手册 | 见上一级 [机制参数升降影响手册.md](../机制参数升降影响手册.md) |

## 复现

```bash
cd generative_agents
python3 tools/param_impact_sweep.py \
  --config data/mechanism/active.json \
  --out-dir ../docs/mechanism/param_impact
```

默认会写入手册 `docs/mechanism/机制参数升降影响手册.md`，并更新 Cursor Canvas（若本机路径存在）。
