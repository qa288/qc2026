# 千川官方接口开发标准手册

最后更新：`2026-03-20`  
最后验证样本：工作台 `1802375893828620`，验证时间 `2026-03-19 03:48:18`

这份文档给同事直接参考，用来基于**已验证的官方接口**做后续开发。  
目标不是介绍页面，而是明确：

- 哪些接口已经验证可用
- 应该按什么顺序调用
- 数据口径和金额单位怎么处理
- 哪些字段不能当官方原始字段使用
- 新增需求时必须遵守哪些规范

配套文档：

- [QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
- [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md)
- [DISCOVERY_RUNBOOK.md](./DISCOVERY_RUNBOOK.md)
- [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)

## 1. 适用范围

这份标准只覆盖巨量官方 `open_api` 的千川能力，不包括：

- `business.oceanengine.com` 页面内部接口
- `/nbs/api/bm/...` 这类工作台内部接口
- 浏览器 Cookie / `csrftoken` 抓取方案
- 非千川官方字段的外部归因数据

当前项目主链路明确只允许使用官方接口。

## 2. 已验证结论

基于真实账号探测，当前已经验证成功的官方能力有：

- 子账户列表
- 账户汇总
- 计划列表
- 计划详情
- 计划商品
- 计划素材
- 视频首发标记
- 自定义全域报表配置
- 自定义全域报表部分主题取数

当前最小粒度结论：

- `账户`：官方直接支持
- `计划`：官方直接支持
- `商品`：官方直接支持
- `素材`：官方直接支持
- `视频`：官方直接支持
- `员工`：只能派生实现
- `剪辑人员 / 制作人 / 编辑人`：官方没有直接字段

详细验证结果见：

- [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)
- [discovery/capability_snapshot_latest.json](./discovery/capability_snapshot_latest.json)

## 3. 开发强约束

### 3.1 数据来源约束

必须遵守：

- 只用巨量官方 `open_api`
- 统一通过共享客户端 [report_qianchuan.py](../report_qianchuan.py) 调用
- 页面层、通知层、脚本层不得各自复制一套 HTTP 请求逻辑

禁止：

- 直接从页面抓包实现正式功能
- 绕过共享客户端手写另一套接口封装
- 把派生字段写成“官方原始字段”

### 3.2 账号模型约束

必须先区分两类 ID：

- `customer_center_id`
  - 纵横工作台 / 客户中心账号
  - 用来展开子账户
- `advertiser_id`
  - 千川实际投放账户
  - 所有报表、计划、商品、素材、视频接口都以它为主

结论：

- 不能直接拿工作台 ID 查账户报表
- 必须先 `customer_center -> advertiser_id 列表`
- 再逐个 `advertiser_id` 查数据

### 3.3 新增数据约束

以后任何新增维度、字段、报表，都必须先走：

1. 查 [QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
2. 查 [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)
3. 如果结论不明确，跑 [DISCOVERY_RUNBOOK.md](./DISCOVERY_RUNBOOK.md)
4. 先确认：
   - 主题是否开放
   - 维度是否开放
   - 指标是否开放
   - 还缺哪些过滤条件
5. 再做正式开发

禁止跳过发现流程，直接猜接口。

## 4. 运行配置标准

当前配置样例见：

- [config.example.json](../config.example.json)

当前配置优先级：

1. 默认值
2. `config.json`
3. 环境变量覆盖

核心环境变量：

- `APP_ID`
- `APP_SECRET`
- `REFRESH_TOKEN`
- `CUSTOMER_CENTER_ID`

关键配置项：

```json
{
  "app_id": 1859509952872521,
  "app_secret": "REPLACE_ME",
  "refresh_token": "REPLACE_ME",
  "customer_center_id": 1802375893828620,
  "account_source": "QIANCHUAN",
  "timezone": "Asia/Shanghai",
  "marketing_goal": "ALL",
  "order_platform": "QIANCHUAN",
  "plan_page_size": 100,
  "plan_marketing_goals": ["VIDEO_PROM_GOODS", "LIVE_PROM_GOODS"]
}
```

说明：

- `app_id / app_secret / refresh_token`
  - 官方授权凭据
- `customer_center_id`
  - 工作台入口账号
- `account_source`
  - 当前固定用 `QIANCHUAN`
- `marketing_goal`
  - 账户汇总默认 `ALL`
- `order_platform`
  - 当前固定用 `QIANCHUAN`
- `plan_marketing_goals`
  - 当前计划列表默认拆查：
    - `VIDEO_PROM_GOODS`
    - `LIVE_PROM_GOODS`

## 5. 已验证官方接口清单

下面这些接口已经在真实账号上验证通过，应该作为后续开发的标准入口。

### 5.1 Token 刷新

- 方法：`POST`
- 地址：`https://ad.oceanengine.com/open_api/oauth2/refresh_token/`
- 代码入口：[report_qianchuan.py](../report_qianchuan.py)

作用：

- 用 `refresh_token` 换新 `access_token`

标准参数：

- `app_id`
- `secret`
- `grant_type=refresh_token`
- `refresh_token`

规范：

- token 统一由共享客户端缓存
- 缓存文件权限必须为 `600`
- 业务层不要自己刷新 token

### 5.2 工作台下子账户列表

- 方法：`GET`
- 地址：`https://ad.oceanengine.com/open_api/2/customer_center/advertiser/list/`
- 代码入口：`OceanEngineClient.list_accounts`

作用：

- 从工作台账号展开全部千川子账户

关键参数：

- `cc_account_id`
- `account_source`
- `page`
- `page_size`

当前验证：

- 返回 `12` 个子账户

### 5.3 账户维度汇总

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/get/`
- 代码入口：`OceanEngineClient.get_account_summary`

作用：

- 查单个 `advertiser_id` 的账户汇总

当前固定字段：

- `stat_cost`
- `total_prepay_and_pay_order_roi2`
- `total_pay_order_count_for_roi2`
- `total_pay_order_gmv_for_roi2`

关键参数：

- `advertiser_id`
- `start_date`
- `end_date`
- `marketing_goal`
- `order_platform`
- `fields`

当前验证：

- 成功 `12 / 12`

### 5.4 计划列表

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/list/`
- 代码入口：`OceanEngineClient.list_plan_summaries`

作用：

- 查单账户计划清单和计划层效果

当前固定字段：

- `stat_cost`
- `total_prepay_and_pay_order_roi2`
- `total_pay_order_count_for_roi2`
- `total_pay_order_gmv_for_roi2`

关键参数：

- `advertiser_id`
- `start_time`
- `end_time`
- `marketing_goal`
- `page`
- `page_size`
- `fields`

当前验证：

- 有计划返回的账户成功 `6 / 12`
- 总计划样本 `23`

说明：

- 这个接口是当前计划榜、计划明细、计划排序的主入口
- 当前实测计划层金额字段需要统一换算，详见第 7 节

### 5.5 计划详情

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/detail/`
- 代码入口：`OceanEngineClient.get_plan_detail`

作用：

- 查单条计划的配置详情

关键参数：

- `advertiser_id`
- `ad_id`

当前验证：

- 成功 `11 / 11`

当前样本里已取到：

- `creative_setting`
- `delivery_setting`
- `product_infos`
- `room_info`
- `marketing_goal`
- `status`
- `opt_status`
- `modify_time`

### 5.6 计划商品

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/product/get/`
- 代码入口：
  - `OceanEngineClient.get_plan_products`
  - `OceanEngineClient.list_plan_products`

作用：

- 拉计划下商品明细

当前固定字段：

- `product_show_count_for_roi2`
- `product_click_count_for_roi2`
- `stat_cost_for_roi2`
- `total_pay_order_count_for_roi2`
- `total_pay_order_gmv_for_roi2`
- `total_prepay_and_pay_order_roi2`

关键参数：

- `advertiser_id`
- `ad_id`
- `start_date`
- `end_date`
- `fields`
- `page`
- `page_size`

当前验证：

- 成功 `11 / 11`

### 5.7 计划素材

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/uni_promotion/ad/material/get/`
- 代码入口：
  - `OceanEngineClient.get_plan_materials`
  - `OceanEngineClient.list_plan_materials`

作用：

- 拉计划下素材列表

关键参数：

- `advertiser_id`
- `ad_id`
- `filtering`
- `page`
- `page_size`

当前已验证素材类型：

- `VIDEO`
- `IMAGE`
- `TITLE`
- `CAROUSEL`
- `LIVE_ROOM`

当前验证：

- 成功 `33 / 55` 组素材探测

说明：

- 对非直播目标计划，当前实现会跳过 `LIVE_ROOM` 查询，避免无意义报错

### 5.8 视频首发标记

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/file/video/original/get/`
- 代码入口：`OceanEngineClient.get_original_videos`

作用：

- 查询视频素材是否首发

关键参数：

- `advertiser_id`
- `material_ids`

当前验证：

- 样本 `18` 个素材返回正常

说明：

- 这个接口返回的是“素材是否首发”标记，不是完整视频表现报表

### 5.9 自定义主题配置

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/config/get/`
- 代码入口：`OceanEngineClient.get_uni_promotion_config`

作用：

- 获取当前账号可用的 `data_topic / dimensions / metrics / query_limit`

关键参数：

- `advertiser_id`
- `data_topics`

当前验证：

- 返回 `12` 个主题

用途：

- 后续任何商品、素材、视频、标题、图文类扩展，都先看这个接口

### 5.10 自定义主题取数

- 方法：`GET`
- 地址：`https://api.oceanengine.com/open_api/v1.0/qianchuan/report/uni_promotion/data/get/`
- 代码入口：`OceanEngineClient.get_uni_promotion_data`

作用：

- 按主题、维度、指标和过滤条件正式取数

关键参数：

- `advertiser_id`
- `data_topic`
- `dimensions`
- `metrics`
- `start_time`
- `end_time`
- `filters`
- `order_by`
- `page`
- `page_size`

当前已直接取数成功的主题：

- `ROI2_IMAGE_AGG_MATERIAL_ANALYSIS`
- `SITE_PROMOTION_PRODUCT_POST_DATA_IMAGE`
- `SITE_PROMOTION_PRODUCT_POST_DATA_OTHER`
- `SITE_PROMOTION_PRODUCT_POST_DATA_TITLE`
- `SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO`
- `SITE_PROMOTION_PRODUCT_PRODUCT`

当前已开放但还需额外过滤条件的主题：

- `SITE_PROMOTION_POST_DATA_LIVE`
- `SITE_PROMOTION_POST_DATA_OTHER`
- `SITE_PROMOTION_POST_DATA_TITLE`
- `SITE_PROMOTION_POST_DATA_VIDEO`

当前样本里发现的必填过滤项包括：

- `ecp_app_id`
- `anchor_id`
- `aggregate_smart_bid_type`

## 6. 官方接口标准调用顺序

后续开发必须优先按下面顺序走，不要乱接：

1. 刷新 token
2. 展开工作台下子账户
3. 拉账户汇总
4. 拉计划列表
5. 拉计划详情
6. 拉计划商品
7. 拉计划素材
8. 拉视频首发标记
9. 如果要加更细维度，再先查 `config/get`
10. 确认维度和过滤条件后，再查 `data/get`

原则：

- 账户和计划是主链路
- 商品、素材、视频是细粒度扩展链路
- 自定义主题一定先查配置，再正式取数

## 7. 数据口径和聚合规范

### 7.1 时间窗口

当前实现统一使用：

- 账户汇总：`start_date / end_date`
- 计划及主题：`start_time / end_time`

标准格式：

- `YYYY-MM-DD HH:MM:SS`

当前页面口径默认支持：

- `day`
- `week`
- `month`

### 7.2 ROI 聚合规则

总 ROI 必须自己重算：

```text
总支付金额 / 总消耗
```

禁止直接平均账户 ROI 或计划 ROI。

### 7.3 计划列表金额单位

`qianchuan/uni_promotion/list` 当前实测金额字段需要统一换算。

当前固定规则：

```text
计划金额展示值 = 原始值 / 100000
```

当前至少适用于：

- `stat_cost`
- `total_pay_order_gmv_for_roi2`

共享实现：

- `normalize_plan_money`

代码位置：

- [report_qianchuan.py](../report_qianchuan.py)

### 7.4 计划分页

当前标准分页值只允许：

- `10`
- `20`
- `50`
- `100`
- `200`

不符合时统一回退到 `100`。

### 7.5 计划营销目标拆查

当前标准拆查值：

- `VIDEO_PROM_GOODS`
- `LIVE_PROM_GOODS`

说明：

- 计划列表默认按两个营销目标拆开查，再合并结果
- 账户汇总则继续用 `ALL`

## 8. 错误处理与重试规范

共享客户端当前重试策略：

- 重试次数：`4`
- 基础退避：`1s`
- 指数退避：`1, 2, 4, 8`

当前重试码：

- `40100`
- `50000`

标准要求：

- 每次请求都要保留原始错误
- 有 `request_id` 时必须落日志
- 页面和通知层不能自己吞掉接口错误

## 9. 能力边界说明

### 9.1 员工

官方没有直接员工字段。

当前只能派生实现，来源通常是：

- `anchor_name`
- 抖音号 / 直播间信息
- 外部映射表

### 9.2 剪辑人员 / 制作人 / 编辑人

当前千川官方接口没有直接字段。

如果要实现，只能来自：

- 内部素材系统
- 素材命名规范
- 外部映射表

### 9.3 自定义主题未完全打通

当前不是所有主题都直接可用。

区分原则：

- `缺少必填项`
  - 代表主题已开放，但还缺业务过滤条件
- `参数错误`
  - 代表当前探测模板还不完整，后续要补参数模板
- `样本 0 行`
  - 代表接口可用，只是当前窗口没有样本数据

## 10. 标准开发流程

同事以后新增任何官方数据开发，固定按这 6 步：

1. 查这份文档，看是不是已验证接口
2. 如果涉及新主题，先跑发现脚本
3. 先在 [report_qianchuan.py](../report_qianchuan.py) 补共享客户端
4. 再补规范化落库，不要直接页面临时查
5. 再补页面、告警或通知逻辑
6. 最后更新：
   - 本文档
   - [QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
   - [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md)
   - 如涉及功能面，再更新 [FUNCTIONAL_SPEC.md](../FUNCTIONAL_SPEC.md)

## 11. 本地代码参考入口

同事开发时优先看这些文件：

- 共享客户端：[report_qianchuan.py](../report_qianchuan.py)
- 能力发现脚本：[tools/discover_qianchuan_capabilities.py](../tools/discover_qianchuan_capabilities.py)
- 能力目录：[QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
- 架构基线：[DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md)
- 发现手册：[DISCOVERY_RUNBOOK.md](./DISCOVERY_RUNBOOK.md)
- 最新验证结果：[discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)

## 12. 官方参考链接

下列是当前主链路对应的官方文档入口：

- [获取纵横工作台下账户列表](https://open.oceanengine.com/labels/12/docs/1796368918556803)
- [获取全域投放账户维度数据](https://open.oceanengine.com/labels/12/docs/1770675169146947)
- [获取全域投放列表](https://open.oceanengine.com/labels/12/docs/1771195810853899)
- [获取全域投放计划详情](https://open.oceanengine.com/labels/12/docs/1804362305657868)
- [获取全域数据-可用维度和指标](https://open.oceanengine.com/labels/12/docs/1823296280645708)
- [获取全域数据](https://open.oceanengine.com/labels/12/docs/1823297941140569)

补充说明：

- `计划商品 / 计划素材 / 视频首发标记` 这三条当前已经通过真实账号取数验证
- 如果同事需要补官方文档页面标题或最新说明，优先按接口路径去开放平台后台检索
- 不要因为文档搜索入口不好用，就回退到页面抓包方案
