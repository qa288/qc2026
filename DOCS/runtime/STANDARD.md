# Runtime Standard

版本：`v2.0`  
状态：`生效中`  
最后更新：`2026-03-22`

## 1. 文档定位

本文档定义当前试运行实现的运行约束。  
正式产品决策以 `DOCS/standard/` 为准；当前文档用于约束：

- 现网代码结构
- 运行链路
- 同步与降级规则
- 通知桥接
- token 读写策略

## 2. 当前运行事实

- 当前正式运行栈：`FastAPI + PostgreSQL + Redis + Celery + Celery Beat + Docker Compose`
- 当前前端形态：`Jinja2 + 原生 JS/CSS`
- 当前站点运维入口：`1Panel`
- 当前主入口域名：`qc.tyos.cc`
- 当前主机：`119.45.193.138`
- 当前服务角色：
  - `web`
  - `worker`
  - `scheduler`
  - `postgres`
  - `redis`

## 3. 代码与部署边界

当前运行目录的核心职责：

- `report_qianchuan.py`
  - 官方接口共享客户端与核心采集逻辑
- `dashboard/main.py`
  - 页面服务、内部 API、落库查询接口
- `dashboard/tasks.py`
  - Celery 任务入口
- `dashboard/celery_app.py`
  - Celery 与 Beat 调度配置
- `bridge_send_alerts.py`
  - 阈值告警桥接到 OpenClaw 通知渠道
- `docker-compose.dashboard.yml`
  - 现网编排基线

禁止事项：

- 不允许切回浏览器抓取、Cookie、`/nbs/api/*`
- 不允许把正式业务调度放回 Web 进程
- 不允许多实例独立刷新同一套 `refresh_token`
- 不允许为了新功能再开一套平行页面或平行采集系统

## 4. 同步与调度规则

当前周期任务统一由 Celery Beat 发起：

- `dashboard.sync`
  - 每 `1` 分钟
  - 负责主快照
- `dashboard.detail_sync`
  - 默认每 `10` 分钟
  - 负责计划详情、商品、素材、视频首发标记
- `dashboard.dispatch_alerts`
  - 每 `1` 分钟
  - 负责阈值告警发送

要求：

- Web 只提供页面与 API，不承担正式业务调度
- Worker 负责调用官方接口、聚合、落库和发送任务
- 单账户或单计划失败不能阻断整批任务

## 5. 通知规则

当前第一阶段只保留：

- 阈值告警

当前已纳入规则对象：

- 账户
- 计划
- 账户余额
- 共享钱包
- 爆单计划

当前通知链路：

- 系统 -> `bridge_send_alerts.py` -> `openclaw message send` -> 已配置 channel

当前不纳入运行基线：

- 定时简报
- 日报 / 周报
- 多通道并发通知策略

## 6. Token 规则

- 逻辑真源：PostgreSQL `oauth_tokens`
- 缓存副本：`/app/data/qianchuan_latest_token.json`
- 刷新锁：Redis
- 对外读取接口：`GET /api/system/integrations/ocean-engine/token-latest`

强约束：

- 只允许一个刷新任务写 token
- 其它服务器只能读取主服务最新 token
- 刷新成功后必须立即覆盖旧 `refresh_token`

## 7. 数据口径与降级

### 7.1 账户汇总

- 优先调用官方账户汇总接口
- 若返回 `50000` 或持续异常
- 自动降级为计划聚合账户汇总

要求：

- 必须保留来源标记
- 不得把降级结果伪装成官方原始值

### 7.2 聚合规则

可直接累加：

- 消耗
- 支付金额
- 订单数

必须重算：

- ROI

ROI 规则：

```text
总支付金额 / 总消耗
```

### 7.2A 余额与共享钱包

- 余额主来源统一使用 `account/fund/get`
- 共享钱包关系通过 `wallet_id` 聚合推导
- 不依赖高权限共享钱包接口作为 V1 主链路
- 当前分钟级落库表：
  - `account_balances`
  - `shared_wallets`
  - `shared_wallet_account_relations`

### 7.3 计划金额单位

当前 `qianchuan/uni_promotion/list` 的计划层金额展示规则：

```text
原始值 / 100000
```

新增金额字段前必须先校验单位。

## 8. 数据能力扩展规则

新增数据前，必须先走能力发现流程：

1. 查 [QIANCHUAN_CAPABILITY_CATALOG.md](./capabilities/QIANCHUAN_CAPABILITY_CATALOG.md)
2. 必要时跑 [DISCOVERY_RUNBOOK.md](./capabilities/DISCOVERY_RUNBOOK.md)
3. 确认主题、维度、指标、过滤条件
4. 再实现页面、聚合或告警

禁止直接猜接口。

## 9. 页面与体验硬约束

必须长期保持：

- 登录保护
- 根路径公开归属人榜
- 桌面优先布局
- 表格排序和筛选记忆
- 时间段筛选：`日 / 昨日 / 近7天 / 近30天 / 指定日期范围`
- 账户 / 计划 / 商品 / 员工 / 素材可查
- 未配置归属规则时允许临时回退到主播字段兜底；一旦配置归属人后，公开页只展示正式归属人结果
- 归属规则页必须包含：
  - 归属人列表
  - 关键词规则
  - 命中预览
  - 人工绑定
  - 未归属池
  - 未归属池覆盖 `账户 / 计划 / 商品 / 素材`
- 阈值告警规则维护页
- 预警中心保留模板式建规则入口
- 历史快照保留

## 10. 文档更新规则

任何影响以下内容的改动，都必须同步更新文档：

- 数据来源
- 页面行为
- 调度节奏
- token 读写方式
- 通知方式
- 口径和降级策略

最少更新：

- `README.md`
- `STANDARD.md`
- `FUNCTIONAL_SPEC.md`
