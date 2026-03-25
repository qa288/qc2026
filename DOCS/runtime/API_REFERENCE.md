# Runtime API Reference

版本：`v2.0`  
状态：`生效中`  
最后更新：`2026-03-25`

## 1. 文档定位

本文档面向当前这套线上运行系统的前后端联调、接口接入和同事参考开发。  
这里只记录“现在实际可调用”的接口，不替代 `DOCS/standard/05_内部接口与集成规范.md` 的长期规范。

当前运行基线：

- 主入口域名：`https://qc.tyos.cc`
- 页面服务：`FastAPI`
- 鉴权方式：`Session Cookie`
- 页面与接口共用同一站点

## 2. 通用规则

### 2.1 鉴权

- `GET /login`
  - 返回登录页
- `POST /login`
  - 表单登录
  - 成功后写入 Session，并 `302` 跳转 `/`
- `POST /logout`
  - 清空 Session，并 `302` 跳转 `/login`

除 `login/logout/healthz/readyz` 外，其余接口都要求已登录。

### 2.2 角色

- `admin`
  - 全量数据
  - 可维护账号、关键词、规则、通知、手动同步、token
- `supervisor`
  - 仅查看分配账户范围
  - 如开启上传权限，可调用上传接口
- `operator`
  - 只看关键词命中的结果
  - 不可调用管理员接口

### 2.3 常见状态码

- `200`
  - 正常返回
- `202`
  - 异步任务已入队
- `400`
  - 业务校验失败或参数非法
- `401`
  - 未登录或 Session 失效
- `403`
  - 已登录，但无权限

### 2.4 通用时间参数

多数查询接口支持以下参数组合：

- `range`
  - `day | yesterday | week | month | custom`
- `start_date`
  - `YYYY-MM-DD`
- `end_date`
  - `YYYY-MM-DD`

当 `range=custom` 时，应同时传 `start_date` 和 `end_date`。

## 3. 页面与会话接口

### `GET /healthz`

- 作用：进程存活检查
- 权限：无

示例返回：

```json
{"status":"ok"}
```

### `GET /readyz`

- 作用：数据库、Redis、Celery、schema 版本就绪检查
- 权限：无

### `GET /api/session/me`

- 作用：读取当前登录账号和权限能力
- 权限：任意登录账号

核心返回字段：

- `id`
- `username`
- `role`
- `display_name`
- `upload_materials_enabled`
- `can_upload_materials`
- `scope_type`
- `scope_count`

### `GET /api/dashboard`

- 作用：工作台首页初始化主接口
- 权限：任意登录账号

核心返回字段：

- `session`
- `latest`
- `extendedSync`
- `tokenInfo`
  - 仅管理员返回
- `summaryHistory`
- `notificationSettings`
  - 仅管理员返回
- `alertRules`
  - 仅管理员返回
- `alertEvents`
  - 仅管理员返回
- `timezone`

`latest` 结构内当前包含：

- `summary`
- `accounts`
- `plans`
- `accountBalances`
- `sharedWallets`
- `walletRelations`
- `products`
- `employees`
- `operators`

### `GET /api/performance`

- 作用：按时间范围读取账户/计划/汇总快照
- 权限：任意登录账号
- 查询参数：
  - `range`
  - `start_date`
  - `end_date`

### `GET /api/material-rankings`

- 作用：读取素材榜
- 权限：任意登录账号
- 查询参数：
  - `snapshot_time`
  - `range`
  - `start_date`
  - `end_date`

### `GET /api/catalog/accounts`

- 作用：读取当前可见账户目录
- 权限：任意登录账号

示例返回：

```json
{
  "items": [
    {
      "advertiser_id": 1848456681117724,
      "advertiser_name": "见山-1 一奕"
    }
  ]
}
```

### `GET /api/accounts/{advertiser_id}/history`

- 作用：读取单账户历史曲线
- 权限：`admin | supervisor`

### `GET /api/plans/{ad_id}/history`

- 作用：读取单计划历史曲线
- 权限：`admin | supervisor`

### `GET /api/plans/{ad_id}/assets`

- 作用：读取计划最近一次明细资产
- 权限：`admin | supervisor`

返回内容当前可能包含：

- `plan`
- `detail`
- `products`
- `materials`
- `originalVideos`

### `GET /api/operator-rankings`

- 作用：读取运营维度排名
- 权限：任意登录账号
- 查询参数：
  - `range`
  - `start_date`
  - `end_date`
  - `sort_key`
  - `sort_dir`

### `GET /api/unassigned-candidates`

- 作用：读取未归属候选对象
- 权限：仅管理员
- 查询参数：
  - `range`
  - `start_date`
  - `end_date`
  - `scope`
    - `all | account | plan | product | material`

## 4. 上传接口

### `GET /api/upload/targets`

- 作用：按目标搜索可上传计划
- 权限：管理员或已开启上传权限的主管
- 查询参数：
  - `scope`
    - 当前默认 `plan`
  - `q`

### `GET /api/upload/jobs`

- 作用：读取上传任务列表
- 权限：管理员或已开启上传权限的主管

### `POST /api/upload/jobs`

- 作用：创建上传任务并入队
- 权限：管理员或已开启上传权限的主管
- Content-Type：`multipart/form-data`

表单字段：

- `scope`
- `query_text`
- `target_plan_ids`
  - JSON 字符串，例如 `[1859150347498163,1852193703480651]`
- `files`
  - 多文件上传

成功返回 `202`，核心字段包括：

- `id`
- `task_id`
- `queued`
- `note`

## 5. 账号与权限接口

### 用户管理

仅管理员可调用。

- `GET /api/users`
- `POST /api/users`
- `PUT /api/users/{user_id}`
- `GET /api/users/{user_id}/account-scopes`
- `PUT /api/users/{user_id}/account-scopes`
- `GET /api/users/{user_id}/keywords`
- `POST /api/users/{user_id}/keywords`
- `DELETE /api/user-keywords/{keyword_id}`
- `GET /api/users/{user_id}/matched-materials`

`POST/PUT /api/users` 请求体：

```json
{
  "username": "operator_a",
  "password": "new-password",
  "role": "operator",
  "display_name": "运营A",
  "enabled": true,
  "upload_materials_enabled": false
}
```

字段说明：

- `username`
  - 3 到 60 位
  - 仅允许 `A-Za-z0-9_.-`
- `password`
  - 更新时可留空表示不修改
- `role`
  - `admin | supervisor | operator`

`PUT /api/users/{user_id}/account-scopes` 请求体：

```json
{
  "advertiser_ids": [1848456681117724, 1848018583664264]
}
```

`POST /api/users/{user_id}/keywords` 请求体：

```json
{
  "keyword": "一奕科技",
  "enabled": true
}
```

`GET /api/users/{user_id}/matched-materials` 查询参数：

- `range`
- `start_date`
- `end_date`
- `q`

### 归属人管理

仅管理员可调用。

- `GET /api/employees`
- `POST /api/employees`
- `PUT /api/employees/{employee_id}`
- `GET /api/employees/{employee_id}/keywords`
- `POST /api/employees/{employee_id}/keywords`
- `PUT /api/employee-keywords/{keyword_id}`
- `DELETE /api/employee-keywords/{keyword_id}`
- `GET /api/employees/{employee_id}/bindings`
- `POST /api/employees/{employee_id}/bindings`
- `DELETE /api/employee-bindings/{binding_id}`
- `GET /api/employee-match-preview`

`POST/PUT /api/employees` 请求体：

```json
{
  "display_name": "运营A",
  "note": "负责车品素材",
  "enabled": true
}
```

`POST/PUT employee keyword` 请求体：

```json
{
  "keyword": "一奕科技",
  "scope": "material",
  "priority": 100,
  "enabled": true
}
```

`scope` 可选值：

- `all`
- `account`
- `plan`
- `product`
- `material`

`POST /api/employees/{employee_id}/bindings` 请求体：

```json
{
  "object_type": "material",
  "object_key": "video:123456",
  "object_label": "素材示例",
  "note": "手工绑定"
}
```

`GET /api/employee-match-preview` 查询参数：

- `keyword`
- `scope`

## 6. 告警接口

仅管理员可调用。

- `GET /api/alert-rules`
- `POST /api/alert-rules`
- `PUT /api/alert-rules/{rule_id}`
- `DELETE /api/alert-rules/{rule_id}`
- `GET /api/notification-settings`
- `PUT /api/notification-settings`

`POST/PUT /api/alert-rules` 请求体：

```json
{
  "entity_type": "plan",
  "metric": "roi",
  "operator": "lt",
  "threshold": 1.2,
  "min_spend": 300,
  "cooldown_minutes": 60,
  "enabled": true,
  "target_id": "",
  "note": "低 ROI 计划提醒"
}
```

当前支持的 `entity_type`：

- `account`
- `plan`
- `account_balance`
- `shared_wallet`
- `burst_plan`

当前支持的 `metric`：

- `stat_cost`
- `roi`
- `order_count`
- `pay_amount`
- `account_balance`
- `wallet_balance`
- `burst_order_count`

`PUT /api/notification-settings` 请求体：

```json
{
  "enabled": false,
  "channel": "feishu",
  "account": "default",
  "target": "",
  "alert_enabled": false,
  "alert_batch_size": 6,
  "summary_enabled": false,
  "summary_times": "",
  "summary_account_limit": 6,
  "summary_plan_limit": 10
}
```

## 7. 系统与同步接口

仅管理员可调用。

- `POST /api/sync`
  - 手动触发主同步
- `POST /api/sync/extended`
  - 手动触发细粒度同步
- `POST /api/sync/backfill/performance`
  - 手动触发主快照回补
- `POST /api/sync/backfill/extended`
  - 手动触发细粒度回补
- `GET /api/system/integrations/ocean-engine/token-latest`
  - 读取最新 token
- `POST /api/system/integrations/ocean-engine/exchange-auth-code`
  - 用 `auth_code` 换新 token

回补接口查询参数：

- `days`
  - 默认 `30`

成功返回示例：

```json
{
  "ok": true,
  "queued": true,
  "task_id": "3df8b0f7-8b5d-4fd1-84f1-0f9c6d2f4e6a",
  "task_name": "dashboard.performance_backfill",
  "days": 30
}
```

`POST /api/system/integrations/ocean-engine/exchange-auth-code` 请求体：

```json
{
  "auth_code": "xxxxxxxxxxxxxxxxxxxxxxxx"
}
```

## 8. 当前前端主依赖接口

当前首页和工作台初始化主要依赖这些接口：

- `GET /api/dashboard`
- `GET /api/performance`
- `GET /api/material-rankings`
- `GET /api/catalog/accounts`
- `GET /api/session/me`

如果页面“有壳但无数据”，优先检查这几个接口返回值与状态码。

## 9. 联调建议

- 先验证 `GET /healthz` 和 `GET /readyz`
- 再验证未登录访问业务接口是否返回 `401`
- 登录后先看 `GET /api/dashboard`
- 若跨日图表异常，再看 `GET /api/performance`
- 若素材页异常，再看 `GET /api/material-rankings`
- 若权限页异常，再看 `/api/users*`、`/api/employees*`

当前线上最近一次接口回归已确认：

- 未登录访问 `/api/dashboard` 返回 `401`
- 登录后 `/api/dashboard` 返回 `200`
- `/api/performance` 返回 `200`
- `/api/material-rankings` 返回 `200`
- `/api/catalog/accounts` 返回 `200`
