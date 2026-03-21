# 巨量千川 OpenClaw 标准文档

版本：`v1.1`  
状态：`生效中`  
最后更新：`2026-03-19`

## 1. 文档目的

本文档用于约束 `qianchuan-reporter` 的长期运维、优化、扩展和新增功能。

功能完整性、页面交互、通知能力、验收清单，以 [FUNCTIONAL_SPEC.md](./FUNCTIONAL_SPEC.md) 为第一基线；本文档偏架构、约束和实现原则。

后续任何 OpenClaw 或人工改动，只要涉及以下内容，都必须先阅读并遵守本文档：

- 数据采集逻辑
- 定时任务
- 通知投递
- 报表结构
- 指标口径
- 新增数据
- 新增提醒
- 新增功能
- 新增数据维度
- 新增自定义主题

## 2. 当前系统定位

这是一个“固定脚本采集 + OpenClaw 模型调度 + OpenClaw 通知渠道投递 + Dashboard 历史看板”的千川报表系统。

设计目标不是做一个复杂应用，而是做一个稳定、可持续扩展、可自动推送的报表系统。

## 3. 当前部署事实

### 3.1 运行环境

- 服务器：`101.42.9.55`
- 系统：`Ubuntu 24.04`
- OpenClaw：`2026.3.8`
- OpenClaw 运行用户：`root`
- OpenClaw workspace 根目录：`/root/.openclaw/workspace`
- 当前报表目录：`/root/.openclaw/workspace/qianchuan-reporter`

### 3.2 当前主要文件

- `/root/.openclaw/workspace/qianchuan-reporter/config.json`
- `/root/.openclaw/workspace/qianchuan-reporter/config.example.json`
- `/root/.openclaw/workspace/qianchuan-reporter/report_qianchuan.py`
- `/root/.openclaw/workspace/qianchuan-reporter/dashboard/main.py`
- `/root/.openclaw/workspace/qianchuan-reporter/docker-compose.dashboard.yml`
- `/root/.openclaw/workspace/qianchuan-reporter/bridge_send_alerts.py`
- `/root/.openclaw/workspace/qianchuan-reporter/README.md`
- `/root/.openclaw/workspace/qianchuan-reporter/STANDARD.md`
- `/root/.openclaw/workspace/qianchuan-reporter/AGENTS.md`
- `/root/.openclaw/workspace/qianchuan-reporter/tools/discover_qianchuan_capabilities.py`
- `/root/.openclaw/workspace/qianchuan-reporter/docs/QIANCHUAN_CAPABILITY_CATALOG.md`
- `/root/.openclaw/workspace/qianchuan-reporter/docs/DATA_ARCHITECTURE.md`
- `/root/.openclaw/workspace/qianchuan-reporter/docs/DISCOVERY_RUNBOOK.md`

### 3.3 当前已生效的定时任务

- 页面服务内采集：
  - 每 `1` 分钟执行一次
  - 负责账户、计划、快照落库
- 页面服务内细粒度采集：
  - 每 `10` 分钟执行一次
  - 负责计划详情、商品、素材、视频首发标记落库
- 页面通知桥接：
  - 由服务器 `systemd timer` 调度
  - 默认每 `1` 分钟检查一次待发告警和定时简报

### 3.4 当前消息投递方式

- 使用 OpenClaw 已配置的通知 channel
- 通过 OpenClaw 自带的消息投递能力发送
- Dashboard 页面可配置：`channel / account / target / 定时简报时间`
- 不依赖外部 webhook 脚本

### 3.5 当前 Web 看板部署

- 页面服务：Docker 容器 `qianchuan-dashboard`
- 访问端口：`9898`
- 登录保护：账号密码登录
- 数据库存储：`/opt/qianchuan-dashboard/data/dashboard.db`
- 页面自动采集：服务内每 `1` 分钟
- 页面告警推送：服务器 `systemd timer`
  - `qianchuan-dashboard-alerts.timer`

## 4. 必须长期保持的核心架构

### 4.1 不可改变的主架构

系统主架构固定为：

```text
巨量官方 open_api
-> report_qianchuan.py 固定脚本采集
-> OpenClaw 自带模型执行与整理输出
-> OpenClaw 通知 channel 投递

巨量官方 open_api
-> dashboard/main.py 容器内采集与落库
-> SQLite 分钟级主快照 + 10 分钟细粒度快照
-> 登录保护的桌面看板
-> bridge_send_alerts.py
-> OpenClaw 通知 channel 告警 / 定时简报
```

Dashboard 内部采集职责固定分层：

- 主快照层：
  - 账户汇总
  - 计划汇总
  - 分钟级排行榜基础数据
- 细粒度层：
  - 计划详情
  - 计划商品
  - 计划素材
  - 视频首发标记
  - 扩展同步状态

### 4.2 明确禁止的替代方案

除非用户明确要求，否则禁止改成以下方式：

- 浏览器自动化抓取
- `business.oceanengine.com` 页面接口
- Cookie、`csrftoken`
- `/nbs/api/bm/promotion/ecp/*`
- 另一套独立调度系统
- 直接由脚本绕开 OpenClaw 发送通知
- 去掉页面登录保护后直接公网裸开
- 丢弃历史快照只保留当前值

## 5. 当前用户要求

这是后续优化和新增功能必须满足的基础要求。

### 5.1 定时要求

- 每天 `09:00` 发简报
- 每 `10` 分钟报一次数据
- 页面数据每 `1` 分钟自动刷新底层快照

### 5.2 报表范围

每次报表至少包含三层：

- 全部账户的整体情况
- 每个账户的基本情况
- 具体推广计划的数据与排名
- 商品维度聚合排名
- 员工维度聚合排名

另外必须提供 Web 页面：

- Boss 总览区
- 账户表现区
- 商品与员工排名区
- 计划决策区
- 告警规则与告警历史区

### 5.3 当前最小指标集

每个账户、整体与计划层至少要包含：

- 消耗
- ROI
- 订单数
- 支付金额

商品层和员工层也必须至少聚合出同一组核心指标。

### 5.4 员工归属默认规则

第一版员工维度不依赖外部人事系统，默认按计划里的主播 / 抖音号字段聚合。

当前硬约束：

- 优先使用 `anchor_name`
- 空值统一归到 `未归属`
- 未接入正式映射表前，不能随意改成根据备注、计划名或账户名模糊猜测
- 如果后续新增员工映射表，必须先更新功能文档再改代码

### 5.5 计划排名要求

简报中必须包含计划层排名。

当前默认规则：

- 仅对“有消耗计划”做排名
- 先按 `订单数` 从高到低
- 同订单数下按 `支付金额` 从高到低
- 再按 `ROI` 从高到低
- 最后按 `消耗` 从高到低

如果用户后续明确指定其他排名规则，可以在此基础上增量调整，但不能无说明地改掉当前默认口径。

### 5.6 调度要求

优先使用 OpenClaw 自带配置的大模型做综合调度，不把调度逻辑外包给单独脚本。

解释：

- 数据采集仍由固定脚本负责
- 任务编排、输出整理、消息投递、定时执行，由 OpenClaw 负责

## 6. 官方接口约束

### 6.1 允许使用的接口

只允许使用巨量官方开放平台接口：

- `oauth2/access_token`
- `oauth2/refresh_token`
- `oauth2/advertiser/get`
- `customer_center/advertiser/list`
- `qianchuan/report/uni_promotion/get`
- `qianchuan/uni_promotion/list`
- `qianchuan/uni_promotion/ad/detail`
- `qianchuan/uni_promotion/ad/product/get`
- `qianchuan/uni_promotion/ad/material/get`
- `qianchuan/file/video/original/get`
- `qianchuan/report/uni_promotion/config/get`
- `qianchuan/report/uni_promotion/data/get`

### 6.2 当前脚本已使用的接口

当前 `report_qianchuan.py` 使用：

- `oauth2/refresh_token`
- `customer_center/advertiser/list`
- `qianchuan/report/uni_promotion/get`
- `qianchuan/uni_promotion/list`

当前共享客户端已补齐并已进入正式存储链路的接口：

- `qianchuan/uni_promotion/ad/detail`
- `qianchuan/uni_promotion/ad/product/get`
- `qianchuan/uni_promotion/ad/material/get`
- `qianchuan/file/video/original/get`

当前共享客户端已补齐、已用于能力发现，但未默认进入周期性通用主题落库的接口：

- `qianchuan/report/uni_promotion/config/get`
- `qianchuan/report/uni_promotion/data/get`

### 6.3 重要参数约束

工作台下子账户列表：

- 必须使用 `cc_account_id`
- 必须补 `account_source=QIANCHUAN`

账户汇总：

- 查询主体必须是子账户 `advertiser_id`
- 不允许把工作台账号直接当作账户报表主体

默认查询口径：

- `marketing_goal=ALL`
- `order_platform=QIANCHUAN`

计划列表查询口径：

- 不允许使用 `marketing_goal=ALL`
- 必须拆成 `VIDEO_PROM_GOODS` 与 `LIVE_PROM_GOODS` 两次查询后再合并

## 7. 指标口径要求

### 7.1 工作台整体情况

工作台整体情况必须由全部子账户聚合得出。

### 7.2 可直接累加的指标

- 消耗
- 支付金额
- 订单数

### 7.3 不能直接平均的指标

- ROI
- 成本类指标
- 退款率类指标

### 7.4 ROI 计算规则

总 ROI 必须按以下规则重算：

```text
总支付金额 / 总消耗
```

禁止直接对账户 ROI 做平均。

### 7.5 计划列表金额单位

`qianchuan/uni_promotion/list` 返回的计划层金额字段，当前实测为原始整型金额，展示前必须统一换算。

当前固定换算规则：

```text
计划金额展示值 = 原始值 / 100000
```

当前至少适用于：

- `stat_cost`
- `total_pay_order_gmv_for_roi2`

如果后续新增其他计划层金额字段，必须先校验单位，再决定是否沿用同一规则。

## 8. 能力发现强约束

后续任何“新增数据、补维度、补字段、补报表”的需求，都必须先经过能力发现流程。

固定入口：

- [docs/QIANCHUAN_CAPABILITY_CATALOG.md](./docs/QIANCHUAN_CAPABILITY_CATALOG.md)
- [docs/DATA_ARCHITECTURE.md](./docs/DATA_ARCHITECTURE.md)
- [docs/DISCOVERY_RUNBOOK.md](./docs/DISCOVERY_RUNBOOK.md)
- [tools/discover_qianchuan_capabilities.py](./tools/discover_qianchuan_capabilities.py)

标准顺序：

1. 先查能力目录
2. 如果结论不明确，先跑发现脚本
3. 先确认：
   - 主题是否开放
   - 维度是否开放
   - 指标是否开放
   - 还缺哪些过滤条件
4. 再做正式采集和页面实现

禁止直接跳过发现流程，凭经验猜接口。

## 9. 当前能力边界

截至 `2026-03-19`，当前真实账号已验证：

- 已验证可实现：
  - 账户
  - 计划
  - 计划详情
  - 商品
  - 素材
  - 视频
  - 视频首发标记
- 派生实现：
  - 员工
- 官方无直接字段：
  - 剪辑人员
  - 制作人
  - 编辑人

另外有部分 `SITE_PROMOTION_POST_*` / `SITE_PROMOTION_PRODUCT_*` 主题已经开放，但样本取数仍缺业务过滤条件，不能误判为“不支持”。

## 10. 报表输出规范

### 8.1 当前 `10` 分钟播报

定义：

- 统计当天 `00:00:00` 到当前时刻的累计数据
- 不是“最近 10 分钟增量”

### 8.2 当前 `09:00` 简报

定义：

- 统计前一天 `00:00:00` 到 `23:59:59`
- 不是“当天晨报实时值”

### 8.3 输出格式

当前推送消息应保持：

- 标题
- 生成时间
- 统计范围
- 整体情况
- 账户明细
- 计划排名

默认用纯文本，不使用复杂卡片。

Web 页面要求：

- 桌面优先
- 简洁、好看、易读
- 支持表格排序
- 用户点击后的排序方式必须持续保持，直到用户再次切换

### 8.4 账户明细排序

默认按消耗从高到低排序。

### 8.5 计划明细排序

默认按“推广效果”排序。

当前“推广效果”的具体定义：

- `订单数` 高的优先
- 同订单数下 `支付金额` 高的优先
- 再按 `ROI`
- 再按 `消耗`

当前默认只展示有消耗计划。

### 8.6 计划明细展示上限

为避免飞书消息过长，当前允许限制计划展示条数。

默认配置：

- `max_plan_rows=30`
- `plan_max_workers=2`

如果活跃计划超过上限：

- 消息中必须注明剩余条数被省略
- 快照中至少保留已展示计划与总体数量

### 8.8 Web 看板交互要求

- 账户表允许点击列头排序
- 计划表允许点击列头排序
- 排序状态在自动刷新后必须保持
- 计划表允许按计划、商品、账户、主播搜索
- 点击账户或计划后必须能看到该对象的趋势快照

### 8.7 计划接口稳定性策略

由于 `qianchuan/uni_promotion/list` 实测可能触发系统级限流，计划层查询必须默认使用保守策略：

- 低并发
- 自动重试
- 指数退避

当前默认实现：

- `plan_max_workers=2`
- 遇到 `40100` 或 `50000` 自动重试

## 11. 配置和安全要求

### 9.1 敏感信息管理

敏感信息只允许出现在：

- `config.json`
- token 缓存文件

当前配置读取顺序已经固定为：

1. 默认值
2. `config.json`
3. 环境变量覆盖

核心环境变量：

- `APP_ID`
- `APP_SECRET`
- `REFRESH_TOKEN`
- `CUSTOMER_CENTER_ID`

后续任何新增脚本、Docker 服务、定时任务都必须遵守同一规则，禁止再实现另一套配置来源。

禁止：

- 写死在 prompt
- 写死在代码里
- 输出到日志
- 输出到飞书消息

### 9.2 文件权限

必须长期保持：

- `config.json` 为 `600`
- token 缓存文件为 `600`
- OpenClaw 凭据目录为 `700`

### 9.3 不允许泄露的信息

后续优化、排障、推送中，不得主动暴露：

- `app_secret`
- `refresh_token`
- `access_token`
- Feishu 目标 ID

## 12. OpenClaw 相关要求

### 10.1 后续优化必须先读文档

只要 OpenClaw 要修改本目录内容，必须先读取：

- `AGENTS.md`
- `STANDARD.md`
- `README.md`

### 10.2 OpenClaw 的职责

OpenClaw 负责：

- 调度脚本
- 使用自带模型整理最终输出
- 用 cron 定时执行
- 投递到 Feishu

### 10.3 脚本的职责

脚本负责：

- 刷新 token
- 调用官方接口
- 计算与聚合
- 输出稳定文本
- 写本地数据快照

### 10.4 Dashboard 服务职责

Dashboard 服务负责：

- 定时采集最新账户与计划数据
- 落库保存历史快照
- 暴露页面和 API
- 提供告警规则管理
- 产生待发送告警事件

### 10.5 不允许的错误做法

- 把采集逻辑直接写进 cron prompt 里
- 每次新增需求就换一套脚本结构
- 不经过脚本直接让模型联网拼装数据
- 只改页面不更新告警桥接
- 改了 dashboard 数据结构但不做历史兼容

## 11. 新增功能标准流程

以后只要用户说“新增数据、优化报表、加提醒、改推送”，必须按以下顺序执行。

### 11.1 第一步：先判断需求类型

必须先明确：

- 数据对象
- 时间范围
- 粒度
- 维度
- 指标
- 输出位置
- 是否推送
- 是否告警

### 11.2 第二步：先判断能否复用现有架构

优先复用：

- `config.json`
- `report_qianchuan.py`
- 现有 cron
- 现有 Feishu channel
- 现有数据目录

### 11.3 第三步：先给最小变更方案

任何新增功能，必须先给：

- 变更目标
- 用哪个官方接口实现
- 改哪些文件
- 是否需要新增字段
- 是否需要新增任务
- 如何验证

### 11.4 第四步：再实施

没有最小变更方案，不允许直接大改。

### 11.5 第五步：更新文档

任何影响运行逻辑、字段口径、调度、消息结构的改动，都必须同步更新：

- `STANDARD.md`
- `README.md`

## 12. 新增数据时的默认规则

如果用户只说“加一个数据”或“加一类报表”，默认按以下原则处理：

- 不重写系统
- 不新增第二套架构
- 先查官方接口能力
- 优先增量扩展现有脚本
- 不默认新增飞书推送
- 不默认新增告警

## 13. 新增功能的兼容性要求

### 13.1 保持现有任务兼容

除非用户明确要求，否则：

- 不删除现有 cron
- 不改已有 cron 名称
- 不改已有报表的基础结构

### 13.2 保持现有配置兼容

新增配置项时：

- 追加新字段
- 不移除旧字段
- 不无提示修改旧字段含义

### 13.3 保持现有输出兼容

如果修改消息内容：

- 必须保留“整体情况 + 账户明细”的主结构
- 除非用户明确要求，否则不要大幅改变阅读顺序

## 14. 测试与验收要求

后续任何改动完成后，至少要做：

### 14.1 本地脚本测试

至少执行：

```bash
python3 report_qianchuan.py intraday
python3 report_qianchuan.py daily
```

### 14.2 OpenClaw 调度测试

至少执行一次：

- `openclaw agent --agent main ...`
或
- `openclaw cron run <job-id>`

### 14.3 飞书发送测试

只要改动影响投递逻辑、消息结构、定时任务，就必须至少做一次实际飞书送达验证。

## 15. 当前已知注意事项

### 15.1 当前 `10` 分钟报表不是增量报表

它现在发送的是“今日累计”，不是“最近 10 分钟新增”。

如果后续要改成增量，必须明确说明这是口径变更，并更新本标准文档。

### 15.2 当前 OpenClaw 版本与环境

当前 OpenClaw 装在 `root` 的运行环境下。  
后续如果升级版本、迁移用户、迁移目录，必须先核对：

- `openclaw` 命令路径
- Node 路径
- Gateway 服务状态
- Feishu channel 配置
- cron 任务是否保留

### 15.3 当前 Feishu 安全策略

当前 Feishu 配置不是最保守策略。  
后续如果做安全收敛，要优先改：

- `groupPolicy`
- 插件 allowlist
- 工具暴露范围

但不能因为安全收敛直接把现有报表投递链路打断。

## 16. 未来推荐优化方向

这些可以做，但必须按本文档流程增量推进：

- 增加更多指标
- 增加计划维度播报
- 增加商品维度报表
- 增加阈值提醒
- 增加日报、周报、月报
- 增加本地数据库
- 增加历史趋势图或附件

## 17. 最终原则

后续所有优化和新增功能，都必须遵守这 6 条：

1. 先读文档。
2. 不重写系统。
3. 只用官方接口。
4. 先给最小变更方案。
5. 改完必须验证。
6. 改完必须更新文档。
