# 千川数据架构与扩展基线

版本：`v1.0`  
最后更新：`2026-03-19`

## 1. 文档目标

这份文档定义本项目后续新增数据时必须遵守的实现路径。

目标不是把所有页面一次做完，而是先把“哪些官方数据已经确认可拉、哪些需要补过滤条件、哪些不能直接拿到”固化下来。后续任何账户、计划、商品、素材、视频、员工类需求，都必须先参考：

- [QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
- [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)
- [DISCOVERY_RUNBOOK.md](./DISCOVERY_RUNBOOK.md)

## 2. 当前已验证的官方数据层

基于 `2026-03-19` 的真实账号探测，当前工作台 `1802375893828620` 下已经确认：

- 账户层：可稳定拉取
- 计划层：可稳定拉取
- 计划详情层：可稳定拉取
- 计划商品层：可稳定拉取
- 计划素材层：可稳定拉取
- 视频首发标记：可稳定拉取
- 自定义全域报表主题：可读取主题配置
- 自定义全域报表数据：部分主题已直接取数成功，部分主题还需要额外过滤条件

结论：

- `账户 / 计划 / 商品 / 素材 / 视频` 都已经进入“官方可实现”范围
- `员工` 不是官方原生字段，只能作为派生维度实现
- `剪辑人员 / 制作人 / 编辑人` 不是千川官方公开字段，必须依赖内部系统映射

## 3. 分层架构

### 3.1 接口层

所有数据只允许来自巨量官方 `open_api`。

当前共享客户端已经补齐这些接口：

- `oauth2/refresh_token`
- `customer_center/advertiser/list`
- `qianchuan/report/uni_promotion/get`
- `qianchuan/uni_promotion/list`
- `qianchuan/uni_promotion/ad/detail`
- `qianchuan/uni_promotion/ad/product/get`
- `qianchuan/uni_promotion/ad/material/get`
- `qianchuan/file/video/original/get`
- `qianchuan/report/uni_promotion/config/get`
- `qianchuan/report/uni_promotion/data/get`

接口实现统一放在：

- [report_qianchuan.py](../report_qianchuan.py)

原则：

- 采集逻辑只在共享客户端里扩展
- 页面和通知层不得各自重复写一套接口请求

### 3.2 能力发现层

能力发现不是页面逻辑，而是“数据边界确认”逻辑。

当前发现脚本：

- [tools/discover_qianchuan_capabilities.py](../tools/discover_qianchuan_capabilities.py)

它负责：

- 取工作台下全部子账户
- 验证账户和计划链路是否正常
- 抽样验证计划详情、商品、素材、视频首发标记
- 拉取全部 `uni_promotion` 自定义主题配置
- 对每个主题做一次最小样本取数
- 输出 JSON 和 Markdown 能力目录

原则：

- 以后新增维度前，先跑发现脚本
- 先确认“主题可用、维度可用、指标可用、过滤条件缺什么”
- 再写正式落库和页面逻辑

### 3.3 规范化采集层

这是后续真正落库用的层。

当前已经正式跑起来的节奏：

- `dashboard-sync`
  - 每 `1` 分钟
  - 拉工作台下全部子账户的账户汇总和计划汇总
- `dashboard-detail-sync`
  - 每 `10` 分钟
  - 基于最新计划快照继续拉计划详情、计划商品、计划素材、视频首发标记

规范化存储仍然按 3 类组织：

1. 基础实体快照
- 账户
- 计划
- 计划详情
- 商品
- 素材
- 视频首发标记

2. 自定义主题快照
- 主题配置
- 主题原始行数据
- 主题字段映射

3. 派生维度快照
- 员工聚合
- 商品聚合
- 视频聚合
- 异常排行

原则：

- 原始响应必须保留
- 页面展示数据来自规范化表，不直接读接口原始 JSON
- 派生维度不能反向污染原始层

### 3.4 派生维度层

当前确认的派生规则：

- 员工：来自 `anchor_name / 抖音号 / 映射表`
- 视频运营归属：来自素材或视频映射
- 剪辑人员：只能来自外部素材系统映射

这层可以做：

- 员工榜
- 员工下账户、计划、商品、素材归因
- 视频表现榜
- 编辑/剪辑归因榜

但约束是：

- 派生字段不算官方字段
- 所有派生逻辑必须有映射来源
- 不能把派生字段写成“官方原始返回”

## 4. 当前正式落库表结构

当前项目已经有：

- `summary_snapshots`
- `account_snapshots`
- `plan_snapshots`
- `plan_detail_snapshots`
- `product_snapshots`
- `material_snapshots`
- `video_origin_flags`
- `extended_sync_runs`
- `alert_rules`
- `alert_events`
- `notification_settings`
- `notification_dispatch_log`

当前正式采集已经分成两层：

- 分钟级主快照：
  - `summary_snapshots`
  - `account_snapshots`
  - `plan_snapshots`
- 10 分钟级细粒度快照：
  - `plan_detail_snapshots`
  - `product_snapshots`
  - `material_snapshots`
  - `video_origin_flags`
  - `extended_sync_runs`

这样设计的目的只有一个：

- 老板看板和实时表格继续保持轻量
- 细粒度商品、素材、视频数据已经按计划落库
- 后续要做商品榜、素材榜、视频榜、计划详情页，只需要读库实现

为了支持更广的后续任意数据扩展，下面这些表仍然保留为推荐基线：

### 4.1 能力登记表

`capability_topic_registry`
- `discovery_time`
- `customer_center_id`
- `advertiser_id`
- `data_topic`
- `dimension_count`
- `metric_count`
- `required_dimensions_json`
- `query_limit_json`
- `probe_status`
- `probe_error`

`capability_field_registry`
- `discovery_time`
- `data_topic`
- `field_type`
- `field_name`
- `field_label`
- `is_required`
- `filterable`
- `filter_only`
- `sortable`
- `description`

### 4.2 基础扩展表

`plan_detail_snapshots`
- `snapshot_time`
- `advertiser_name`
- `advertiser_id`
- `ad_id`
- `ad_name`
- `product_id`
- `product_name`
- `anchor_name`
- `marketing_goal`
- `status`
- `opt_status`
- `roi_goal`
- `modify_time`
- `product_count`
- `room_count`
- `has_delivery_setting`
- `has_creative_setting`
- `raw_json`

`product_snapshots`
- `snapshot_time`
- `window_start`
- `window_end`
- `advertiser_id`
- `advertiser_name`
- `ad_id`
- `ad_name`
- `product_key`
- `product_id`
- `product_name`
- `product_show_count`
- `product_click_count`
- `stat_cost`
- `pay_amount`
- `order_count`
- `roi`
- `raw_json`

`material_snapshots`
- `snapshot_time`
- `window_start`
- `window_end`
- `advertiser_id`
- `advertiser_name`
- `ad_id`
- `ad_name`
- `material_type`
- `material_key`
- `material_id`
- `material_name`
- `video_id`
- `product_show_count`
- `product_click_count`
- `stat_cost`
- `pay_amount`
- `order_count`
- `roi`
- `raw_json`

`video_origin_flags`
- `snapshot_time`
- `advertiser_id`
- `material_id`
- `is_original`
- `raw_json`

`extended_sync_runs`
- `snapshot_time`
- `window_start`
- `window_end`
- `status`
- `plan_count`
- `detail_count`
- `product_row_count`
- `material_row_count`
- `original_video_row_count`
- `error_count`
- `error_json`
- `created_at`
- `finished_at`

### 4.3 自定义主题表

`topic_data_snapshots`
- `snapshot_time`
- `range_key`
- `advertiser_id`
- `data_topic`
- `dimensions_json`
- `metrics_json`
- `raw_json`

### 4.4 映射表

`employee_mappings`
- `mapping_type`
- `mapping_key`
- `employee_name`
- `employee_group`
- `priority`
- `effective_from`
- `effective_to`
- `status`

`editor_mappings`
- `mapping_type`
- `mapping_key`
- `editor_name`
- `team_name`
- `effective_from`
- `effective_to`
- `status`

## 5. 后续新增数据的标准流程

以后不管要看什么数据，都按这 6 步走：

1. 先在能力目录里确认有没有现成官方来源  
2. 如果没有明确结论，先跑发现脚本  
3. 从发现结果里确认：
   - 对应接口
   - 对应主题
   - 必填维度
   - 必填过滤条件
   - 样本是否已取数成功
4. 再扩共享客户端或正式采集脚本  
5. 再落表、做页面、做提醒  
6. 最后更新：
   - 能力目录
   - 功能文档
   - 标准文档

禁止直接跳到第 4 步。

## 6. 当前已知边界

### 6.1 已经确认可实现

- 账户榜
- 计划榜
- 商品榜
- 素材榜
- 视频榜
- 视频首发标记
- 员工榜

### 6.2 需要补过滤条件后实现

部分 `SITE_PROMOTION_POST_*` 主题已经确认开放，但样本取数还要求额外过滤条件，例如：

- `ecp_app_id`
- `anchor_id`
- `aggregate_smart_bid_type`

这类主题不属于“不可用”，而属于“主题可用但还差业务过滤条件”。

### 6.3 当前官方无直接字段

- 剪辑人员
- 制作人
- 编辑人
- 任意内部人效字段

这些必须通过外部系统映射实现。

## 7. 实施原则

- 先能力发现，再正式实现
- 先共享客户端，再页面和通知
- 先保留原始 JSON，再做规范化
- 先做可验证的官方字段，再做派生映射
- 任何新增功能都必须回写能力目录和功能文档
