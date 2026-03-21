# qc2026

千川经营看板与官方接口接入项目。

目录说明：

- `qianchuan_standard_docs/`
  - 目标产品、架构、部署、运维、接口和执行清单文档
- `server_payload/qianchuan_openclaw_reporter/`
  - 当前可运行代码
  - 已迁移到 `FastAPI + PostgreSQL + Redis + Celery + scheduler + Docker Compose`
- `docs/`
  - 补充文档与 OpenClaw 主提示词

当前部署基线：

- Web/API：FastAPI
- 主数据库：PostgreSQL
- 队列/缓存/锁：Redis
- 异步任务：Celery
- 调度：独立 scheduler
- 反向代理与站点管理：1Panel

当前正式文档入口：

- `qianchuan_standard_docs/00_README_千川投放趋势大盘.md`
- `server_payload/qianchuan_openclaw_reporter/README.md`
