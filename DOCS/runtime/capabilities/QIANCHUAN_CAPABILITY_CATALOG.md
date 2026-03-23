# 千川官方能力目录

最后更新：`2026-03-19 03:48:18`

这份文档是当前项目对“千川官方到底能拉到什么”的稳定结论页。  
详细探测结果在：

- [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md)
- [discovery/capability_snapshot_latest.json](./discovery/capability_snapshot_latest.json)

## 1. 当前结论

已经基于真实工作台 `1802375893828620` 验证：

- `账户`：已验证可拉
- `计划`：已验证可拉
- `计划详情`：已验证可拉
- `商品`：已验证可拉
- `素材`：已验证可拉
- `视频`：已验证可拉
- `视频首发标记`：已验证可拉
- `员工`：只能派生实现
- `剪辑人员 / 制作人 / 编辑人`：官方没有直接字段

## 2. 已验证可实现的数据维度

### 2.1 账户维度

来源：

- `qianchuan/report/uni_promotion/get`

可直接拿到：

- 消耗
- 支付金额
- 订单数
- ROI
- 其它账户汇总指标

适用场景：

- 账户榜
- 账户经营总览
- 工作台整体汇总

### 2.2 计划维度

来源：

- `qianchuan/uni_promotion/list`
- `qianchuan/uni_promotion/ad/detail`

可直接拿到：

- 计划基础信息
- 状态
- 营销目标
- 商品信息
- 直播间 / 抖音号信息
- 配置详情
- 计划效果指标

适用场景：

- 投流决策台
- 计划排名
- 计划详情抽屉
- 计划异常提醒

### 2.3 商品维度

来源：

- `qianchuan/uni_promotion/ad/product/get`
- `SITE_PROMOTION_PRODUCT_PRODUCT`

当前状态：

- 已验证接口可取数
- 已验证主题可取数

适用场景：

- 商品榜
- 商品下计划贡献
- 商品 ROI 排名

### 2.4 素材 / 视频维度

来源：

- `qianchuan/uni_promotion/ad/material/get`
- `SITE_PROMOTION_PRODUCT_POST_DATA_IMAGE`
- `SITE_PROMOTION_PRODUCT_POST_DATA_TITLE`
- `SITE_PROMOTION_PRODUCT_POST_DATA_VIDEO`
- `SITE_PROMOTION_PRODUCT_POST_DATA_OTHER`
- `ROI2_IMAGE_AGG_MATERIAL_ANALYSIS`
- `qianchuan/file/video/original/get`

当前状态：

- 计划素材列表：已验证可取数
- 产品素材主题：已验证可取数
- 视频首发标记：已验证可取数

适用场景：

- 素材榜
- 视频榜
- 素材下计划效果
- 首发视频识别

## 3. 已开放但还需补业务过滤条件的主题

以下主题已经确认在 `config/get` 里开放，但样本取数还缺必填过滤条件：

- `SITE_PROMOTION_POST_DATA_LIVE`
- `SITE_PROMOTION_POST_DATA_OTHER`
- `SITE_PROMOTION_POST_DATA_TITLE`
- `SITE_PROMOTION_POST_DATA_VIDEO`

当前探测返回的必填过滤项提示包括：

- `ecp_app_id`
- `anchor_id`
- `aggregate_smart_bid_type`

这意味着：

- 它们不是“官方不支持”
- 而是“需要先明确业务过滤参数，再正式实现”

## 4. 当前探测下仍未直接取数成功的主题

下面两个主题在当前样本里返回“参数错误”，还需要进一步补参数模板：

- `SITE_PROMOTION_PRODUCT_AD`
- `SITE_PROMOTION_PRODUCT_POST_ASSIST_TASK`

当前应对原则：

- 不把它们判定为不可用
- 先记为“待补参数模板”
- 以后有明确业务需要时，再按发现脚本继续补齐

## 5. 派生维度

### 5.1 员工维度

当前结论：

- 官方没有直接员工字段
- 员工榜可以实现，但必须派生

当前可用来源：

- `anchor_name`
- 抖音号 / 直播间信息
- 计划归属
- 外部映射表

标准做法：

- 第一版：`anchor_name -> 员工`
- 稳定版：增加 `employee_mappings`

### 5.2 剪辑人员 / 制作人 / 编辑人

当前结论：

- 官方投放接口没有直接字段
- 不能从千川开放平台直接查到

实现方式只能是：

- 素材系统映射
- 视频命名规范映射
- 内部生产系统映射

## 6. 以后新增数据时怎么判断

以后任何人再提“能不能看某个数据”，先按这个顺序判断：

1. 看这份目录里有没有现成维度  
2. 看 [discovery/capability_snapshot_latest.md](./discovery/capability_snapshot_latest.md) 里有没有对应主题  
3. 如果没有明确答案，跑 [DISCOVERY_RUNBOOK.md](./DISCOVERY_RUNBOOK.md) 里的发现流程  
4. 确认官方字段存在后，再做正式实现

不要跳过发现流程，直接猜接口。
