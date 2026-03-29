# 巨量千川全域投放官方接口对接文档

版本：`v1.0`
状态：`可实施`
最后核验时间：`2026-03-13`
适用场景：从纵横工作台账号出发，拉取其下全部千川子账户的账户汇总、计划列表、计划详情和计划级统计，并在自有系统中汇总成工作台总表。
文档角色：背景设计与选型说明；规范真源以 [runtime/capabilities/QIANCHUAN_OFFICIAL_API_STANDARD.md](../runtime/capabilities/QIANCHUAN_OFFICIAL_API_STANDARD.md) 为准。

## 1. 目标

本文档定义一套只依赖巨量开放平台公开接口的标准实现方案，用于替代浏览器登录态加内部接口的非正式抓取方式。

目标包括：

- 从纵横工作台账号获取全部千川子账户。
- 获取每个子账户的全域投放账户维度数据。
- 获取每个子账户的全域投放计划列表。
- 获取单计划详情。
- 生成工作台层级的总表、子账户表、计划表。
- 支持近 7 天、30 天、180 天的稳定查询和周期刷新。
- 提供可落库、可重试、可对账、可扩展的标准实现。

## 2. 非目标

本文档不把以下方式作为生产主链路：

- 浏览器内部接口，如 `business.oceanengine.com` 下的 `/nbs/api/bm/promotion/ecp/*`
- 依赖 Cookie、`csrftoken`、页面登录态的抓取逻辑
- 旧版千川报表接口作为主方案

这些方式可以用于人工核验，但不进入正式生产方案。

## 3. 关键结论

### 3.1 可以实现的数据范围

通过官方公开接口，可以稳定拿到以下数据：

- 工作台下全部千川子账户列表
- 子账户的账户维度汇总指标
- 子账户下的全域投放计划列表
- 单计划详情
- 计划级统计
- 商品、素材、标题等自定义维度报表

### 3.2 正确的官方接口族

本场景应优先使用 `uni_promotion` 相关接口，而不是旧的 `qianchuan/report/advertiser/get` 或 `qianchuan/report/ad/get`。

### 3.3 账号模型必须分层

`1802375893828620` 这类账号是纵横工作台账号，不是直接投放账户。
正式实现时必须：

1. 先查询工作台账号下的子账户。
2. 再对子账户逐个查数。
3. 最后由自有系统汇总为工作台总表。

### 3.4 内部接口不作为正式方案

虽然页面内部接口目前可用，但它们不属于开放平台公开文档能力，没有稳定性承诺。后续改版、字段调整、限流、风控、权限收紧都属于高风险事件。

## 4. 术语定义

### 4.1 开发者应用

指你在巨量开放平台创建的应用，持有：

- `app_id`
- `app_secret`

### 4.2 授权账户

指通过 OAuth 授权给你的应用的账户。授权完成后，你可以获取：

- `access_token`
- `refresh_token`

### 4.3 纵横工作台账号

也可理解为客户中心或工作台级账号。
它是账户树入口，但不能直接作为全域投放报表查询主体。

### 4.4 千川子账户

纵横工作台下面实际投放的千川账户。
所有全域投放报表、计划列表、计划详情，都应以子账户 `advertiser_id` 为查询主体。

### 4.5 全域投放

本文中的“全域投放”对应官方 `uni_promotion` 能力和 ROI2 指标体系。

## 5. 接入前提

### 5.1 应用类型

应用必须选择 `千川PC版`。
不建议使用 `仅千川随心推`，因为本文档面向的是工作台、千川子账户、全域投放、ROI2、计划列表等 PC 端能力。

### 5.2 授权方式

标准流程如下：

1. 你使用自己的开发者账号创建应用。
2. 被查询方授权你的应用。
3. 你用自己的 `app_id + app_secret + auth_code` 换取 `access_token`。
4. 再用 `access_token` 查询授权账户及其数据。

### 5.3 权限范围

正式接入前，需要确认应用具备以下能力对应的权限：

- 获取已授权账户
- 获取纵横工作台下账户列表
- 获取全域投放账户维度数据
- 获取全域投放列表
- 获取全域投放计划详情
- 获取全域数据配置和明细

## 6. 官方接口选型

### 6.1 主链路接口

| 目的 | 接口 | 说明 |
|---|---|---|
| 获取 Access Token | `POST /open_api/oauth2/access_token/` | 用 `auth_code` 换 token |
| 获取已授权账户 | `GET /open_api/oauth2/advertiser/get/` | 获取当前 token 可访问的授权账户 |
| 获取工作台下子账户 | `GET /open_api/2/customer_center/advertiser/list/` | 从工作台账号展开子账户 |
| 获取账户维度汇总 | `GET /open_api/v1.0/qianchuan/report/uni_promotion/get/` | 获取子账户全域汇总指标 |
| 获取全域投放列表 | `GET /open_api/v1.0/qianchuan/uni_promotion/list/` | 获取子账户下计划列表及统计 |
| 获取全域投放计划详情 | `GET /open_api/v1.0/qianchuan/uni_promotion/ad/detail/` | 获取单计划详情 |
| 获取全域数据配置 | `GET /open_api/v1.0/qianchuan/report/uni_promotion/config/get/` | 查询可用维度和指标 |
| 获取全域明细数据 | `GET /open_api/v1.0/qianchuan/report/uni_promotion/data/get/` | 查询计划/商品/素材等明细数据 |

### 6.2 不作为主链路的旧接口

| 接口 | 结论 |
|---|---|
| `GET /open_api/v1.0/qianchuan/ad/get/` | 不作为全域投放主方案 |
| `GET /open_api/v1.0/qianchuan/report/ad/get/` | 不作为全域投放主方案 |
| `GET /open_api/v1.0/qianchuan/report/advertiser/get/` | 不作为全域投放主方案 |

原因：

- 旧接口口径与当前页面的全域投放 ROI2 口径不一致。
- 实测中旧接口在当前场景下返回为空或无法覆盖需要的页面数据。

## 7. 整体实现架构

推荐架构如下：

1. `OAuth 服务`
2. `账户树同步任务`
3. `账户汇总同步任务`
4. `计划列表同步任务`
5. `计划详情同步任务`
6. `汇总计算服务`
7. `对账与监控服务`
8. `数据存储层`

逻辑顺序如下：

```text
授权 -> Access Token -> 已授权账户 -> 工作台账号 -> 子账户列表
     -> 子账户账户汇总
     -> 子账户计划列表
     -> 单计划详情
     -> 自有系统汇总
     -> 工作台总表/子账户表/计划表
```

## 8. 标准查询链路

### 8.1 第一步：获取 Token

输入：

- `app_id`
- `app_secret`
- `grant_type=auth_code`
- `auth_code`

输出：

- `access_token`
- `refresh_token`
- `expires_in`

标准要求：

- `auth_code` 为一次性、短时有效参数，收到后应立即交换。
- 必须持久化 `access_token` 和 `refresh_token`。
- 需要实现 token 刷新机制。

### 8.2 第二步：获取已授权账户

目的：

- 确认当前 token 关联的授权账户。
- 确认目标工作台账号是否已被授权。

输出建议保留：

- 授权账户 ID
- 授权关系快照时间
- 权限范围

### 8.3 第三步：展开工作台下子账户

接口：`customer_center/advertiser/list`

输入：

- 工作台账号 ID

输出：

- 子账户 `advertiser_id`
- 账户名称
- 状态
- 分页信息

标准要求：

- 全量拉完所有分页。
- 将工作台账号与子账户关系落库。
- 每日同步一次，识别新增账户、失效账户和名称变更。

### 8.4 第四步：查询子账户账户汇总

接口：`report/uni_promotion/get`

输入：

- `advertiser_id`
- `start_date`
- `end_date`
- `marketing_goal`
- `order_platform`
- `fields`

输出：

- 账户层级的全域汇总指标

标准要求：

- 工作台层总数据必须通过子账户汇总得到，不能直接对工作台账号发起该接口。
- 默认查询口径建议：
  - `marketing_goal=ALL`
  - `order_platform=QIANCHUAN`

### 8.5 第五步：查询子账户计划列表

接口：`uni_promotion/list`

输入：

- `advertiser_id`
- `start_time`
- `end_time`
- `marketing_goal`
- `fields`
- `page`
- `page_size`

输出：

- `ad_list`
- `page_info`

每条计划可包含：

- 计划基本信息
- 商品信息
- 抖音号或直播间信息
- 统计字段

标准要求：

- 全量分页拉取。
- 计划列表是正式“计划表”的主数据来源。
- 计划层指标优先取 `stats_info`。

### 8.6 第六步：查询单计划详情

接口：`uni_promotion/ad/detail`

输入：

- `advertiser_id`
- `ad_id`

输出：

- 计划完整配置
- 出价、预算、时间、商品、素材、抖音号等信息

标准要求：

- 新计划首次发现时拉取一次详情。
- 若计划 `modify_time` 变化，再重新拉取。
- 不建议每次全量重复拉详情。

### 8.7 第七步：按需查询明细报表

接口：

- `report/uni_promotion/config/get`
- `report/uni_promotion/data/get`

用途：

- 获取可用维度和指标
- 获取计划、商品、素材、标题、图文、视频等更细粒度报表

标准要求：

- 每次先调用 `config/get`，确认当前主题可用字段。
- 再按返回的维度、指标组合构造 `data/get`。
- 不建议把字段集永久硬编码。

## 9. 标准参数规范

### 9.1 时间参数

账户汇总接口使用：

- `start_date`
- `end_date`

计划列表接口使用：

- `start_time`
- `end_time`

统一格式：

- `YYYY-MM-DD HH:mm:ss`

统一规则：

- 日级查询起始时间统一为 `00:00:00`
- 日级查询结束时间统一为 `23:59:59`

示例：

- 最近一周：`2026-03-07 00:00:00` 到 `2026-03-13 23:59:59`

### 9.2 时间范围限制

官方限制需遵守：

- 单次最大查询跨度为 `180` 天
- 小时维度最大为 `7` 天

实现要求：

- 后端对输入时间范围做强校验
- 超过限制时自动拆段

### 9.3 默认查询口径

账户汇总默认值：

- `marketing_goal=ALL`
- `order_platform=QIANCHUAN`

计划列表默认值：

- `marketing_goal=VIDEO_PROM_GOODS` 或按业务需要拆查

说明：

- 账户汇总实测中，`marketing_goal=ALL` 的稳定性优于部分更细粒度组合。
- 若业务必须拆直播全域和商品全域，建议以子任务形式分别查询，再在系统层汇总。

## 10. 页面指标与官方字段映射

以下是当前常用页面指标与官方字段的标准映射关系：

| 页面指标 | 官方字段 |
|---|---|
| 整体消耗 | `stat_cost` |
| 整体支付 ROI | `total_prepay_and_pay_order_roi2` |
| 整体成交订单数 | `total_pay_order_count_for_roi2` |
| 整体成交订单成本 | `total_cost_per_pay_order_for_roi2` |
| 用户实际支付金额 | `total_pay_order_gmv_for_roi2` |
| 整体成交金额 | `total_pay_order_gmv_include_coupon_for_roi2` |
| 平台补贴金额 | `total_ecom_platform_subsidy_amount_for_roi2` |
| 1 小时结算金额 | `total_order_settle_amount_for_roi2_1h` |
| 1 小时结算 ROI | `total_prepay_and_pay_settle_roi2_1h` |
| 1 小时退款金额 | `total_refund_order_gmv_for_roi2_1h_all` |
| 1 小时退款率 | `total_refund_order_gmv_for_roi2_1h_rate` |

## 11. 推荐查询字段

### 11.1 账户汇总字段

第一批核心字段：

- `stat_cost`
- `total_prepay_and_pay_order_roi2`
- `total_pay_order_count_for_roi2`
- `total_pay_order_gmv_for_roi2`
- `total_pay_order_gmv_include_coupon_for_roi2`
- `total_ecom_platform_subsidy_amount_for_roi2`

第二批扩展字段：

- `total_cost_per_pay_order_for_roi2`
- `total_order_settle_amount_for_roi2_1h`
- `total_prepay_and_pay_settle_roi2_1h`
- `total_refund_order_gmv_for_roi2_1h_all`
- `total_refund_order_gmv_for_roi2_1h_rate`
- `total_order_settle_count_for_roi2_1h`

### 11.2 计划列表字段

建议最小字段集包含：

- 计划 ID
- 计划名称
- 投放状态
- 操作状态
- 预算
- 预算模式
- ROI 目标
- 投放方式
- 营销目标
- 商品信息
- 抖音号或直播间信息
- 计划统计字段

### 11.3 自定义明细字段

通过 `config/get` 动态获取：

- 可用维度
- 可用指标
- 互斥关系
- 排序能力
- 时间范围限制

## 12. 汇总口径规则

### 12.1 可直接求和的字段

以下字段可在子账户层直接累加：

- `stat_cost`
- `total_pay_order_count_for_roi2`
- `total_pay_order_gmv_for_roi2`
- `total_pay_order_gmv_include_coupon_for_roi2`
- `total_ecom_platform_subsidy_amount_for_roi2`
- `total_order_settle_amount_for_roi2_1h`
- `total_refund_order_gmv_for_roi2_1h_all`

### 12.2 禁止直接平均的字段

以下字段不能直接取账户平均值：

- `total_prepay_and_pay_order_roi2`
- `total_cost_per_pay_order_for_roi2`
- `total_prepay_and_pay_settle_roi2_1h`
- `total_refund_order_gmv_for_roi2_1h_rate`

### 12.3 派生指标重算公式

工作台总支付 ROI：

```text
sum(整体成交金额) / sum(整体消耗)
```

工作台整体成交订单成本：

```text
sum(整体消耗) / sum(整体成交订单数)
```

工作台 1 小时结算 ROI：

```text
sum(1小时结算金额) / sum(整体消耗)
```

工作台 1 小时退款率：

```text
sum(1小时退款金额) / sum(整体成交金额)
```

### 12.4 除零处理

若分母为 `0`：

- 返回 `0`
- 同时记录除零标记或警告日志

## 13. 金额单位规范

### 13.1 账户汇总接口

实测中，`report/uni_promotion/get` 返回的金额字段可直接按元值使用。

### 13.2 计划列表接口

实测中，`uni_promotion/list` 的 `stats_info` 中部分金额字段表现为原始整型值，不能默认直接展示。

因此生产实现要求如下：

- 账户总表口径以 `report/uni_promotion/get` 为准。
- 计划层金额要先做归一化校验，再作为展示值使用。
- 首次接入时需进行页面与接口对比，确认金额缩放比例。
- 原始返回必须保留 `raw_json`，便于回溯。

说明：

- “计划列表金额需要归一化校验”是基于 `2026-03-13` 的实测现象得到的实现要求。
- 在正式上线前，必须用样本计划完成一次单位核对。

## 14. 数据存储设计

建议至少建立以下数据表。

### 14.1 `oauth_authorization`

建议字段：

- `app_id`
- `authorized_uid`
- `access_token`
- `refresh_token`
- `token_expire_time`
- `scope_json`
- `authorized_at`
- `updated_at`

### 14.2 `customer_center_account`

建议字段：

- `customer_center_id`
- `advertiser_id`
- `advertiser_name`
- `account_status`
- `snapshot_time`
- `raw_json`

唯一键建议：

```text
customer_center_id + advertiser_id + snapshot_time
```

### 14.3 `uni_account_summary`

建议字段：

- `customer_center_id`
- `advertiser_id`
- `stat_start_time`
- `stat_end_time`
- `marketing_goal`
- `order_platform`
- 原子指标字段
- 派生指标字段
- `request_id`
- `raw_json`
- `snapshot_time`

唯一键建议：

```text
advertiser_id + stat_start_time + stat_end_time + marketing_goal + order_platform
```

### 14.4 `uni_plan_summary`

建议字段：

- `advertiser_id`
- `ad_id`
- `stat_start_time`
- `stat_end_time`
- `name`
- `status`
- `opt_status`
- `budget`
- `budget_mode`
- `roi2_goal`
- `smart_bid_type`
- `marketing_goal`
- `product_info_json`
- `room_info_json`
- 统计字段
- `request_id`
- `raw_json`
- `snapshot_time`

唯一键建议：

```text
advertiser_id + ad_id + stat_start_time + stat_end_time
```

### 14.5 `uni_plan_detail_latest`

建议字段：

- `advertiser_id`
- `ad_id`
- `modify_time`
- `detail_snapshot_time`
- `raw_json`

唯一键建议：

```text
advertiser_id + ad_id
```

## 15. 任务调度设计

### 15.1 账户树同步任务

频率：

- 每天 1 次

职责：

- 拉取工作台下全部子账户
- 检测新增账户
- 检测失效账户
- 检测名称变更

### 15.2 账户汇总同步任务

频率建议：

- 每小时刷新当天数据
- 每日重刷最近 7 天
- 每周重刷最近 30 天

原因：

- 结算、退款、补贴类指标存在回刷
- 单次当天抓取不足以保证最终口径稳定

### 15.3 计划列表同步任务

频率建议：

- 每小时同步当天涉及的计划列表
- 每日重刷最近 7 天

职责：

- 同步新增计划
- 同步状态变化
- 同步计划层统计

### 15.4 计划详情同步任务

触发条件：

- 新计划出现
- `modify_time` 变化

职责：

- 拉取计划完整配置
- 更新最新详情快照

## 16. 错误处理与重试策略

### 16.1 HTTP 层

建议配置：

- 超时：`10s` 到 `20s`
- 最大重试次数：`3`
- 退避策略：`1s -> 2s -> 4s`

### 16.2 业务错误码处理

`50000`：

- 按服务端临时错误处理
- 允许重试

`40000`：

- 视为参数错误
- 不重试
- 记录请求参数并告警

Token 失效类错误：

- 先刷新 token
- 再重试一次

`role is wrong`：

- 视为调用主体错误
- 说明使用了工作台账号而不是子账户
- 不重试，直接修正调用逻辑

### 16.3 字段拆批策略

若 `report/uni_promotion/get` 在大字段组合下出现 `50000`，建议拆批查询：

批次 A：

- `stat_cost`
- `total_prepay_and_pay_order_roi2`
- `total_pay_order_count_for_roi2`

批次 B：

- `total_pay_order_gmv_for_roi2`
- `total_pay_order_gmv_include_coupon_for_roi2`
- `total_ecom_platform_subsidy_amount_for_roi2`

批次 C：

- 结算与退款相关字段

最后在系统层合并结果。

## 17. 对账与验收标准

### 17.1 对账顺序

对账必须按以下顺序进行：

1. 单个子账户对账
2. 多个子账户汇总对账
3. 工作台总表对账

### 17.2 重点对账字段

优先对以下字段：

- 整体消耗
- 整体支付 ROI
- 整体成交订单数
- 用户实际支付金额
- 整体成交金额

### 17.3 可接受差异来源

若存在差异，优先检查：

- 页面口径与开放平台口径差异
- 查询时间边界是否一致
- 是否错误使用工作台账号代替子账户
- 是否将 `marketing_goal` 配置为不同值
- 计划列表金额是否完成归一化
- 是否错误平均了 ROI 或退款率

### 17.4 验收建议

建议以以下标准作为上线前验收：

- 核心金额字段差异不超过 `1%`
- 订单数字段差异不超过 `1%`
- ROI 差异若超阈值，必须从分子分母层复核

## 18. 安全与合规要求

### 18.1 密钥管理

必须安全存储：

- `app_secret`
- `access_token`
- `refresh_token`

要求：

- 不写入前端
- 不出现在日志明文中
- 不硬编码到代码仓库

### 18.2 接口访问

要求：

- 所有接口必须由服务端发起
- 不允许浏览器端直接持有开放平台敏感凭据

### 18.3 原始返回留存

建议在数据库或对象存储中保留：

- 原始接口响应
- 请求参数快照
- `request_id`

目的：

- 方便后续排错
- 方便与官方工单沟通

## 19. 内部接口的正式定位

当前页面实际使用过的内部接口包括：

- `/nbs/api/bm/promotion/ecp/get_roi2_account_list`
- `/nbs/api/bm/promotion/ecp/get_roi2_ad_list`

生产定位要求：

- 仅用于人工对账
- 仅用于问题排查
- 不纳入正式主流程

原因如下：

- 依赖浏览器登录态
- 依赖 Cookie 和 `csrftoken`
- 不在公开开放平台文档中
- 没有版本和稳定性承诺

## 20. 实测结论记录

以下为 `2026-03-13` 的实测结论，用于指导实现优先级：

### 20.1 已验证可用

- `customer_center/advertiser/list` 能成功返回工作台下子账户列表
- `report/uni_promotion/config/get` 能成功返回 ROI2 相关指标集合
- `report/uni_promotion/get` 能成功返回子账户账户汇总核心字段
- `uni_promotion/list` 能成功返回计划列表和计划层统计
- `uni_promotion/ad/detail` 能成功返回单计划详情

### 20.2 已验证不建议作为主方案

- `qianchuan/ad/get` 在当前场景下未返回需要的全域投放计划列表
- `qianchuan/report/ad/get` 在当前场景下未返回需要的计划报表数据

### 20.3 实现层特别注意

- `report/uni_promotion/get` 对部分参数组合可能返回 `50000`，应采用稳定参数和拆批策略
- 账户汇总查询建议优先使用 `marketing_goal=ALL`
- 工作台账号不能直接用作全域汇总查询主体

## 21. 推荐的第一版落地范围

第一版建议只做以下能力：

### 21.1 必做

- OAuth 授权和 token 刷新
- 工作台下子账户同步
- 子账户账户汇总同步
- 子账户计划列表同步
- 工作台总表汇总计算
- 基础对账页

### 21.2 第二阶段

- 单计划详情同步
- 商品、素材、标题等明细报表
- 趋势分析
- 监控与告警

## 22. 交付标准

开发完成后，应至少满足以下交付标准：

- 输入工作台账号，能拿到全部子账户
- 输入时间范围，能返回全部子账户账户汇总
- 能返回全部计划列表
- 能按工作台维度汇总生成总表
- 对 `request_id`、原始返回、错误码有完整记录
- 能支持重试、回刷、对账

## 23. 参考文档

- 获取 Access Token
  <https://open.oceanengine.com/labels/12/docs/1697468230144003>

- 获取已授权的账户
  <https://open.oceanengine.com/labels/12/docs/1697467748096067>

- 获取纵横工作台下账户列表
  <https://open.oceanengine.com/labels/12/docs/1796368918556803>

- 获取全域投放账户维度数据
  <https://open.oceanengine.com/labels/12/docs/1770675169146947>

- 获取全域投放列表
  <https://open.oceanengine.com/labels/12/docs/1771195810853899>

- 获取全域投放计划详情
  <https://open.oceanengine.com/labels/12/docs/1804362305657868>

- 获取全域数据-可用维度和指标
  <https://open.oceanengine.com/labels/12/docs/1823296280645708>

- 获取全域数据
  <https://open.oceanengine.com/labels/12/docs/1823297941140569>
