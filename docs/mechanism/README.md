# 机制文档索引

健康仿真机制相关说明集中在本目录；参数 JSON 本体仍在 `generative_agents/data/mechanism/`。

| 文档 | 说明 |
|------|------|
| [机制参数升降影响手册.md](./机制参数升降影响手册.md) | 对 `active.json` 每个可升降参数：升高/降低后模拟如何变（机制层实测） |
| [param_impact/](./param_impact/) | 验参原始结果与复现说明 |
| [../机制参数JSON使用指南.md](../机制参数JSON使用指南.md) | 如何改 JSON / CLI / 版本 |
| [../健康机制双层架构与AI编辑.md](../健康机制双层架构与AI编辑.md) | 双层架构、AI 编辑边界、注册表 |
| [../健康机制改动前后对比.md](../健康机制改动前后对比.md) | 相对改动前的能力对比 |
| [../健康干预仿真_可调参数全景.md](../健康干预仿真_可调参数全景.md) | 早期参数盘点（以升降手册为准） |

## 代码与配置路径

| 路径 | 作用 |
|------|------|
| `generative_agents/data/mechanism/active.json` | 当前生效参数 |
| `generative_agents/data/mechanism/registry.json` | 机制注册表 |
| `generative_agents/modules/health_mechanisms/` | 机制代码（含 `rules/`） |
| `generative_agents/tools/param_impact_sweep.py` | 升降验参脚本 |
| `generative_agents/tools/param_zh_catalog.py` | 参数中文名/说明 |
| `.cursor/skills/edit-mechanism-config/` | AI 改参数 Skill |
| `.cursor/skills/edit-health-mechanisms/` | AI 改机制代码 Skill |
