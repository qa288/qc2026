# Today 表现链统一到 `uni_promotion` 主链

## 目的

当前 `today` 的账户页和计划页存在混源：

- 账户页基础表现来自账户接口
- 净成交、退款、计划数又来自计划聚合
- 计划页还会被 `standard` / `uni_report` fallback 补位

这会导致：

- 同一页面内不同列来自不同官方口径
- 账户合计和计划合计不一定严格一致
- 分钟级热路径请求过多

本方案把 `today` 表现链统一到官方 `uni_promotion` 主链，只保留必要的独立资金链和按需 fallback。

## 字段分层

### A. 主链原始字段

这些字段必须来自官方主接口，不在本地猜测：

- `stat_cost`
- `pay_amount`
- `total_pay_amount`
- `settled_pay_amount`
- `order_count`
- `settled_order_count`
- `refund_amount_1h`
- `marketing_goal`
- `status`
- `opt_status`
- `roi_goal`
- `product_id`
- `product_name`
- `anchor_name`

主接口：

- 账户 today 主接口：`qianchuan/report/uni_promotion/get`
- 计划 today 主接口：`qianchuan/uni_promotion/list`

## B. 本地推导字段

这些字段可由原始字段统一推导，不再要求分钟级向上游重复请求：

- `roi = pay_amount / stat_cost`
- `settled_roi = settled_pay_amount / stat_cost`
- `pay_order_cost = stat_cost / order_count`
- `settled_amount_rate = settled_pay_amount / total_pay_amount`
- `refund_rate_1h = refund_amount_1h / total_pay_amount`

要求：

- 统一在后端读模型或聚合层推导
- 前端只展示，不再自己拼多套公式

## C. 独立资金链字段

以下字段不属于 `uni_promotion` 表现口径，必须保留独立资金接口：

- `account_balance`
- `available_balance`
- `wallet_id`
- `wallet_balance`
- `shared_wallet` 相关关系字段

独立接口：

- `account/fund/get`

说明：

- 页面层可以把资金字段与表现字段并排展示
- 采集层不能把资金链硬并进 `uni_promotion`

## D. Fallback 字段与接口

这些接口不能再作为 `today` 分钟级默认热路径，只保留成按需 fallback 或历史链路：

- `qianchuan/report/advertiser/get`
- `qianchuan/ad/get`
- `qianchuan/report/ad/get`
- `qianchuan/report/uni_promotion/data/get`

允许使用场景：

- 主接口失败
- 历史刷新
- 特定字段排障
- 单独的能力验证

不允许使用场景：

- `today` 默认分钟级表现采集
- 与主链表现值做平级求和
- 为了补齐少量元数据而再次混入口径

## 库表落地

today 主链统一后，账户聚合结果必须直接落到账户快照表，而不是只在前端二次拼装。

涉及表：

- `account_snapshots`
- `account_daily`
- `plan_snapshots`
- `plan_daily`

账户快照需要完整落以下 today 字段：

- `stat_cost`
- `pay_amount`
- `total_pay_amount`
- `settled_pay_amount`
- `order_count`
- `settled_order_count`
- `refund_amount_1h`
- `plan_count`
- `roi`
- `settled_roi`
- `pay_order_cost`
- `settled_amount_rate`
- `refund_rate_1h`
- `ok`
- `error`

要求：

- 账户行可直接由数据库读出并展示
- 前端只把计划聚合作为兼容 fallback，不再作为唯一来源
- daily 读模型与 minute 快照字段保持一致

## today 页面口径

### 计划页

- 直接读取 `uni_promotion/list` 结果
- 不再把 `standard` / `uni_report` 结果并进同一计划行

### 账户页

- 由同一批计划主链结果按 `advertiser_id` 聚合生成
- 不再依赖独立账户表现接口作为主展示来源

这样能保证：

- 账户合计 = 计划合计
- 账户页与计划页同口径
- today 快照只保留一套真源

## 投放类型识别限制

### 当前可稳定识别

从 `uni_promotion` 主链能稳定拿到：

- `marketing_goal = VIDEO_PROM_GOODS`
- `marketing_goal = LIVE_PROM_GOODS`

这足够区分：

- 商品全域推广
- 直播间全域推广

### 当前不能稳定识别

`uni_promotion/list` 与 `report/uni_promotion/get` 本身是全域投放接口。

当前代码里 `plan_delivery_type = CUBIC` 的来源，不是主链直接返回，而是：

- `report/uni_promotion/data/get` fallback 里的人为归类

因此在纯 `uni_promotion` today 主链下，能稳定确认的是：

- `plan_delivery_type = GLOBAL`

不能继续假定：

- 所有 `today` 计划都能通过主链自动识别为 `CUBIC`

结论：

- 上述主链接口适配全域投放
- 乘方投放不应再在 today 热路径里通过 fallback 混入

## 执行结果要求

1. `today` 分钟级热路径只保留：
   - `report/uni_promotion/get`
   - `uni_promotion/list`
   - `account/fund/get`
2. 账户页 today 由计划主链聚合
3. 比率类字段统一本地推导
4. `standard` 与 `uni_report` 退出 today 热路径
5. 计划投放类型在主链下按 `GLOBAL` 解释，`CUBIC` 仅保留在独立 fallback / 历史链路
