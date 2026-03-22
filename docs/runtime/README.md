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
set -a && . ./.env.dashboard && set +a
docker-compose -f docker-compose.dashboard.yml up -d --build
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

- `9898` 端口提供公开页与登录保护的运营工作台
- 当前正式域名：`qc.tyos.cc`
- 页面必须覆盖：
  - 公开归属人排名页
  - 全部账户整体情况
  - 每个账户的基本情况
  - 推广计划的排名明细
  - 商品、素材、员工维度的经营拆解
  - 员工归属规则与账号权限
  - 阈值告警配置与告警事件
- 计划排名默认按 `订单数 -> 支付金额 -> ROI -> 消耗` 排序

Dashboard 页面当前包含：

- 公开页：`/`
  - 匿名可访问归属人排名页
  - 当前默认列：`排名 / 归属人 / 消耗 / 支付 / 订单 / ROI / 计划数 / 账户数`
  - 顶部有归属人数、榜首归属人、总消耗、总订单四个摘要卡
  - 若已配置归属规则，则只展示正式归属人；若未配置，则回退到主播字段兜底并在页面提示
- 工作台：`/workbench`
  - 八个主视图：`总览 / 账户 / 经营拆解 / 计划 / 素材 / 归属规则 / 权限 / 预警中心`
- 总览：KPI、系统状态、明细同步状态、老板关注提醒
- 账户：按账户看 `消耗 / 支付 / 订单 / ROI`，支持排序、搜索和 `日 / 昨日 / 周 / 月 / 指定日期范围`
- 经营拆解：商品榜和归属人榜，支持排序、搜索、详情卡和 `日 / 昨日 / 周 / 月 / 指定日期范围`
- 计划：计划明细表 + 右侧详情栏 + 最近一次素材/商品摘要
- 素材：素材榜单 + 右侧素材详情，支持 `日 / 昨日 / 周 / 月 / 指定日期范围`，跨天按每日最后一次明细快照汇总
- 归属规则：维护归属人、关键词规则、命中预览、人工绑定和未归属池
  - 未归属池支持 `账户 / 计划 / 商品 / 素材` 四类对象的一键绑定
- 权限：维护后台账号和账户可见范围
- 预警中心：统一管理通知通道、模板式阈值规则和告警事件

当前落库层已经包括：

- 分钟级：`summary_snapshots / account_snapshots / plan_snapshots`
- 分钟级余额与钱包：`account_balances / shared_wallets / shared_wallet_account_relations`
- 10 分钟级细粒度：`plan_detail_snapshots / product_snapshots / material_snapshots / video_origin_flags`
- 素材预聚合：`material_rollups`
- 细粒度同步状态：`extended_sync_runs`

当前页面 API 额外可直接读取：

- `GET /api/public/employee-rankings`
  - 匿名公开归属人榜
- `POST /api/sync/extended`
  - 手动提交一次细粒度同步任务，接口立即返回 `202`
- `GET /api/plans/{ad_id}/assets`
  - 读取某条计划最近一次落库的详情、商品、素材和视频首发标记
- `GET /api/material-rankings`
  - 读取素材聚合榜单，优先走 `material_rollups`
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

- 当前正式口径是“归属人”
- 归属人来自管理员维护的：
  - 归属人列表
  - 关键词规则
  - 人工绑定
  - 未归属池人工修正
- 命中对象包括：
  - 账户
  - 计划
  - 商品
  - 素材
- 未命中任何规则时统一归到 `未归属`
- 若当前还没有配置任何归属规则，则公开页和后台归属人榜会回退到 `anchor_name` 兜底聚合；一旦配置归属人后，公开页仅展示正式归属人结果
- 当前运营角色查看归属规则页时默认为只读；管理员可修改归属人、关键词和绑定

## 查询执行边界

当前正式规则：

- 页面查询接口只读本地库，不允许在查询请求里直接拉取 OceanEngine 远程报表
- 官方接口只允许出现在：
  - 定时同步任务
  - 手动补数
  - token 换取与刷新
- 当前已确认纯读库的页面接口包括：
  - `GET /api/public/employee-rankings`
  - `GET /api/dashboard`
  - `GET /api/performance`
  - `GET /api/material-rankings`
  - `GET /api/accounts/{advertiser_id}/history`
  - `GET /api/plans/{ad_id}/history`
  - `GET /api/plans/{ad_id}/assets`

这条规则是为了避免再次出现“切时间范围时页面绕回官方接口、导致响应变慢”的问题。

## 历史回补与预聚合

当前历史与性能策略：

- `GET /api/performance`
  - 默认只读 `summary_snapshots / account_snapshots / plan_snapshots`
  - 若查询 `昨日 / 本周 / 本月 / 指定日期范围` 时发现缺失历史日快照：
    - 自动按天从官方接口回补
    - 回补完成后写入 PostgreSQL
    - 后续查询继续只读库
- `GET /api/material-rankings`
  - 优先读取 `material_rollups`
  - `material_rollups` 在每次细粒度同步后生成
  - 如历史老快照尚未生成 `material_rollups`，才临时回退到 `material_snapshots` 聚合

## 手动同步行为

当前手动同步接口统一改为“入队，不阻塞等待”：

- `POST /api/sync`
- `POST /api/sync/extended`

接口行为：

- 立即返回 `202 Accepted`
- 由 Celery Worker 异步执行
- 避免经过 1Panel / 反向代理时因长任务导致 `504 Gateway Timeout`

当前 Web 看板数据刷新节奏：

- 服务端采集：每 `1` 分钟
- 浏览器轮询：每 `60` 秒

当前余额与共享钱包口径：

- 主来源：`/open_api/v3.0/account/fund/get/`
- 账户余额使用：
  - `total_balance`
  - `valid_balance`
- 共享钱包使用：
  - `wallet_id`
  - `wallet_total_balance_valid`
- 当前通过同 `wallet_id` 关联多个账户来推导共享钱包关系
- 更高权限共享钱包接口当前存在权限限制，不作为 V1 主链路

当前预警中心口径：

- 规则类型支持：
  - 账户
  - 计划
  - 账户余额
  - 共享钱包
  - 爆单计划
- 页面提供快速模板：
  - 账户余额
  - 共享钱包
  - 计划消耗
  - 爆单计划
- 当前支持页面内触发记录与外发配置结构；是否实际外发取决于通知开关与渠道配置

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
