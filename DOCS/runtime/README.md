# Qianchuan Runtime Docs

这是当前千川看板的试运行实现与运行口径文档。

当前定位：

- 记录当前运行中的代码架构、数据链路和页面行为
- 记录官方能力验证结论与已踩坑点
- 为后续重构、迁移和新增功能提供运行事实参考
- 不替代 `DOCS/standard/` 的正式开发决策文档

专题真源：

- 决策基线：
  - [13_已确认决策基线](/Users/xy/千川/DOCS/standard/13_已确认决策基线.md)
- 角色与权限：
  - [20_角色模型与运营工作台方案](/Users/xy/千川/DOCS/standard/20_角色模型与运营工作台方案.md)
- 素材上传：
  - [19_素材上传与批量投放方案](/Users/xy/千川/DOCS/standard/19_素材上传与批量投放方案.md)
- 预警规则：
  - [21_管理员预警规则页方案](/Users/xy/千川/DOCS/standard/21_管理员预警规则页方案.md)

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
- 线上目录 `/opt/qianchuan/qianchuan_openclaw_reporter` 不是 Git 工作树
- 正式发布通过“同步文件 + Compose 重建”完成，不依赖线上目录直接 `git pull`

当前运行检查接口：

- `GET /healthz`
  - 用于进程存活检查
- `GET /readyz`
  - 用于数据库、Redis、Celery 与 schema 版本就绪检查

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

## 当前线上页面事实

- 当前正式域名：`qc.tyos.cc`
- 所有角色统一登录后进入工作台，不再保留匿名公开页
- 当前页面结构与角色口径以 `DOCS/standard/20` 和 `DOCS/standard/22` 为准
- 这里仅记录线上当前可访问模块，不再重复做产品决策

Dashboard 当前包含：

- 登录页：`/login`
- 工作台：`/`
- 当前管理员主导航：`总览 / 账户 / 计划 / 素材 / 运营排名 / 批量上传 / 账号与权限 / 预警`
- 主管按账户范围裁剪，运营按关键词结果裁剪
- 所有跨日查询统一支持：`日 / 昨日 / 近7天 / 近30天 / 指定日期范围`
- 页面查询只读本地库；若缺历史，会异步排队回补，不在请求链路里直连远程接口

当前落库层已经包括：

- 分钟级：`summary_snapshots / account_snapshots / plan_snapshots`
- 分钟级余额与钱包：`account_balances / shared_wallets / shared_wallet_account_relations`
- 10 分钟级细粒度：`plan_detail_snapshots / product_snapshots / material_snapshots / video_origin_flags`
- 素材预聚合：`material_rollups`
- 细粒度同步状态：`extended_sync_runs`
- schema 版本记录：`schema_migrations`

当前页面 API 额外可直接读取：

- `GET /api/session/me`
  - 登录后读取当前账号与权限能力
- `POST /api/sync/extended`
  - 手动提交一次细粒度同步任务，接口立即返回 `202`
- `POST /api/sync/backfill/performance`
  - 管理员手动提交一次主快照历史回补任务，默认回补最近 `30` 天
- `POST /api/sync/backfill/extended`
  - 管理员手动提交一次细粒度历史回补任务，默认回补最近 `30` 天
- `GET /api/plans/{ad_id}/assets`
  - 读取某条计划最近一次落库的详情、商品、素材和视频首发标记
- `GET /api/material-rankings`
  - 读取素材聚合榜单，优先走 `material_rollups`
- `GET /api/system/integrations/ocean-engine/token-latest`
  - 登录后读取当前最新 `access_token / refresh_token / expires_at / updated_at`
- `POST /api/system/integrations/ocean-engine/exchange-auth-code`
  - 用新的 `auth_code` 直接换最新 token，并覆盖本地 token 真源

当前账号权限口径：

- 管理员：全量页面、全量数据、账号与权限配置、预警规则配置
- 主管：仅查看被分配账户范围内的数据；如管理员开启“允许上传素材”，则可使用上传页
- 运营：不配置账户范围，只按管理员分配的关键词查看命中数据

当前上传页状态：

- 已支持目标搜索、计划勾选、视频文件选择、上传任务入库
- 管理员和已开启上传权限的主管可用
- 已接通后台异步执行链路：
  - 按账户分组上传
  - 同账户按文件 hash 复用已上传素材
  - 逐计划绑定素材
- 当前任务状态会经历：
  - `prepared`
  - `processing`
  - `completed / failed`
- 当前线上已知阻塞点不是执行器，而是部分广告主缺少官方接口权限：
  - `/open_api/v3.0/local/file/video/upload/`
- 当官方返回权限不足时，任务会失败并展示友好错误文案

当前数据能力结论：

- 账户、计划、商品、素材、视频 已确认有官方实现路径
- 员工维度属于派生实现
- 剪辑人员 / 制作人 / 编辑人 不属于千川官方直接字段
- 部分 `SITE_PROMOTION_POST_*` / `SITE_PROMOTION_PRODUCT_*` 主题还需补业务过滤条件
- 最新探测结果见 [capability_snapshot_latest.md](./capabilities/discovery/capability_snapshot_latest.md)

当前运营归属口径：

- 当前正式口径是“运营账号关键词归属”
- 管理员给运营账号配置一个或多个关键词
- 命中对象包括：
  - 账户
  - 计划
  - 商品
  - 素材
- 命中结果聚合到对应运营账号，用于团队排名和运营工作台
- 未命中任何规则时统一归到 `未归属`
- 若当前还没有配置任何运营关键词，团队榜会回退到 `anchor_name` 兜底聚合；一旦配置运营关键词后，优先展示正式运营账号排名
- 当前运营角色只读自己的命中结果，不维护全局规则；管理员可修改关键词和绑定

当前素材预览口径：

- 管理员 / 主管 / 运营的素材列表均支持“预览素材”入口
- 若素材存在可播放地址，则弹层内直接播放
- 若只有封面，则展示封面图
- 若官方未返回可播放地址，则提示当前素材暂不可直接播放

## 查询执行边界

当前正式规则：

- 页面查询接口只读本地库，不允许在查询请求里直接拉取 OceanEngine 远程报表
- 官方接口只允许出现在：
  - 定时同步任务
  - 手动补数
  - token 换取与刷新
- 当前已确认纯读库的页面接口包括：
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
  - 若查询 `昨日 / 近7天 / 近30天 / 指定日期范围` 时发现缺失历史日快照：
    - 不在页面请求里直接远程拉数
    - 只返回当前已有库内结果，并标记 `history_backfill_pending`
    - 由定时任务或管理员手动触发回补
- `GET /api/material-rankings`
  - 优先读取 `material_rollups`
  - `material_rollups` 在每次细粒度同步后生成
  - 查询 `昨日 / 近7天 / 近30天 / 指定日期范围` 时，会先检查是否缺少历史明细日快照
  - 若缺失：
    - 不在页面请求里直接远程拉数
    - 只返回当前已有库内结果，并标记 `history_backfill_pending`
    - 由定时任务或管理员手动触发回补
  - 如历史老快照尚未生成 `material_rollups`，才临时回退到 `material_snapshots` 聚合

## 手动同步行为

当前手动同步接口统一改为“入队，不阻塞等待”：

- `POST /api/sync`
- `POST /api/sync/extended`
- `POST /api/sync/backfill/performance`
- `POST /api/sync/backfill/extended`

接口行为：

- 立即返回 `202 Accepted`
- 由 Celery Worker 异步执行
- 避免经过 1Panel / 反向代理时因长任务导致 `504 Gateway Timeout`

当前历史回补调度：

- 每天 `02:10` 回补最近 `30` 天主快照历史
- 每天 `02:30` 回补最近 `30` 天细粒度明细历史

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
