
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import traceback

from dashboard.main import service

CC = "1848205818628227"
TARGETS = {
"1853441984626953": ["2026-01-15","2026-01-16","2026-01-17","2026-01-18","2026-01-19","2026-01-20","2026-01-21","2026-01-22","2026-01-23","2026-01-24","2026-01-25","2026-01-26","2026-01-27","2026-01-29","2026-02-03","2026-02-04","2026-02-05","2026-02-06","2026-02-07","2026-02-08","2026-02-09","2026-02-11"],
"1856640453724521": ["2026-03-06","2026-03-07","2026-03-08","2026-03-13","2026-03-14","2026-03-28","2026-03-29","2026-03-31","2026-04-01","2026-04-06"],
"1853442189521920": ["2026-02-24","2026-02-25","2026-02-26","2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-05"],
"1858258103971927": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-03","2026-03-04","2026-03-05","2026-03-06"],
"1858078344327641": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-03","2026-03-04","2026-03-05"],
"1858078480954368": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-03","2026-03-04","2026-03-05"],
"1858078435909708": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-03","2026-03-05"],
"1858602380243463": ["2026-03-03","2026-03-04","2026-03-05","2026-03-06","2026-03-17","2026-03-31"],
"1859445903870090": ["2026-03-13","2026-03-14","2026-03-19","2026-03-20","2026-03-22","2026-03-31"],
"1858078457407625": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02","2026-03-03"],
"1858550325204115": ["2026-03-03","2026-03-04","2026-03-05","2026-03-06","2026-03-07"],
"1858078388051335": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02"],
"1858078414003204": ["2026-02-27","2026-02-28","2026-03-01","2026-03-02"],
"1858078569346248": ["2026-03-06","2026-03-07","2026-03-12","2026-03-15"],
"1859438567433228": ["2026-03-13","2026-03-14","2026-03-15","2026-03-16"],
"1858550396808204": ["2026-03-03","2026-03-04","2026-03-05"],
"1858550421783623": ["2026-03-03","2026-03-04","2026-03-05"],
"1859438213335048": ["2026-03-13","2026-03-14","2026-03-15"],
"1859445932580104": ["2026-03-13","2026-03-14","2026-03-16"],
"1858550478758169": ["2026-03-25","2026-04-01"],
"1858602430180363": ["2026-03-03","2026-03-04"],
"1859438240102729": ["2026-03-14","2026-03-15"],
"1859545404094480": ["2026-03-17","2026-03-18"],
"1859545521811465": ["2026-03-30","2026-03-31"],
"1853442376608073": ["2026-03-21"],
"1858258146194432": ["2026-03-04"],
"1858258313347081": ["2026-03-04"],
"1858716869200199": ["2026-03-05"],
"1859545365522441": ["2026-04-15"],
}

def log(event, **payload):
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)

def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i+size]

def main():
    tz = ZoneInfo(service.read_config()["timezone"])
    scoped_config = service._scoped_config_for_customer_center(CC)
    scoped_config = {**scoped_config, "detail_material_types": ["VIDEO"]}
    client = service._build_scoped_customer_center_client(CC)
    target_advertisers_by_date = defaultdict(set)
    for adv_s, dates in TARGETS.items():
        adv = int(adv_s)
        for d in dates:
            target_advertisers_by_date[d].add(adv)
    log("start", date_count=len(target_advertisers_by_date), material_types=scoped_config.get("detail_material_types"))
    total_plan_count = 0
    total_material_rows = 0
    errors = []
    for day_index, target_date in enumerate(sorted(target_advertisers_by_date), start=1):
        target_day = datetime.strptime(target_date, "%Y-%m-%d").date()
        day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
        day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
        snapshot_time = service._scoped_day_snapshot_time(day_end, CC)
        advertiser_ids = sorted(target_advertisers_by_date[target_date])
        try:
            plan_rows = []
            with service.db() as conn:
                for chunk in chunks(advertiser_ids, 300):
                    ph = ",".join("?" for _ in chunk)
                    rows = conn.execute(
                        f"""
                        SELECT *
                        FROM plan_daily
                        WHERE customer_center_id = ?
                          AND biz_date = ?
                          AND advertiser_id IN ({ph})
                          AND UPPER(COALESCE(plan_source, '')) IN ('UNI_PROMOTION','UNI_CUBIC','UNI_REPORT')
                        """,
                        [CC, target_date, *chunk],
                    ).fetchall()
                    plan_rows.extend(dict(r) for r in rows)
            plan_rows = [row for row in plan_rows if service._plan_row_has_material_activity(row)]
            plan_ids = sorted({int(row.get("ad_id", 0) or 0) for row in plan_rows if int(row.get("ad_id", 0) or 0) > 0})
            if not plan_ids:
                log("skip", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, reason="no_active_plan")
                continue
            result = service._refresh_material_history_for_changed_plans(
                client=client,
                customer_center_id=CC,
                target_date=target_date,
                snapshot_time=snapshot_time,
                window_start=day_start.strftime("%Y-%m-%d %H:%M:%S"),
                window_end=day_end.strftime("%Y-%m-%d %H:%M:%S"),
                scoped_config=scoped_config,
                changed_plan_ids=plan_ids,
                changed_plan_rows=plan_rows,
            )
            total_plan_count += int(result.get("changed_plan_count", 0) or 0)
            total_material_rows += int(result.get("material_row_count", 0) or 0)
            if int(result.get("error_count", 0) or 0):
                errors.extend({"date": target_date, **dict(item)} for item in (result.get("errors") or []))
            log("progress", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, plan_count=len(plan_ids), result={k: result.get(k) for k in ("changed_plan_count","material_plan_fetch_count","material_row_count","material_snapshot_row_count","material_daily_row_count","material_relation_row_count","error_count")})
        except Exception as exc:
            errors.append({"date": target_date, "stage": "video_material_backfill", "error": str(exc)})
            log("error", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, error=str(exc), traceback=traceback.format_exc(limit=3))
    with service.db() as conn:
        sample = conn.execute("select count(*) rows, coalesce(sum(stat_cost),0) stat_cost, coalesce(sum(pay_amount),0) pay_amount, coalesce(sum(order_count),0) orders from material_relation_daily where customer_center_id=? and biz_date=? and ad_id=?", (CC, "2026-01-15", 1854344250975739)).fetchone()
    log("done", total_plan_count=total_plan_count, total_material_rows=total_material_rows, error_count=len(errors), error_samples=errors[:10], sample_1854344250975739_2026_01_15=dict(sample))

if __name__ == "__main__":
    main()
