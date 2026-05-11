# NAS 26.5.2-1 restore and deploy

Run these commands in the NAS project directory that contains `.env.dashboard`
and `docker-compose.dashboard.image.yml`.

## 1. Preconditions

The aa side must stay online during restore:

- Dashboard image: `aa.tyos.cc/qc-dashboard:26.5.2-1`
- Restore image: `aa.tyos.cc/qianchuan-db-restore-stream:26.5.2-1`
- Dump URL: `http://aa.tyos.cc:18181/qianchuan_aa_26.5.2-1_20260502.dump`
- Dump sha256: `b50a70ad31882ccfcba4a35ee49946c8d843610a768dffb4fcfa3f3c206007d8`

NAS Docker storage should have at least 10G free space.

## 2. Stop app containers only

Keep `qianchuan-postgres` and `qianchuan-redis` running.

```bash
docker stop \
  qianchuan-web \
  qianchuan-worker \
  qianchuan-upload-worker \
  qianchuan-upload-bind-worker \
  qianchuan-history-worker \
  qianchuan-scheduler 2>/dev/null || true
```

## 3. Restore aa database into NAS PostgreSQL

Copy `docker-compose.nas-restore-stream.yml` into this same project directory,
then run:

```bash
docker compose --env-file .env.dashboard -f docker-compose.nas-restore-stream.yml pull
docker compose --env-file .env.dashboard -f docker-compose.nas-restore-stream.yml up \
  --abort-on-container-exit --exit-code-from restore
```

The restore is successful only if the log ends with:

```text
aa 26.5.2-1 database restore done
```

After success, remove the one-shot restore project:

```bash
docker compose --env-file .env.dashboard -f docker-compose.nas-restore-stream.yml down
```

## 4. Publish the new app image

Make sure `.env.dashboard` contains:

```dotenv
QC_DASHBOARD_IMAGE=aa.tyos.cc/qc-dashboard:26.5.2-1
```

Then pull and recreate the app containers:

```bash
docker compose --env-file .env.dashboard -f docker-compose.dashboard.image.yml pull \
  web worker upload-worker upload-bind-worker history-worker scheduler

docker compose --env-file .env.dashboard -f docker-compose.dashboard.image.yml up -d \
  web worker upload-worker upload-bind-worker history-worker scheduler
```

## 5. Check result

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
docker logs --tail=80 qianchuan-web
curl -fsS http://127.0.0.1:9898/healthz
curl -fsS http://127.0.0.1:9898/readyz
```
