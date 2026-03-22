# Docs Index

本项目所有正式文档统一收口在 `docs/`。

目录分层：

- `standard/`
  - V1 正式开发、部署、运维、接口和验收基线
- `runtime/`
  - 当前试运行实现、现网口径、能力验证与运行约束
- `runtime/capabilities/`
  - 官方接口能力目录、发现手册、能力快照
- `integrations/`
  - 具体对接专题文档
- `prompts/`
  - OpenClaw 主提示词和后续扩展提示词

建议阅读顺序：

1. [标准总览](/Users/xy/千川/docs/standard/00_README_千川投放趋势大盘.md)
2. [已确认决策基线](/Users/xy/千川/docs/standard/13_已确认决策基线.md)
3. [目标技术架构与部署基线](/Users/xy/千川/docs/standard/03_目标技术架构与部署基线.md)
4. [内部接口与集成规范](/Users/xy/千川/docs/standard/05_内部接口与集成规范.md)
5. [公开页与后台重构方案](/Users/xy/千川/docs/standard/18_公开页与后台重构方案.md)
6. [运行目录说明](/Users/xy/千川/docs/runtime/README.md)
7. [官方能力目录](/Users/xy/千川/docs/runtime/capabilities/QIANCHUAN_CAPABILITY_CATALOG.md)

统一规则：

- `docs/standard/` 是正式开发真源
- `docs/runtime/` 是当前实现与能力验证基线
- 不再以 `qianchuan_standard_docs/` 或 `server_payload/.../docs/` 作为文档入口
