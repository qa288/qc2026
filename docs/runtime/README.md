# Qianchuan Runtime Docs

这是当前千川看板的试运行实现与运行口径文档。

当前定位：

- 记录当前运行中的代码架构、数据链路和页面行为
- 记录官方能力验证结论与已踩坑点
- 为后续重构、迁移和新增功能提供运行事实参考
- 不替代 `docs/standard/` 的正式开发决策文档

在本目录内进行任何修改前，必须先阅读：

- [FUNCTIONAL_SPEC.md](./FUNCTIONAL_SPEC.md)
- [STANDARD.md](./STANDARD.md)
- [AGENTS.md](./AGENTS.md)
- [QIANCHUAN_OFFICIAL_API_STANDARD.md](./capabilities/QIANCHUAN_OFFICIAL_API_STANDARD.md)
- [QIANCHUAN_CAPABILITY_CATALOG.md](./capabilities/QIANCHUAN_CAPABILITY_CATALOG.md)
- [DATA_ARCHITECTURE.md](./capabilities/DATA_ARCHITECTURE.md)

## 关联代码与配置

- `server_payload/qianchuan_openclaw_reporter/config.json`
  - 真实运行配置
- `server_payload/qianchuan_openclaw_reporter/config.example.json`
  - 配置样例
- `server_payload/qianchuan_openclaw_reporter/report_qianchuan.py`
  - 固定数据采集与报表生成脚本
- `server_payload/qianchuan_openclaw_reporter/dashboard/`
  - Docker 内运行的经营看板服务
- `server_payload/qianchuan_openclaw_reporter/docker-compose.dashboard.yml`
  - Web 看板的容器编排文件
- `server_payload/qianchuan_openclaw_reporter/bridge_send_alerts.py`
  - 将页面触发的待发送阈值告警推送到 OpenClaw 已配置的通知渠道
- `server_payload/qianchuan_openclaw_reporter/tools/discover_qianchuan_capabilities.py`
  - 官方能力发现脚本，用于确认主题、维度、指标和必填过滤条件
- `capabilities/`
  - 能力目录、架构文档、发现手册与最新发现结果
- `capabilities/QIANCHUAN_OFFICIAL_API_STANDARD.md`
  - 给同事直接参考的官方接口开发标准手册
- `STANDARD.md`
  - 长期标准文档
- `FUNCTIONAL_SPEC.md`
  - 功能规格、已实现能力与重构验收基线
- `AGENTS.md`
  - 当前目录的强制约束

## 配置优先级

当前项目已经统一支持：

1. 默认值
2. `config.json`
3. 环境变量覆盖

也就是：

- 环境变量优先级最高
- `config.json` 继续保留，作为本地和服务器默认配置
- 如果只想覆盖敏感字段，可以只设置环境变量，不必改动 `config.json`

核心环境变量：

```bash
export APP_ID="..."
export APP_SECRET="..."
export REFRESH_TOKEN="..."
export CUSTOMER_CENTER_ID="..."
```

常用扩展环境变量：

```bash
export FEISHU_TARGET="..."
export TIMEZONE="Asia/Shanghai"
export ACCOUNT_SOURCE="QIANCHUAN"
export MARKETING_GOAL="ALL"
export ORDER_PLATFORM="QIANCHUAN"
export PLAN_MARKETING_GOALS="VIDEO_PROM_GOODS,LIVE_PROM_GOODS"
export PLAN_PAGE_SIZE="100"
```

## 当前运行方式

当前正式运行方式统一为 Docker Compose：

```bash
docker-compose -f docker-compose.dashboard.yml --env-file .env.dashboard up -d --build
```

现网运维入口：

- 通过 `1Panel` 管理反向代理和站点入口
- 通过 `1Panel` 查看 Docker 应用与容器状态
- 应用内部服务编排仍然以 Compose 文件为准

服务拆分：

- `web`
  - FastAPI 页面与内部 API
- `worker`
  - Celery 异步任务执行器
- `scheduler`
  - Celery Beat，负责任务调度
- `postgres`
  - 主数据库
- `redis`
  - 队列、缓存、token 刷新锁

调度节奏：

- 每 `1` 分钟主快照同步一次
- 每 `10` 分钟细粒度同步一次
- 告警只保留阈值告警，不再发送定时简报

## 当前目标输出

- `9898` 端口提供登录保护的运营看板
- 页面必须覆盖：
  - 全部账户整体情况
  - 每个账户的基本情况
  - 推广计划的排名明细
  - 商品、素材、员工维度的经营拆解
  - 阈值告警配置与告警事件
- 计划排名默认按 `订单数 -> 支付金额 -> ROI -> 消耗` 排序

Dashboard 页面当前包含：

- 六个主视图：`总览 / 账户 / 经营拆解 / 计划 / 素材 / 通知规则`
- 总览：KPI、系统状态、明细同步状态、老板关注提醒
- 账户：按账户看 `消耗 / 支付 / 订单 / ROI`，支持排序、搜索和 `日 / 周 / 月`
- 经营拆解：商品榜和员工榜，支持排序、搜索、详情卡和 `日 / 周 / 月`
- 计划：计划明细表 + 右侧详情栏 + 最近一次素材/商品摘要
- 素材：素材榜单 + 右侧素材详情，支持刷新最近一次明细同步结果
- 通知规则：统一管理通知渠道、目标和阈值规则

当前落库层已经包括：

- 分钟级：`summary_snapshots / account_snapshots / plan_snapshots`
- 10 分钟级细粒度：`plan_detail_snapshots / product_snapshots / material_snapshots / video_origin_flags`
- 细粒度同步状态：`extended_sync_runs`

当前页面 API 额外可直接读取：

- `POST /api/sync/extended`
  - 手动触发一次细粒度同步
- `GET /api/plans/{ad_id}/assets`
  - 读取某条计划最近一次落库的详情、商品、素材和视频首发标记
- `GET /api/material-rankings`
  - 读取最近一次素材聚合榜单
- `GET /api/system/integrations/ocean-engine/token-latest`
  - 登录后读取当前最新 `access_token / refresh_token / expires_at / updated_at`
- `POST /api/system/integrations/ocean-engine/exchange-auth-code`
  - 用新的 `auth_code` 直接换最新 token，并覆盖本地 token 真源

当前数据能力结论：

- 账户、计划、商品、素材、视频 已确认有官方实现路径
- 员工维度属于派生实现
- 剪辑人员 / 制作人 / 编辑人 不属于千川官方直接字段
- 部分 `SITE_PROMOTION_POST_*` / `SITE_PROMOTION_PRODUCT_*` 主题还需补业务过滤条件
- 最新探测结果见 [capability_snapshot_latest.md](./capabilities/discovery/capability_snapshot_latest.md)

当前员工维度口径：

- 第一版按计划里的 `anchor_name` 聚合
- `anchor_name` 为空时统一归到 `未归属`
- 如果后续引入员工映射表，必须先更新 `FUNCTIONAL_SPEC.md` 和 `STANDARD.md`

当前 Web 看板数据刷新节奏：

- 服务端采集：每 `1` 分钟
- 浏览器轮询：每 `60` 秒

当前 token 真源：

- 逻辑真源：PostgreSQL `oauth_tokens`
- 缓存副本：`/app/data/qianchuan_latest_token.json`
- 其它服务器只读主服务器的 token，不要各自独立刷新
- 推荐读取方式：
  - 登录 dashboard 后请求 `GET /api/system/integrations/ocean-engine/token-latest`
  - 或直接在主服务器读取 `/opt/qianchuan/qianchuan_openclaw_reporter/data/qianchuan_latest_token.json`
- token 刷新使用 Redis 分布式锁，避免多 worker 在过期点并发刷新

## 重要说明

- 功能完整性、页面行为、通知能力、验收清单，以 `FUNCTIONAL_SPEC.md` 为第一基线。
- 新增任何数据维度前，必须先看 `capabilities/QIANCHUAN_CAPABILITY_CATALOG.md`，不确定时先跑 `tools/discover_qianchuan_capabilities.py`。
- 这是运行文档目录，对应代码目录不要随意重命名脚本、改动配置字段或删除任务逻辑。
- 不要改掉 `9898` 的 dashboard 部署和登录保护，除非用户明确要求。
- 如果要增加更多数据、更多维度、更多提醒，必须按 `STANDARD.md` 的扩展流程进行。
