# DOCS 文档导航

本项目所有正式文档统一收口在 `DOCS/`。  
`DOCS/` 是唯一文档入口，旧的散落目录已经废弃并删除。

## 目录架构

- `DOCS/standard/`
  - 正式开发真源
  - 放产品范围、页面设计、技术架构、数据模型、接口规范、实施计划、验收清单
- `DOCS/runtime/`
  - 当前线上实现与运行事实
  - 放现网行为、运行约束、功能规格、目录约束
- `DOCS/runtime/capabilities/`
  - 官方接口能力探测与验证结果
  - 放能力目录、发现手册、能力快照、接口标准
- `DOCS/integrations/`
  - 单专题对接文档
  - 放跨系统接入或专题能力说明
- `DOCS/prompts/`
  - 面向 OpenClaw / 代理执行的提示词与工作约束

## 阅读顺序

1. [标准总览](/Users/xy/千川/DOCS/standard/00_README_千川投放趋势大盘.md)
2. [已确认决策基线](/Users/xy/千川/DOCS/standard/13_已确认决策基线.md)
3. [目标技术架构与部署基线](/Users/xy/千川/DOCS/standard/03_目标技术架构与部署基线.md)
4. [内部接口与集成规范](/Users/xy/千川/DOCS/standard/05_内部接口与集成规范.md)
5. [角色模型与运营工作台方案](/Users/xy/千川/DOCS/standard/20_角色模型与运营工作台方案.md)
6. [管理员预警规则页方案](/Users/xy/千川/DOCS/standard/21_管理员预警规则页方案.md)
7. [工作台重构与完整开发计划](/Users/xy/千川/DOCS/standard/22_工作台重构与完整开发计划.md)
8. [技术架构优化与分阶段推进计划](/Users/xy/千川/DOCS/standard/23_技术架构优化与分阶段推进计划.md)
9. [运行目录说明](/Users/xy/千川/DOCS/runtime/README.md)
10. [运行时接口参考](/Users/xy/千川/DOCS/runtime/API_REFERENCE.md)
11. [官方能力目录](/Users/xy/千川/DOCS/runtime/capabilities/QIANCHUAN_CAPABILITY_CATALOG.md)

## 使用规则

- `DOCS/standard/` 与 `DOCS/runtime/` 冲突时，以 `DOCS/standard/` 为准。
- `DOCS/runtime/` 只记录当前实现事实，不替代正式方案。
- 任何新文档都必须归类到 `DOCS/` 的现有分层中，禁止再新建平行文档根目录。
- 代码、部署、运维调整后，必须同步回写 `DOCS/`，不能只改代码不改文档。

## 专题真源

同类信息只能有一个专题真源，其它文档只做摘要或引用，不重复展开。

- 决策基线：
  - [13_已确认决策基线](/Users/xy/千川/DOCS/standard/13_已确认决策基线.md)
- 技术架构与部署基线：
  - [03_目标技术架构与部署基线](/Users/xy/千川/DOCS/standard/03_目标技术架构与部署基线.md)
- 角色、权限、关键词归属：
  - [20_角色模型与运营工作台方案](/Users/xy/千川/DOCS/standard/20_角色模型与运营工作台方案.md)
- 素材上传：
  - [19_素材上传与批量投放方案](/Users/xy/千川/DOCS/standard/19_素材上传与批量投放方案.md)
- 预警规则：
  - [21_管理员预警规则页方案](/Users/xy/千川/DOCS/standard/21_管理员预警规则页方案.md)
- 实施阶段与排期：
  - [22_工作台重构与完整开发计划](/Users/xy/千川/DOCS/standard/22_工作台重构与完整开发计划.md)
- 技术架构优化推进：
  - [23_技术架构优化与分阶段推进计划](/Users/xy/千川/DOCS/standard/23_技术架构优化与分阶段推进计划.md)
- 当前线上运行事实：
  - [runtime/README.md](/Users/xy/千川/DOCS/runtime/README.md)
  - [runtime/STANDARD.md](/Users/xy/千川/DOCS/runtime/STANDARD.md)
  - [runtime/API_REFERENCE.md](/Users/xy/千川/DOCS/runtime/API_REFERENCE.md)

如果同类信息在多份文档同时出现，以对应专题真源为准。
