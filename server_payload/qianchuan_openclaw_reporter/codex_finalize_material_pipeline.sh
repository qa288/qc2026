#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/qianchuan/qianchuan_openclaw_reporter"
BACKFILL_LOG="/tmp/material_history_backfill_20260108_20260315.log"
FINALIZE_LOG="/tmp/material_finalize_after_backfill_$(date +%Y%m%d_%H%M%S).log"
FINALIZE_LOCK="/tmp/material_finalize_after_backfill.lock"
CONTAINER_PY="/tmp/aa_finalize_material_pipeline.py"
HOST_PY="/tmp/aa_finalize_material_pipeline.py"
RETENTION_DAYS="${MATERIAL_RANKING_INDEX_RETENTION_DAYS:-140}"
ALLOW_BACKFILL_SKIPPED_DAYS="${ALLOW_BACKFILL_SKIPPED_DAYS:-1}"
FINALIZE_INDEX_START_DATE="${FINALIZE_INDEX_START_DATE:-2026-01-01}"
FINALIZE_INDEX_SCOPES="${FINALIZE_INDEX_SCOPES:-current}"
SKIP_IMAGE_UPDATE="${SKIP_IMAGE_UPDATE:-1}"
RECREATE_SERVICES_AFTER_FINALIZE="${RECREATE_SERVICES_AFTER_FINALIZE:-0}"
RECREATE_SERVICES_ON_FAILURE="${RECREATE_SERVICES_ON_FAILURE:-0}"
FINALIZE_PHASE="init"
SCHEDULES_PAUSED=0
SCHEDULES_RESTORED=0

exec > >(tee -a "$FINALIZE_LOG") 2>&1

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
  log "ERROR: $*"
  exit 1
}

cleanup() {
  rm -f "$FINALIZE_LOCK"
}

on_error() {
  local exit_code=$?
  local line_no="${BASH_LINENO[0]:-unknown}"
  trap - ERR
  log "ERROR: finalize pipeline failed; phase=${FINALIZE_PHASE:-unknown}; line=${line_no}; exit_code=${exit_code}"
  if [ "${SCHEDULES_PAUSED:-0}" = "1" ] && [ "${SCHEDULES_RESTORED:-0}" != "1" ]; then
    log "attempting to restore hot/night/half-hour schedules after failure"
    set +e
    set_env_value ENABLE_HOT_SYNC_SCHEDULES 1
    local env_hot_rc=$?
    set_env_value ENABLE_STARTUP_HISTORY_CATCHUP 0
    local env_catchup_rc=$?
    local compose_rc=0
    if [ "${RECREATE_SERVICES_ON_FAILURE:-0}" = "1" ]; then
      compose_up
      compose_rc=$?
    else
      log "skipping compose up during failure restore; RECREATE_SERVICES_ON_FAILURE=0"
    fi
    clear_material_cache
    local cache_rc=$?
    log "failure restore finished; env_hot_exit=${env_hot_rc}; env_catchup_exit=${env_catchup_rc}; compose_exit=${compose_rc}; cache_exit=${cache_rc}"
  fi
  exit "$exit_code"
}

cd "$APP_DIR"

if [ -e "$FINALIZE_LOCK" ] && kill -0 "$(cat "$FINALIZE_LOCK" 2>/dev/null)" 2>/dev/null; then
  fail "finalize script already running with pid $(cat "$FINALIZE_LOCK")"
fi
echo $$ > "$FINALIZE_LOCK"
trap cleanup EXIT
trap on_error ERR

wait_for_backfill() {
  log "waiting for material backfill to finish"
  while ps -ef | grep -E 'material_history_backfill.py' | grep -v grep >/dev/null; do
    tail -5 "$BACKFILL_LOG" || true
    sleep 60
  done
  [ -f "$BACKFILL_LOG" ] || fail "backfill log not found: $BACKFILL_LOG"
  tail -20 "$BACKFILL_LOG" || true
  python3 - "$BACKFILL_LOG" "$ALLOW_BACKFILL_SKIPPED_DAYS" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
allow_skipped = str(sys.argv[2]).strip().lower() in {"1", "true", "yes", "on"}
done = None
day_results = []
skipped_events = set()
for line in path.read_text(errors="replace").splitlines():
    try:
        item = json.loads(line)
    except Exception:
        continue
    event = item.get("event")
    if event == "day_result":
        day_results.append(item)
    if event == "done":
        done = item
    if event == "day_skipped_after_retries" and item.get("day"):
        skipped_events.add(str(item.get("day")))
if done is None:
    raise SystemExit("backfill did not write done event")
failed_days = {str(day) for day in (done.get("failed_days") or [])}
if failed_days and not allow_skipped:
    raise SystemExit(f"backfill failed_days={sorted(failed_days)}")
skipped_days = failed_days | skipped_events
latest_by_day = {}
for item in day_results:
    day = item.get("day")
    if day:
        latest_by_day[str(day)] = item
bad = [
    item
    for day, item in latest_by_day.items()
    if int(item.get("error_count") or 0) > 0 and day not in skipped_days
]
if bad:
    raise SystemExit(f"backfill final day_result has errors: {bad[:3]}")
print({
    "done": done,
    "day_result_count": len(day_results),
    "final_day_result_count": len(latest_by_day),
    "allow_skipped_days": allow_skipped,
    "skipped_days": sorted(skipped_days),
})
PY
}

set_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$key" "$value" .env .env.dashboard <<'PY'
from pathlib import Path
import sys

key, value, *paths = sys.argv[1:]
for raw_path in paths:
    path = Path(raw_path)
    lines = path.read_text().splitlines() if path.exists() else []
    out = []
    seen = False
    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out).rstrip() + "\n")
PY
}

compose_up() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --env-file .env.dashboard -f docker-compose.dashboard.image.yml up -d
  else
    docker-compose --env-file .env.dashboard -f docker-compose.dashboard.image.yml up -d
  fi
}

clear_material_cache() {
  log "clearing material redis cache"
  for pat in 'dashboard:payload:material:*' 'dashboard:cache-version:material:*' 'dashboard:cache-version:material-operator-rankings'; do
    docker exec qianchuan-redis sh -lc "redis-cli -n 0 --scan --pattern '$pat' | xargs -r redis-cli -n 0 DEL >/dev/null"
  done
}

run_finalize_python() {
  log "copying finalize python into web container"
  docker cp "$HOST_PY" "qianchuan-web:$CONTAINER_PY"
  log "running index build and 2026-04-17 calibration"
  docker exec \
    -e PYTHONPATH=/app \
    -e PYTHONUNBUFFERED=1 \
    -e MATERIAL_RANKING_INDEX_RETENTION_DAYS="$RETENTION_DAYS" \
    -e FINALIZE_INDEX_START_DATE="$FINALIZE_INDEX_START_DATE" \
    -e FINALIZE_INDEX_SCOPES="$FINALIZE_INDEX_SCOPES" \
    -e PLAN_MATERIAL_PAGE_WORKERS=4 \
    -e NIGHTLY_HISTORY_PLAN_MATERIAL_REQUESTS_PER_MINUTE=420 \
    -e MATERIAL_SYNC_WORKERS=8 \
    qianchuan-web sh -lc "python '$CONTAINER_PY'"
}

commit_hotfix_image() {
  if [ "${SKIP_IMAGE_UPDATE:-1}" = "1" ]; then
    log "skipping docker commit and QC_DASHBOARD_IMAGE update; current web image remains unchanged"
    return 0
  fi
  local tag="qc-dashboard:aa-hotfix-final-$(date +%Y%m%d_%H%M%S)"
  log "committing current hotfixed web container to $tag"
  docker commit --pause=false qianchuan-web "$tag" >/dev/null
  printf '%s
' "$tag" > DEPLOYED_IMAGE.txt
  set_env_value QC_DASHBOARD_IMAGE "$tag"
  log "new image committed: $tag"
}

verify_after_restart() {
  log "verifying containers"
  docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
  log "verifying material query on web container"
  docker exec -e PYTHONPATH=/app qianchuan-web sh -lc "python - <<'PY'
from dashboard.main import DashboardService
svc = DashboardService()
payload = svc.material_rankings_page_for_user({'role':'admin'}, 'custom', '2026-01-04', '2026-01-04', '', None, 'all', 'performance', 1, 20, 'stat_cost', 'desc', '', True)
for item in payload.get('items') or []:
    if str(item.get('material_key') or '') == '7578841328127164431':
        print({k:item.get(k) for k in ('material_key','stat_cost','pay_amount','order_count','plan_count','advertiser_count','plan_ids','advertiser_ids')})
        break
PY"
}

main() {
  log "finalize pipeline started; log=$FINALIZE_LOG"
  FINALIZE_PHASE="waiting_for_backfill"
  wait_for_backfill

  FINALIZE_PHASE="pausing_schedules"
  log "setting index retention to $RETENTION_DAYS and keeping sync paused during finalize"
  set_env_value MATERIAL_RANKING_INDEX_RETENTION_DAYS "$RETENTION_DAYS"
  set_env_value ENABLE_HOT_SYNC_SCHEDULES 0
  set_env_value ENABLE_STARTUP_HISTORY_CATCHUP 0
  SCHEDULES_PAUSED=1

  FINALIZE_PHASE="running_finalize_python"
  run_finalize_python

  FINALIZE_PHASE="committing_hotfix_image"
  commit_hotfix_image

  FINALIZE_PHASE="restoring_schedules"
  log "enabling hot/night/half-hour schedules in env files"
  set_env_value ENABLE_HOT_SYNC_SCHEDULES 1
  set_env_value ENABLE_STARTUP_HISTORY_CATCHUP 0
  SCHEDULES_RESTORED=1
  clear_material_cache

  if [ "${RECREATE_SERVICES_AFTER_FINALIZE:-0}" = "1" ]; then
    FINALIZE_PHASE="recreating_dashboard_services"
    log "recreating dashboard services on current configured image"
    compose_up
    sleep 20

    FINALIZE_PHASE="post_restart_cache_clear"
    clear_material_cache
  else
    log "skipping dashboard service recreate; current running container and image remain unchanged"
  fi

  FINALIZE_PHASE="post_finalize_verify"
  verify_after_restart
  FINALIZE_PHASE="completed"
  log "finalize pipeline completed"
}

main "$@"
