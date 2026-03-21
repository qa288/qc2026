# 千川投放趋势大盘 - 标准文档总览

## 1. 文档定位

本目录用于定义 **V1 正式开发基线**。  
后续产品、研发、测试、运维如果与本目录冲突，以本目录为准。

当前统一口径：

- 产品定位：公司内部使用的千川经营与投流决策平台
- 页面形态：单登录入口、单主看板，不再并行维护公开页、大屏页、独立 `/admin`
- 官方数据：只走官方开放接口，不做页面抓取
- 通知范围：第一阶段只做 **阈值告警**
- 通知通道：先走 **OpenClaw -> Feishu**，后续再切钉钉
- Token 策略：**单点刷新 + 共享最新 token**
- 账户汇总：官方接口异常时，允许 **计划聚合降级**
- 目标生产架构：**FastAPI + PostgreSQL + Redis + Celery + 独立 scheduler + Docker Compose**

---

## 2. 文档分层

本项目文档分为两层：

### 2.1 标准开发文档
用于指导 V1 正式开发、部署、联调、验收。

位置：
- `qianchuan_standard_docs/`

### 2.2 试运行 / 能力验证文档
用于记录现网试运行实现、接口探测结果、已踩坑点、官方字段能力。

位置：
- `server_payload/qianchuan_openclaw_reporter/docs/`

说明：
- 试运行文档不能直接替代目标生产架构文档
- 正式开发必须以 `qianchuan_standard_docs/` 为准

---

## 3. 建议阅读顺序

1. [13_已确认决策基线.md](/Users/xy/千川/qianchuan_standard_docs/13_已确认决策基线.md)
2. [01_PRD_产品需求文档.md](/Users/xy/千川/qianchuan_standard_docs/01_PRD_产品需求文档.md)
3. [02_页面与交互说明.md](/Users/xy/千川/qianchuan_standard_docs/02_页面与交互说明.md)
4. [03_目标技术架构与部署基线.md](/Users/xy/千川/qianchuan_standard_docs/03_目标技术架构与部署基线.md)
5. [04_数据模型与存储设计.md](/Users/xy/千川/qianchuan_standard_docs/04_数据模型与存储设计.md)
6. [05_内部接口与集成规范.md](/Users/xy/千川/qianchuan_standard_docs/05_内部接口与集成规范.md)
7. [06_任务调度与预警设计.md](/Users/xy/千川/qianchuan_standard_docs/06_任务调度与预警设计.md)
8. [07_开发实施计划.md](/Users/xy/千川/qianchuan_standard_docs/07_开发实施计划.md)
9. [08_测试验收与上线清单.md](/Users/xy/千川/qianchuan_standard_docs/08_测试验收与上线清单.md)
10. [10_Codex_开发交接说明.md](/Users/xy/千川/qianchuan_standard_docs/10_Codex_开发交接说明.md)
11. [11_字段字典与排序规则.md](/Users/xy/千川/qianchuan_standard_docs/11_字段字典与排序规则.md)
12. [12_初始化配置模板.md](/Users/xy/千川/qianchuan_standard_docs/12_初始化配置模板.md)
13. [14_开发执行清单.md](/Users/xy/千川/qianchuan_standard_docs/14_开发执行清单.md)
14. [15_前端执行清单.md](/Users/xy/千川/qianchuan_standard_docs/15_前端执行清单.md)
15. [16_后端执行清单.md](/Users/xy/千川/qianchuan_standard_docs/16_后端执行清单.md)
16. [17_运维上线清单.md](/Users/xy/千川/qianchuan_standard_docs/17_运维上线清单.md)
17. [09_待确认技术项.md](/Users/xy/千川/qianchuan_standard_docs/09_待确认技术项.md)

---

## 4. 当前标准范围

V1 标准范围包括：

- 登录与会话
- 总览页
- 账户、计划、商品/员工、素材榜单
- 时间段筛选、排序、搜索、详情侧栏
- 分钟级同步与历史保留
- 阈值告警
- OpenClaw 通知适配
- Token 单点刷新与内部共享
- Docker Compose 部署

V1 不包括：

- 公开页
- 大屏模式
- 定时简报
- 浏览器抓取
- 多租户
- BI 设计器
- 单点登录

---

## 5. 核心原则

1. 只有一套主技术栈，不再保留 Node/Nest 方案作为正式要求。
2. 只有一套主产品形态，不再并行维护公开页和后台两套系统。
3. 只有一套 Token 真源，不允许多实例各自刷新。
4. 阈值告警优先，定时简报后置。
5. 页面只查本地数据，不直接打官方接口。
6. 先把结构、同步、聚合、告警做稳，再做扩展功能。
