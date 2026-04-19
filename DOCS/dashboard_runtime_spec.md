# Qianchuan Dashboard Runtime Spec

## Scope

This document is the canonical runtime contract for `server_payload/qianchuan_openclaw_reporter/dashboard`.

Any future bug fix, refactor, or optimization must preserve this model:

- day-time traffic is served by `Redis + current`
- history is repaired only by the nightly history chain
- database long-term storage is `current + daily + material_profile`
- legacy snapshot/backfill/detail chains must not be reintroduced into scheduler, API routes, or query fallback logic

## Canonical Chains

The dashboard keeps only these business chains:

1. `dashboard.sync`
   Purpose: account hot chain + plan hot chain
   Schedule: every 1 minute
   Writes: `summary_current`, `account_current`, `plan_current`

2. `dashboard.detail_sync`
   Purpose: material hot chain
   Schedule: every 30 minutes
   Writes: `material_current`, `material_daily`, `material_profile`
   Note: task name is retained for compatibility, but semantically it is the material hot chain, not an old "detail sync" chain.

3. `dashboard.nightly_history_refresh`
   Purpose: nightly history correction chain
   Queue: `history`
   Schedule: every day at 02:00
   Behavior: pause hot syncs, rebuild recent account/plan history into `*_daily`, rebuild material history into `material_daily`, rebuild low-frequency material metadata into `material_profile`, clear runtime caches, then resume hot syncs.

4. `dashboard.comment_sync_hot`
   Purpose: hot comment sync

5. `dashboard.oauth_token_refresh`
   Purpose: token refresh / authorization health maintenance

6. `dashboard.dispatch_alerts`
   Purpose: deliver pending alert events

7. `dashboard.material_upload`
   Purpose: material upload job execution

## Prohibited Legacy Paths

The following logic is deprecated and must not be scheduled, routed, or used as query fallback:

- `dashboard.performance_backfill`
- `dashboard.performance_refresh_recent`
- `dashboard.detail_backfill`
- `dashboard.detail_refresh_recent`
- `dashboard.plan_delivery_type_metadata_refresh`
- `/api/sync/extended`
- `/api/sync/backfill/performance`
- `/api/sync/backfill/extended`
- automatic query-triggered history backfill
- fallback reads from legacy snapshot tables as primary query logic

Legacy tables may still exist in storage during transition, but they are no longer part of the runtime contract.

## Read Model Rules

### Performance

- today reads: `Redis -> summary_current/account_current/plan_current`
- history reads: `summary_daily/account_daily/plan_daily`
- query layer must not fall back to `summary_snapshots/account_snapshots/plan_snapshots`

### Material

- today reads: `Redis -> material_current`
- history reads: `material_daily`
- low-frequency metadata reads: `material_profile`
- query layer must not fall back to `material_snapshots/material_rollups/extended_sync_runs`

### Upload / Catalog / Context

- plan context must come from `plan_current`, then `plan_daily`
- asset/catalog metadata must come from `current/daily/material_current/material_profile`
- no upload, catalog, or query path may depend on `plan_detail_snapshots`, `product_snapshots`, or other legacy snapshot tables

## Scheduler Rules

- `ENABLE_HOT_SYNC_SCHEDULES=1` means beat schedules `dashboard.sync` and `dashboard.detail_sync`
- `ENABLE_HOT_SYNC_SCHEDULES=0` disables only those hot schedules
- `dashboard.comment_sync_hot`, `dashboard.oauth_token_refresh`, `dashboard.dispatch_alerts`, and `dashboard.nightly_history_refresh` stay available
- `history-worker` concurrency must follow `NIGHTLY_HISTORY_WORKERS` and default to `6`

## Server Rollout Order

For a fresh deploy or after a large runtime repair:

1. Set `ENABLE_HOT_SYNC_SCHEDULES=0`
2. Start `web`, `history-worker`, and `scheduler`
3. Trigger `dashboard.full_refresh` through `/api/sync/full-refresh`
4. Wait until `/api/sync/full-refresh/status` reaches `completed`
5. Set `ENABLE_HOT_SYNC_SCHEDULES=1`
6. Restart `scheduler`
7. Start or keep `worker` running for normal hot-chain operation

This order is mandatory for initial backfill so nightly history data is repaired before hot chains resume normal updates.

### Docker Compose Runbook

If the server uses `server_payload/qianchuan_openclaw_reporter/docker-compose.dashboard.image.yml`, the rollout should follow these commands:

1. In `.env.dashboard`, set `ENABLE_HOT_SYNC_SCHEDULES=0`
2. Start base services:

```powershell
docker compose -f server_payload/qianchuan_openclaw_reporter/docker-compose.dashboard.image.yml up -d postgres redis web history-worker scheduler
```

3. Trigger the nightly rebuild entry with an authenticated admin session:

```powershell
curl -X POST http://127.0.0.1:9898/api/sync/full-refresh -H "Cookie: session=<admin-session-cookie>"
```

4. Poll until `/api/sync/full-refresh/status` returns `completed`
5. In `.env.dashboard`, set `ENABLE_HOT_SYNC_SCHEDULES=1`
6. Restart scheduler and hot worker:

```powershell
docker compose -f server_payload/qianchuan_openclaw_reporter/docker-compose.dashboard.image.yml up -d worker
docker compose -f server_payload/qianchuan_openclaw_reporter/docker-compose.dashboard.image.yml restart scheduler
```

`worker` must not be started before the initial history rebuild is complete.

## Change Control

Any future change that wants to add:

- a new scheduled chain
- a new manual sync route
- a fallback to legacy snapshot tables
- a second source of truth outside `Redis + current + daily + material_profile`

must be treated as an architecture change and updated in this document first.
