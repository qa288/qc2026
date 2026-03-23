# qc2026

千川经营看板与官方接口接入项目。

唯一文档入口：

- `DOCS/README.md`

目录说明：

- `DOCS/`
  - 全部正式文档入口
  - 包含 `standard / runtime / integrations / prompts`
- `server_payload/qianchuan_openclaw_reporter/`
  - 当前可运行代码
  - 已迁移到 `FastAPI + PostgreSQL + Redis + Celery + scheduler + Docker Compose`

当前部署基线：

- Web/API：FastAPI
- 主数据库：PostgreSQL
- 队列/缓存/锁：Redis
- 异步任务：Celery
- 调度：独立 scheduler
- 反向代理与站点管理：1Panel

当前正式文档入口：

- `DOCS/README.md`
- `DOCS/standard/00_README_千川投放趋势大盘.md`
- `DOCS/runtime/README.md`
