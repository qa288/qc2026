# 千川官方能力目录

- 生成时间：`2026-03-19 03:48:18`
- 工作台账号：`1802375893828620`
- 统计窗口：`2026-02-18 00:00:00` 到 `2026-03-19 03:47:45`
- 探测账户数：`12`
- 活跃计划样本数：`11`

## 接口验证

| 接口 | 状态 | 说明 |
|---|---|---|
| 子账户列表 | 通过 | 返回 `12` 个子账户 |
| 账户汇总 | 通过 | 成功 `12` / `12` |
| 计划列表 | 通过 | 成功 `6` / `12` |
| 计划详情 | 通过 | 成功 `11` / `11` |
| 计划商品 | 通过 | 成功 `11` / `11` |
| 计划素材 | 通过 | 成功 `33` / `55` |
| 视频首发标记 | 通过 | 样本 `18` 个素材 |
| 自定义主题配置 | 通过 | 返回 `12` 个主题 |
| 自定义主题取数 | 通过 | 成功 `6` / `12` |

## 最小粒度结论

| 维度 | 结论 | 数据源 | 说明 |
|---|---|---|---|
| account | 已验证 | qianchuan/report/uni_promotion/get | 账户消耗、支付、订单、ROI 可直接获取。 |
| plan | 已验证 | qianchuan/uni_promotion/list + qianchuan/uni_promotion/ad/detail | 计划基础配置、状态、商品、直播间和表现可直接获取。 |
| product | 已验证 | qianchuan/uni_promotion/ad/product/get + SITE_PROMOTION_PRODUCT_PRODUCT | 计划下商品与商品维度报表都可通过官方接口扩展。 |
| material | 已验证 | qianchuan/uni_promotion/ad/material/get | 素材列表可按 VIDEO/IMAGE/TITLE/CAROUSEL/LIVE_ROOM 探测。 |
| video | 已验证 | qianchuan/report/uni_promotion/data/get + qianchuan/file/video/original/get | 视频维度依赖自定义全域报表主题；首发标记接口只返回素材是否首发。 |
| employee | 派生实现 | 计划里的 anchor_name / 抖音号映射 | 官方没有直接员工字段，需要映射表或计划归属规则聚合。 |
| editor | 官方无直接字段 | 无官方公开字段 | 剪辑人员/制作人不在千川开放平台标准返回里，必须依赖内部素材系统映射。 |

## 自定义全域报表主题

| 主题 | 维度数 | 指标数 | 必填维度 | 样本取数 |
|---|---:|---:|---|---|
| ROI2_IMAGE_AGG_MATERIAL_ANALYSIS | 5 | 57 | - | 通过，样本 `0` 行 |
| SITE_PROMOTION_POST_DATA_LIVE | 6 | 98 | anchor_id | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误：筛选条件中缺少必填项: ecp_app_id', 'request_id': '20260319034751F6704DEAC929A12A4117'} |
| SITE_PROMOTION_POST_DATA_OTHER | 5 | 9 | roi2_other_creative_name | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误：筛选条件中缺少必填项: ecp_app_id', 'request_id': '2026031903475141AE757502DD0500D019'} |
| SITE_PROMOTION_POST_DATA_TITLE | 6 | 15 | roi2_title_material_v3 | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误：筛选条件中缺少必填项: aggregate_smart_bid_type', 'request_id': '20260319034751856C813D1B24E508AF06'} |
| SITE_PROMOTION_POST_DATA_VIDEO | 12 | 110 | roi2_material_video_name,roi2_material_video_type,material_id | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误：筛选条件中缺少必填项: anchor_id', 'request_id': '2026031903475186BCD0F381B0B178281E'} |
| SITE_PROMOTION_PRODUCT_AD | 4 | 49 | - | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误', 'request_id': '20260319034751083B7A460AB2DAFC7F91'} |
| SITE_PROMOTION_PRODUCT_POST_ASSIST_TASK | 8 | 31 | - | 失败：get uni promotion data failed: {'code': 40000, 'message': '参数错误', 'request_id': '20260319034751D48A7728862757F10ECE'} |
| SITE_PROMOTION_PRODUCT_POST_DATA_IMAGE | 7 | 55 | material_id,roi2_material_image_name | 通过，样本 `5` 行 |
| SITE_PROMOTION_PRODUCT_POST_DATA_OTHER | 3 | 6 | roi2_other_creative_name | 通过，样本 `1` 行 |
| SITE_PROMOTION_PRODUCT_POST_DATA_TITLE | 4 | 13 | roi2_title_material_v3 | 通过，样本 `10` 行 |
| SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO | 8 | 65 | roi2_material_video_name,material_id | 通过，样本 `10` 行 |
| SITE_PROMOTION_PRODUCT_PRODUCT | 4 | 53 | - | 通过，样本 `10` 行 |

## 当前官方结论

- 账户、计划、商品、素材、视频相关数据都可以通过官方接口分层获取。
- 员工维度不是官方原生字段，必须通过计划字段或外部映射表聚合。
- 剪辑人员、制作人不是当前千川官方开放字段，不能直接从投放接口读取。
- 后续新增任何维度，先看 `data_topics` 和 `config/get`，再实现对应存储与页面。
