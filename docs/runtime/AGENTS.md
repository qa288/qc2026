# Qianchuan Reporter Rules

本目录下的所有优化、修复、扩展都必须先阅读 [FUNCTIONAL_SPEC.md](./FUNCTIONAL_SPEC.md)、[STANDARD.md](./STANDARD.md)、[README.md](./README.md)、[QIANCHUAN_CAPABILITY_CATALOG.md](./capabilities/QIANCHUAN_CAPABILITY_CATALOG.md) 和 [DATA_ARCHITECTURE.md](./capabilities/DATA_ARCHITECTURE.md)。

强约束：

- 不要重写现有系统，只允许在当前架构上增量扩展。
- 只使用巨量官方 `open_api`，禁止改成浏览器抓取、Cookie、`/nbs/api/bm/*`。
- Dashboard Web 页必须继续保持 `Docker Compose + FastAPI + PostgreSQL + Redis + Celery + 桌面优先前端` 的架构，不要另起一套临时页面。
- 数据采集和聚合必须通过现有共享客户端、worker 和 scheduler 体系完成，不要把抓数逻辑临时塞进 prompt 或页面层。
- `bridge_send_alerts.py` 是当前阈值告警到 OpenClaw 通知渠道的固定桥接链路，除非有明确替代方案，否则不要绕开。
- 所有新增功能必须先给最小变更方案，再实施。
- 任何新增数据维度前，必须先跑或引用最新能力发现结果，不能直接猜接口。
- 任何新增字段、报表、提醒、推送格式，都必须保持与现有 `config.json`、`report_qianchuan.py`、Celery 任务和数据表兼容，除非用户明确要求破坏性调整。
- 任何新增功能完成后，必须同步更新 `FUNCTIONAL_SPEC.md` 以及必要的 `STANDARD.md` / `README.md`。
