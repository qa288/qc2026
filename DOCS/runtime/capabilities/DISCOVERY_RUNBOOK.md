# 千川能力发现手册

最后更新：`2026-03-19`

## 1. 目的

这份手册用于重跑“千川官方能力发现”。

适用场景：

- 想确认某个新维度有没有官方字段
- 想知道某个 `data_topic` 是否已经开放
- 想知道某个主题取数还缺哪些过滤条件
- 想给后续页面、告警、报表加新数据

## 2. 入口脚本

脚本位置：

- [tools/discover_qianchuan_capabilities.py](../tools/discover_qianchuan_capabilities.py)

共享客户端：

- [report_qianchuan.py](../report_qianchuan.py)

## 3. 本地运行

如果本地有真实 `config.json`：

```bash
python3 /path/to/qianchuan-reporter/tools/discover_qianchuan_capabilities.py \
  --base-dir /path/to/qianchuan-reporter \
  --output-dir /path/to/qianchuan-reporter/DOCS/runtime/capabilities/discovery
```

输出：

- `capability_snapshot_latest.json`
- `capability_snapshot_latest.md`

## 4. 服务器运行

建议先约定两个变量：

- `REPO_ROOT=/path/to/repo`
- `APP_ROOT=$REPO_ROOT/server_payload/qianchuan_openclaw_reporter`

建议步骤：

1. 先同步最新 `report_qianchuan.py` 和 `tools/discover_qianchuan_capabilities.py`
2. 准备脚本需要的 `state/token_cache.json`：

```bash
mkdir -p "$APP_ROOT/state"
cp "$APP_ROOT/data/qianchuan_latest_token.json" \
  "$APP_ROOT/state/token_cache.json"
```

3. 再运行发现脚本：

```bash
python3 "$APP_ROOT/tools/discover_qianchuan_capabilities.py" \
  --base-dir "$APP_ROOT" \
  --output-dir "$REPO_ROOT/DOCS/runtime/capabilities/discovery"
```

## 5. 怎么看结果

### 5.1 先看接口验证

先看：

- 子账户列表
- 账户汇总
- 计划列表
- 计划详情
- 计划商品
- 计划素材
- 视频首发标记
- 自定义主题配置
- 自定义主题取数

如果这里没通，不要直接做页面。

### 5.2 再看最小粒度结论

这块直接回答：

- 哪些维度已经官方可实现
- 哪些维度只能派生
- 哪些维度官方没有字段

### 5.3 最后看主题表

重点看：

- `样本取数通过`
- `失败原因`
- `缺少哪些筛选条件`

如果失败原因是：

- `缺少必填项`
  说明主题开放了，但你还缺过滤条件
- `参数错误`
  说明当前探测模板还不够，需要补参数模板
- `样本 0 行`
  说明接口可用，但这个时间窗口下没有数据

## 6. 结果如何沉淀

每次发现后至少做这 3 件事：

1. 更新：
   - [QIANCHUAN_CAPABILITY_CATALOG.md](./QIANCHUAN_CAPABILITY_CATALOG.md)
2. 检查是否要更新：
   - [DATA_ARCHITECTURE.md](./DATA_ARCHITECTURE.md)
3. 如果要做功能实现，再更新：
   - [FUNCTIONAL_SPEC.md](../FUNCTIONAL_SPEC.md)
   - [STANDARD.md](../STANDARD.md)
   - [README.md](../README.md)

## 7. 强约束

- 发现脚本只用于确认能力，不替代正式采集链路
- 正式采集仍然必须走共享客户端
- 不允许改回浏览器抓取、Cookie 或内部页面接口
- 新增数据前必须先跑发现或引用最新发现结果
