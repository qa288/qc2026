
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import traceback

from dashboard.main import service
from report_qianchuan import fetch_plan_bundle, build_account_summaries_from_plan_rollups

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


def log(event: str, **payload):
    print(json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True), flush=True)


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def db_account_names():
    ids = sorted(int(k) for k in TARGETS)
    names = {}
    with service.db() as conn:
        for chunk in chunks(ids, 300):
            ph = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT advertiser_id, MAX(advertiser_name) AS advertiser_name
                FROM account_daily
                WHERE customer_center_id = ? AND advertiser_id IN ({ph})
                GROUP BY advertiser_id
                """,
                [CC, *chunk],
            ).fetchall()
            for row in rows:
                names[int(row["advertiser_id"] or 0)] = str(row["advertiser_name"] or "")
    return names


def material_mismatch_plans_for_date(conn, target_date: str, advertiser_ids: list[int]):
    if not advertiser_ids:
        return []
    plan_rows = []
    for chunk in chunks(sorted(set(advertiser_ids)), 300):
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
        plan_rows.extend(dict(row) for row in rows)
    active_rows = [row for row in plan_rows if service._plan_row_has_material_activity(row)]
    if not active_rows:
        return []
    ad_ids = sorted({int(row.get("ad_id", 0) or 0) for row in active_rows if int(row.get("ad_id", 0) or 0) > 0})
    material_by_ad = {}
    for chunk in chunks(ad_ids, 400):
        ph = ",".join("?" for _ in chunk)
        rows = conn.execute(
            f"""
            SELECT ad_id,
                   COUNT(*) AS row_count,
                   COALESCE(SUM(stat_cost), 0) AS stat_cost,
                   COALESCE(SUM(pay_amount), 0) AS pay_amount,
                   COALESCE(SUM(order_count), 0) AS order_count
            FROM material_relation_daily
            WHERE customer_center_id = ?
              AND biz_date = ?
              AND ad_id IN ({ph})
            GROUP BY ad_id
            """,
            [CC, target_date, *chunk],
        ).fetchall()
        for row in rows:
            material_by_ad[int(row["ad_id"] or 0)] = dict(row)
    mismatches = []
    for row in active_rows:
        ad_id = int(row.get("ad_id", 0) or 0)
        mat = material_by_ad.get(ad_id) or {"row_count": 0, "stat_cost": 0, "pay_amount": 0, "order_count": 0}
        plan_cost = float(row.get("stat_cost", 0.0) or 0.0)
        plan_pay = float(row.get("pay_amount", 0.0) or 0.0)
        plan_orders = int(float(row.get("order_count", 0) or 0))
        mat_cost = float(mat.get("stat_cost", 0.0) or 0.0)
        mat_pay = float(mat.get("pay_amount", 0.0) or 0.0)
        mat_orders = int(float(mat.get("order_count", 0) or 0))
        row_count = int(mat.get("row_count", 0) or 0)
        if row_count <= 0 or abs(plan_cost - mat_cost) > 0.05 or abs(plan_pay - mat_pay) > 0.05 or plan_orders != mat_orders:
            mismatches.append(row)
    return mismatches


def route_counts():
    rows = []
    with service.db() as conn:
        for adv_s, dates in TARGETS.items():
            adv = int(adv_s)
            for target_date in dates:
                acc = conn.execute(
                    "SELECT stat_cost,pay_amount,order_count,plan_count FROM account_daily WHERE customer_center_id=? AND advertiser_id=? AND biz_date=?",
                    (CC, adv, target_date),
                ).fetchone()
                plan = conn.execute(
                    "SELECT COALESCE(SUM(stat_cost),0) stat_cost, COALESCE(SUM(pay_amount),0) pay_amount, COALESCE(SUM(order_count),0) order_count, COUNT(*) cnt FROM plan_daily WHERE customer_center_id=? AND advertiser_id=? AND biz_date=?",
                    (CC, adv, target_date),
                ).fetchone()
                mat = conn.execute(
                    "SELECT COALESCE(SUM(stat_cost),0) stat_cost, COALESCE(SUM(pay_amount),0) pay_amount, COALESCE(SUM(order_count),0) order_count, COUNT(*) rows, COUNT(DISTINCT ad_id) plans FROM material_relation_daily WHERE customer_center_id=? AND advertiser_id=? AND biz_date=?",
                    (CC, adv, target_date),
                ).fetchone()
                acc_cost = float(acc["stat_cost"] or 0) if acc else 0.0
                plan_cost = float(plan["stat_cost"] or 0)
                mat_cost = float(mat["stat_cost"] or 0)
                ap_gap = round(acc_cost - plan_cost, 2)
                pm_gap = round(plan_cost - mat_cost, 2)
                if abs(ap_gap) > 0.01:
                    cat = "account_plan_gap"
                elif abs(pm_gap) > 0.05:
                    cat = "plan_material_gap"
                elif acc_cost == 0 and plan_cost == 0 and mat_cost == 0:
                    cat = "all_zero"
                else:
                    cat = "route_balanced"
                rows.append({
                    "cat": cat,
                    "advertiser_id": adv,
                    "date": target_date,
                    "account_cost": round(acc_cost, 2),
                    "plan_cost": round(plan_cost, 2),
                    "material_cost": round(mat_cost, 2),
                    "account_plan_gap": ap_gap,
                    "plan_material_gap": pm_gap,
                    "plan_rows": int(plan["cnt"] or 0),
                    "material_rows": int(mat["rows"] or 0),
                })
    counts = defaultdict(int)
    for row in rows:
        counts[row["cat"]] += 1
    samples = {cat: [row for row in rows if row["cat"] == cat][:10] for cat in sorted(counts)}
    return dict(counts), samples, rows


def main():
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("start", started_at=started_at, pair_count=sum(len(v) for v in TARGETS.values()), date_count=len({d for ds in TARGETS.values() for d in ds}))
    tz = ZoneInfo(service.read_config()["timezone"])
    client = service._build_scoped_customer_center_client(CC)
    scoped_config = service._scoped_config_for_customer_center(CC)
    account_names = db_account_names()
    try:
        live_accounts = client.list_accounts()
        for row in live_accounts:
            adv = int(row.get("advertiser_id", 0) or 0)
            if adv > 0 and row.get("advertiser_name"):
                account_names[adv] = str(row.get("advertiser_name") or "")
    except Exception as exc:
        log("list_accounts_error", error=str(exc))

    perf_errors = []
    official_gaps = []
    written_pairs = 0
    missing_pairs = 0
    pairs = [(int(adv), date) for adv, dates in TARGETS.items() for date in dates]
    for index, (advertiser_id, target_date) in enumerate(pairs, start=1):
        target_day = datetime.strptime(target_date, "%Y-%m-%d").date()
        day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
        day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
        snapshot_time = service._scoped_day_snapshot_time(day_end, CC)
        account = {"advertiser_id": advertiser_id, "advertiser_name": account_names.get(advertiser_id, "")}
        try:
            official = client.get_account_summary(advertiser_id, account["advertiser_name"], day_start, day_end)
            plans, plan_error = fetch_plan_bundle(
                client,
                account,
                day_start,
                day_end,
                allow_standard_fallback=False,
                allow_report_fallback=False,
                merge_report_only_cubic=True,
            )
            account_rows, failures = build_account_summaries_from_plan_rollups(
                [account],
                plans,
                plan_errors_by_advertiser={advertiser_id: plan_error} if plan_error else {},
            )
            if not account_rows:
                missing_pairs += 1
                perf_errors.append({"advertiser_id": advertiser_id, "date": target_date, "stage": "rollup", "error": "no account rollup"})
                log("perf_missing", index=index, total=len(pairs), advertiser_id=advertiser_id, date=target_date, plan_error=plan_error or "")
                continue
            with service.db() as conn:
                service._replace_performance_daily_account_subset(
                    conn,
                    customer_center_id=CC,
                    target_date=target_date,
                    snapshot_time=snapshot_time,
                    account_rows=account_rows,
                    plan_rows=plans,
                )
            written_pairs += 1
            plan_cost = round(sum(float(p.stat_cost or 0.0) for p in plans), 2)
            official_cost = round(float(getattr(official, "stat_cost", 0.0) or 0.0), 2)
            gap = round(official_cost - plan_cost, 2)
            if abs(gap) > 0.05:
                official_gaps.append({"advertiser_id": advertiser_id, "date": target_date, "official_cost": official_cost, "plan_cost": plan_cost, "gap": gap, "plan_error": plan_error or ""})
            if index == 1 or index % 10 == 0 or abs(gap) > 0.05:
                log("perf_progress", index=index, total=len(pairs), advertiser_id=advertiser_id, date=target_date, official_cost=official_cost, plan_cost=plan_cost, gap=gap, plan_count=len(plans), plan_error=plan_error or "")
        except Exception as exc:
            perf_errors.append({"advertiser_id": advertiser_id, "date": target_date, "stage": "performance", "error": str(exc)})
            log("perf_error", index=index, total=len(pairs), advertiser_id=advertiser_id, date=target_date, error=str(exc))

    log("performance_done", written_pairs=written_pairs, missing_pairs=missing_pairs, official_gap_count=len(official_gaps), error_count=len(perf_errors), official_gap_samples=official_gaps[:10], error_samples=perf_errors[:10])

    target_advertisers_by_date = defaultdict(set)
    for adv_s, dates in TARGETS.items():
        adv = int(adv_s)
        for target_date in dates:
            target_advertisers_by_date[target_date].add(adv)

    material_results = []
    material_errors = []
    refreshed_plan_count = 0
    for day_index, target_date in enumerate(sorted(target_advertisers_by_date), start=1):
        target_day = datetime.strptime(target_date, "%Y-%m-%d").date()
        day_start = datetime(target_day.year, target_day.month, target_day.day, 0, 0, 0, tzinfo=tz)
        day_end = datetime(target_day.year, target_day.month, target_day.day, 23, 59, 59, tzinfo=tz)
        snapshot_time = service._scoped_day_snapshot_time(day_end, CC)
        advertiser_ids = sorted(target_advertisers_by_date[target_date])
        try:
            with service.db() as conn:
                mismatch_rows = material_mismatch_plans_for_date(conn, target_date, advertiser_ids)
            plan_ids = sorted({int(row.get("ad_id", 0) or 0) for row in mismatch_rows if int(row.get("ad_id", 0) or 0) > 0})
            if not plan_ids:
                log("material_skip", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, reason="no_mismatch")
                material_results.append({"date": target_date, "changed_plan_count": 0, "error_count": 0})
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
                changed_plan_rows=mismatch_rows,
            )
            refreshed_plan_count += int(result.get("changed_plan_count", 0) or 0)
            material_results.append({"date": target_date, **result})
            if int(result.get("error_count", 0) or 0):
                material_errors.extend({"date": target_date, **dict(item)} for item in (result.get("errors") or []))
            log("material_progress", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, plan_count=len(plan_ids), result={k: result.get(k) for k in ("changed_plan_count","material_plan_fetch_count","material_row_count","material_snapshot_row_count","material_daily_row_count","material_relation_row_count","error_count")})
        except Exception as exc:
            material_errors.append({"date": target_date, "stage": "material", "error": str(exc)})
            log("material_error", day_index=day_index, total_days=len(target_advertisers_by_date), date=target_date, error=str(exc), traceback=traceback.format_exc(limit=3))

    counts, samples, rows = route_counts()
    log("material_done", refreshed_plan_count=refreshed_plan_count, material_day_count=len(material_results), material_error_count=len(material_errors), material_error_samples=material_errors[:10])
    log("route_counts", counts=counts, samples=samples)
    sample_0115 = [row for row in rows if row["advertiser_id"] == 1853441984626953 and row["date"] == "2026-01-15"]
    log("sample_1853441984626953_2026_01_15", rows=sample_0115)
    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("finished", finished_at=finished_at)


if __name__ == "__main__":
    main()
