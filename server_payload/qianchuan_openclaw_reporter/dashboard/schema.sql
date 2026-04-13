PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS summary_snapshots (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    account_count INTEGER NOT NULL,
    active_account_count INTEGER NOT NULL,
    plan_count INTEGER NOT NULL,
    active_plan_count INTEGER NOT NULL,
    stat_cost REAL NOT NULL,
    pay_amount REAL NOT NULL,
    order_count INTEGER NOT NULL,
    roi REAL NOT NULL,
    account_failures INTEGER NOT NULL,
    plan_failures INTEGER NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time)
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id)
);

CREATE TABLE IF NOT EXISTS plan_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    marketing_goal TEXT NOT NULL,
    plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
    plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
    status TEXT NOT NULL,
    opt_status TEXT NOT NULL,
    roi_goal REAL NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_center_id, snapshot_time, ad_id)
);

CREATE TABLE IF NOT EXISTS summary_daily (
    customer_center_id TEXT NOT NULL DEFAULT '',
    biz_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    account_count INTEGER NOT NULL,
    active_account_count INTEGER NOT NULL,
    plan_count INTEGER NOT NULL,
    active_plan_count INTEGER NOT NULL,
    stat_cost REAL NOT NULL,
    pay_amount REAL NOT NULL,
    order_count INTEGER NOT NULL,
    roi REAL NOT NULL,
    account_failures INTEGER NOT NULL,
    plan_failures INTEGER NOT NULL,
    PRIMARY KEY (customer_center_id, biz_date)
);

CREATE TABLE IF NOT EXISTS account_daily (
    customer_center_id TEXT NOT NULL DEFAULT '',
    biz_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (customer_center_id, biz_date, advertiser_id)
);

CREATE TABLE IF NOT EXISTS plan_daily (
    customer_center_id TEXT NOT NULL DEFAULT '',
    biz_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    marketing_goal TEXT NOT NULL,
    plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
    plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
    status TEXT NOT NULL,
    opt_status TEXT NOT NULL,
    roi_goal REAL NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_center_id, biz_date, ad_id)
);

CREATE TABLE IF NOT EXISTS summary_current (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    account_count INTEGER NOT NULL,
    active_account_count INTEGER NOT NULL,
    plan_count INTEGER NOT NULL,
    active_plan_count INTEGER NOT NULL,
    stat_cost REAL NOT NULL,
    pay_amount REAL NOT NULL,
    order_count INTEGER NOT NULL,
    roi REAL NOT NULL,
    account_failures INTEGER NOT NULL,
    plan_failures INTEGER NOT NULL,
    PRIMARY KEY (customer_center_id)
);
CREATE INDEX IF NOT EXISTS idx_summary_current_snapshot
ON summary_current (snapshot_time, customer_center_id);

CREATE TABLE IF NOT EXISTS account_current (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL,
    error TEXT,
    PRIMARY KEY (customer_center_id, advertiser_id)
);
CREATE INDEX IF NOT EXISTS idx_account_current_snapshot
ON account_current (snapshot_time, customer_center_id, advertiser_id);

CREATE TABLE IF NOT EXISTS plan_current (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    marketing_goal TEXT NOT NULL,
    plan_source TEXT NOT NULL DEFAULT 'UNI_PROMOTION',
    plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
    status TEXT NOT NULL,
    opt_status TEXT NOT NULL,
    roi_goal REAL NOT NULL,
    stat_cost REAL NOT NULL,
    roi REAL NOT NULL,
    order_count INTEGER NOT NULL,
    pay_amount REAL NOT NULL,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_center_id, ad_id)
);
CREATE INDEX IF NOT EXISTS idx_plan_current_snapshot
ON plan_current (snapshot_time, customer_center_id, ad_id);

CREATE TABLE IF NOT EXISTS plan_delivery_type_metadata (
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL DEFAULT '',
    marketing_goal TEXT NOT NULL DEFAULT '',
    plan_delivery_type TEXT NOT NULL DEFAULT 'GLOBAL',
    source TEXT NOT NULL DEFAULT 'UNI_MAIN_LIST',
    detected_at TEXT NOT NULL DEFAULT '',
    refreshed_at TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, ad_id)
);
CREATE INDEX IF NOT EXISTS idx_plan_delivery_type_metadata_cc_adv
ON plan_delivery_type_metadata (customer_center_id, advertiser_id, plan_delivery_type);
CREATE INDEX IF NOT EXISTS idx_plan_delivery_type_metadata_cc_refresh
ON plan_delivery_type_metadata (customer_center_id, refreshed_at);

CREATE TABLE IF NOT EXISTS plan_detail_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    anchor_name TEXT NOT NULL,
    marketing_goal TEXT NOT NULL,
    status TEXT NOT NULL,
    opt_status TEXT NOT NULL,
    roi_goal REAL NOT NULL,
    modify_time TEXT NOT NULL DEFAULT '',
    product_count INTEGER NOT NULL DEFAULT 0,
    room_count INTEGER NOT NULL DEFAULT 0,
    has_delivery_setting INTEGER NOT NULL DEFAULT 0,
    has_creative_setting INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time, ad_id)
);

CREATE TABLE IF NOT EXISTS product_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    product_key TEXT NOT NULL,
    product_id TEXT NOT NULL,
    product_name TEXT NOT NULL,
    product_show_count INTEGER NOT NULL DEFAULT 0,
    product_click_count INTEGER NOT NULL DEFAULT 0,
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time, ad_id, product_key)
);

CREATE TABLE IF NOT EXISTS material_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL,
    material_type TEXT NOT NULL,
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_name TEXT NOT NULL,
    create_time TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    product_show_count INTEGER NOT NULL DEFAULT 0,
    product_click_count INTEGER NOT NULL DEFAULT 0,
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, ad_id, material_type, material_key)
);

CREATE TABLE IF NOT EXISTS material_rollups (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_name TEXT NOT NULL,
    create_time TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL,
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    advertiser_count INTEGER NOT NULL DEFAULT 0,
    plan_ids_json TEXT NOT NULL DEFAULT '[]',
    advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
    is_original INTEGER NOT NULL DEFAULT 0,
    top_plan_name TEXT NOT NULL DEFAULT '',
    top_account_name TEXT NOT NULL DEFAULT '',
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    product_names_json TEXT NOT NULL DEFAULT '[]',
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    overall_ctr REAL NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL DEFAULT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time, material_key)
);

CREATE TABLE IF NOT EXISTS material_current (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_name TEXT NOT NULL,
    create_time TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL,
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    advertiser_count INTEGER NOT NULL DEFAULT 0,
    plan_ids_json TEXT NOT NULL DEFAULT '[]',
    advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
    is_original INTEGER NOT NULL DEFAULT 0,
    top_plan_name TEXT NOT NULL DEFAULT '',
    top_account_name TEXT NOT NULL DEFAULT '',
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    product_names_json TEXT NOT NULL DEFAULT '[]',
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    overall_ctr REAL NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL DEFAULT NULL,
    PRIMARY KEY (customer_center_id, material_key)
);
CREATE INDEX IF NOT EXISTS idx_material_current_snapshot
ON material_current (snapshot_time, customer_center_id, material_key);
CREATE INDEX IF NOT EXISTS idx_material_current_stat_cost_nonzero
ON material_current (customer_center_id, stat_cost DESC, material_key)
WHERE stat_cost > 0;
CREATE INDEX IF NOT EXISTS idx_material_current_total_pay_nonzero
ON material_current (customer_center_id, total_pay_amount DESC, material_key)
WHERE total_pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_current_settled_pay_nonzero
ON material_current (customer_center_id, settled_pay_amount DESC, material_key)
WHERE settled_pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_current_pay_nonzero
ON material_current (customer_center_id, pay_amount DESC, material_key)
WHERE pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_current_order_nonzero
ON material_current (customer_center_id, order_count DESC, material_key)
WHERE order_count > 0;

CREATE TABLE IF NOT EXISTS material_daily (
    customer_center_id TEXT NOT NULL DEFAULT '',
    biz_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL,
    material_name TEXT NOT NULL,
    create_time TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL,
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    plan_count INTEGER NOT NULL DEFAULT 0,
    advertiser_count INTEGER NOT NULL DEFAULT 0,
    plan_ids_json TEXT NOT NULL DEFAULT '[]',
    advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
    is_original INTEGER NOT NULL DEFAULT 0,
    top_plan_name TEXT NOT NULL DEFAULT '',
    top_account_name TEXT NOT NULL DEFAULT '',
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    product_names_json TEXT NOT NULL DEFAULT '[]',
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    overall_ctr REAL NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL DEFAULT NULL,
    PRIMARY KEY (customer_center_id, biz_date, material_key)
);
CREATE INDEX IF NOT EXISTS idx_material_daily_date
ON material_daily (biz_date, customer_center_id, material_key);
CREATE INDEX IF NOT EXISTS idx_material_daily_stat_cost_nonzero
ON material_daily (biz_date, customer_center_id, stat_cost DESC, material_key)
WHERE stat_cost > 0;
CREATE INDEX IF NOT EXISTS idx_material_daily_total_pay_nonzero
ON material_daily (biz_date, customer_center_id, total_pay_amount DESC, material_key)
WHERE total_pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_daily_settled_pay_nonzero
ON material_daily (biz_date, customer_center_id, settled_pay_amount DESC, material_key)
WHERE settled_pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_daily_pay_nonzero
ON material_daily (biz_date, customer_center_id, pay_amount DESC, material_key)
WHERE pay_amount > 0;
CREATE INDEX IF NOT EXISTS idx_material_daily_order_nonzero
ON material_daily (biz_date, customer_center_id, order_count DESC, material_key)
WHERE order_count > 0;

CREATE TABLE IF NOT EXISTS material_profile (
    customer_center_id TEXT NOT NULL DEFAULT '',
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    create_time TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    is_original INTEGER NOT NULL DEFAULT 0,
    top_plan_name TEXT NOT NULL DEFAULT '',
    top_account_name TEXT NOT NULL DEFAULT '',
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    product_names_json TEXT NOT NULL DEFAULT '[]',
    plan_ids_json TEXT NOT NULL DEFAULT '[]',
    advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
    plan_count INTEGER NOT NULL DEFAULT 0,
    advertiser_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, material_key)
);

CREATE TABLE IF NOT EXISTS material_relation_edges (
    customer_center_id TEXT NOT NULL DEFAULT '',
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL DEFAULT 0,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL DEFAULT 0,
    ad_name TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL DEFAULT '',
    last_snapshot_time TEXT NOT NULL DEFAULT '',
    seen_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (customer_center_id, material_key, advertiser_id, ad_id)
);
CREATE INDEX IF NOT EXISTS idx_material_profile_updated
ON material_profile (updated_at, customer_center_id, material_key);

CREATE TABLE IF NOT EXISTS material_relation_current (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL DEFAULT 0,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL DEFAULT 0,
    ad_name TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL DEFAULT '',
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    create_time TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    is_original INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_center_id, advertiser_id, ad_id, material_type, material_key)
);
CREATE INDEX IF NOT EXISTS idx_material_relation_current_snapshot
ON material_relation_current (snapshot_time, customer_center_id, material_key);

CREATE TABLE IF NOT EXISTS material_relation_daily (
    customer_center_id TEXT NOT NULL DEFAULT '',
    biz_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL DEFAULT 0,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL DEFAULT 0,
    ad_name TEXT NOT NULL DEFAULT '',
    material_type TEXT NOT NULL DEFAULT '',
    material_key TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    create_time TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    cover_url TEXT NOT NULL DEFAULT '',
    aweme_item_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    top_anchor_name TEXT NOT NULL DEFAULT '',
    product_info_text TEXT NOT NULL DEFAULT '',
    is_original INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_center_id, biz_date, advertiser_id, ad_id, material_type, material_key)
);
CREATE INDEX IF NOT EXISTS idx_material_relation_daily_date
ON material_relation_daily (biz_date, customer_center_id, material_key);

CREATE TABLE IF NOT EXISTS video_origin_flags (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    material_id TEXT NOT NULL,
    is_original INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, material_id)
);

CREATE TABLE IF NOT EXISTS material_report_snapshots (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    material_type TEXT NOT NULL,
    material_match_key TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    create_time TEXT NOT NULL DEFAULT '',
    stat_cost REAL NOT NULL DEFAULT 0,
    pay_amount REAL NOT NULL DEFAULT 0,
    total_pay_amount REAL NOT NULL DEFAULT 0,
    settled_pay_amount REAL NOT NULL DEFAULT 0,
    order_count INTEGER NOT NULL DEFAULT 0,
    settled_order_count INTEGER NOT NULL DEFAULT 0,
    overall_show_count INTEGER NOT NULL DEFAULT 0,
    overall_click_count INTEGER NOT NULL DEFAULT 0,
    roi REAL NOT NULL DEFAULT 0,
    settled_roi REAL NOT NULL DEFAULT 0,
    pay_order_cost REAL NOT NULL DEFAULT 0,
    settled_amount_rate REAL NOT NULL DEFAULT 0,
    refund_amount_1h REAL NOT NULL DEFAULT 0,
    refund_rate_1h REAL DEFAULT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id, material_type, material_match_key)
);

CREATE TABLE IF NOT EXISTS extended_sync_runs (
    customer_center_id TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    status TEXT NOT NULL,
    plan_count INTEGER NOT NULL DEFAULT 0,
    detail_count INTEGER NOT NULL DEFAULT 0,
    product_row_count INTEGER NOT NULL DEFAULT 0,
    material_row_count INTEGER NOT NULL DEFAULT 0,
    original_video_row_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    error_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    PRIMARY KEY (customer_center_id, snapshot_time)
);

CREATE TABLE IF NOT EXISTS plan_refresh_states (
    customer_center_id TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL,
    advertiser_id BIGINT NOT NULL DEFAULT 0,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    opt_status TEXT NOT NULL DEFAULT '',
    last_hot_sync_at TEXT NOT NULL DEFAULT '',
    last_warm_sync_at TEXT NOT NULL DEFAULT '',
    last_cold_sync_at TEXT NOT NULL DEFAULT '',
    next_cold_due_at TEXT NOT NULL DEFAULT '',
    last_material_sync_at TEXT NOT NULL DEFAULT '',
    last_material_change_at TEXT NOT NULL DEFAULT '',
    last_status_change_at TEXT NOT NULL DEFAULT '',
    last_nonzero_perf_at TEXT NOT NULL DEFAULT '',
    last_material_error_at TEXT NOT NULL DEFAULT '',
    last_material_error_code INTEGER NOT NULL DEFAULT 0,
    last_material_error_message TEXT NOT NULL DEFAULT '',
    last_material_error_retryable INTEGER NOT NULL DEFAULT 0,
    consecutive_material_error_count INTEGER NOT NULL DEFAULT 0,
    next_material_retry_at TEXT NOT NULL DEFAULT '',
    last_material_row_count INTEGER NOT NULL DEFAULT 0,
    sync_priority TEXT NOT NULL DEFAULT 'cold',
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (customer_center_id, ad_id)
);

CREATE TABLE IF NOT EXISTS history_refresh_states (
    customer_center_id TEXT NOT NULL DEFAULT '',
    target_date TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    trigger TEXT NOT NULL DEFAULT '',
    snapshot_time TEXT NOT NULL DEFAULT '',
    affected_tables_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    last_attempt_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    last_success_at TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (customer_center_id, target_date, stage)
);

CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold REAL NOT NULL,
    min_spend REAL NOT NULL DEFAULT 0,
    cooldown_minutes INTEGER NOT NULL DEFAULT 60,
    enabled INTEGER NOT NULL DEFAULT 1,
    target_id TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    snapshot_time TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold REAL NOT NULL,
    current_value REAL NOT NULL,
    stat_cost REAL NOT NULL,
    pay_amount REAL NOT NULL,
    order_count INTEGER NOT NULL,
    roi REAL NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    sent_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(rule_id) REFERENCES alert_rules(id)
);

CREATE TABLE IF NOT EXISTS notification_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    channel TEXT NOT NULL DEFAULT 'feishu',
    account TEXT NOT NULL DEFAULT 'default',
    target TEXT NOT NULL DEFAULT '',
    alert_enabled INTEGER NOT NULL DEFAULT 0,
    alert_batch_size INTEGER NOT NULL DEFAULT 6,
    summary_enabled INTEGER NOT NULL DEFAULT 0,
    summary_times TEXT NOT NULL DEFAULT '09:00',
    summary_account_limit INTEGER NOT NULL DEFAULT 6,
    summary_plan_limit INTEGER NOT NULL DEFAULT 10,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_dispatch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    schedule_key TEXT NOT NULL,
    status TEXT NOT NULL,
    channel TEXT NOT NULL,
    account TEXT NOT NULL,
    target TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(kind, schedule_key)
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    app_id TEXT NOT NULL,
    customer_center_id TEXT NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL DEFAULT 0,
    refresh_token_expires_in INTEGER,
    updated_at INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'runtime',
    PRIMARY KEY (app_id, customer_center_id)
);

CREATE TABLE IF NOT EXISTS runtime_config_overrides (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    customer_center_id TEXT NOT NULL DEFAULT '',
    refresh_token TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employee_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'all',
    priority INTEGER NOT NULL DEFAULT 100,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS employee_manual_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    object_type TEXT NOT NULL,
    object_key TEXT NOT NULL,
    object_label TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(employee_id) REFERENCES employees(id),
    UNIQUE (object_type, object_key)
);

CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    display_name TEXT NOT NULL DEFAULT '',
    upload_materials_enabled INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_account_scopes (
    user_id INTEGER NOT NULL,
    advertiser_id BIGINT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, advertiser_id),
    FOREIGN KEY(user_id) REFERENCES app_users(id)
);

CREATE TABLE IF NOT EXISTS user_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES app_users(id)
);

CREATE TABLE IF NOT EXISTS material_upload_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_by_user_id INTEGER NOT NULL,
    scope TEXT NOT NULL DEFAULT 'plan',
    query_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    task_id TEXT NOT NULL DEFAULT '',
    total_files INTEGER NOT NULL DEFAULT 0,
    total_targets INTEGER NOT NULL DEFAULT 0,
    uploaded_files INTEGER NOT NULL DEFAULT 0,
    processed_files INTEGER NOT NULL DEFAULT 0,
    success_files INTEGER NOT NULL DEFAULT 0,
    failed_files INTEGER NOT NULL DEFAULT 0,
    processed_targets INTEGER NOT NULL DEFAULT 0,
    success_targets INTEGER NOT NULL DEFAULT 0,
    failed_targets INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    completed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(created_by_user_id) REFERENCES app_users(id)
);

CREATE TABLE IF NOT EXISTS material_upload_job_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT NOT NULL DEFAULT '',
    file_sha256 TEXT NOT NULL DEFAULT '',
    file_md5 TEXT NOT NULL DEFAULT '',
    processed_advertisers INTEGER NOT NULL DEFAULT 0,
    success_advertisers INTEGER NOT NULL DEFAULT 0,
    failed_advertisers INTEGER NOT NULL DEFAULT 0,
    material_id TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'stored',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(job_id) REFERENCES material_upload_jobs(id)
);

CREATE TABLE IF NOT EXISTS material_upload_job_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL DEFAULT '',
    ad_id BIGINT NOT NULL,
    ad_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES material_upload_jobs(id)
);

CREATE TABLE IF NOT EXISTS advertiser_material_assets (
    advertiser_id BIGINT NOT NULL,
    file_sha256 TEXT NOT NULL,
    material_id TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    material_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (advertiser_id, file_sha256)
);

CREATE TABLE IF NOT EXISTS material_upload_job_file_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    material_id TEXT NOT NULL DEFAULT '',
    video_id TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES material_upload_jobs(id),
    FOREIGN KEY(file_id) REFERENCES material_upload_job_files(id)
);

CREATE TABLE IF NOT EXISTS material_upload_job_target_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES material_upload_jobs(id),
    FOREIGN KEY(target_id) REFERENCES material_upload_job_targets(id),
    FOREIGN KEY(file_id) REFERENCES material_upload_job_files(id)
);

CREATE TABLE IF NOT EXISTS account_balances (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    advertiser_id BIGINT NOT NULL,
    advertiser_name TEXT NOT NULL,
    account_balance REAL NOT NULL DEFAULT 0,
    available_balance REAL NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (customer_center_id, snapshot_time, advertiser_id)
);

CREATE TABLE IF NOT EXISTS shared_wallets (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    main_wallet_id TEXT NOT NULL,
    wallet_name TEXT NOT NULL DEFAULT '',
    total_balance REAL NOT NULL DEFAULT 0,
    valid_balance REAL NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (customer_center_id, snapshot_time, main_wallet_id)
);

CREATE TABLE IF NOT EXISTS shared_wallet_account_relations (
    snapshot_time TEXT NOT NULL,
    customer_center_id TEXT NOT NULL DEFAULT '',
    main_wallet_id TEXT NOT NULL,
    advertiser_id BIGINT NOT NULL,
    child_wallet_id TEXT NOT NULL DEFAULT '',
    wallet_name TEXT NOT NULL DEFAULT '',
    raw_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (customer_center_id, snapshot_time, main_wallet_id, advertiser_id)
);

CREATE INDEX IF NOT EXISTS idx_account_snapshots_adv_time
ON account_snapshots (advertiser_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_summary_snapshots_cc_time
ON summary_snapshots (customer_center_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_account_snapshots_cc_adv_time
ON account_snapshots (customer_center_id, advertiser_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_plan_snapshots_plan_time
ON plan_snapshots (ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_plan_snapshots_cc_plan_time
ON plan_snapshots (customer_center_id, ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_summary_daily_date_cc
ON summary_daily (biz_date, customer_center_id);

CREATE INDEX IF NOT EXISTS idx_account_daily_date_cc_adv
ON account_daily (biz_date, customer_center_id, advertiser_id);

CREATE INDEX IF NOT EXISTS idx_plan_daily_date_cc_plan
ON plan_daily (biz_date, customer_center_id, ad_id);

CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_plan_time
ON plan_detail_snapshots (ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_plan_detail_snapshots_cc_plan_time
ON plan_detail_snapshots (customer_center_id, ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_product_snapshots_plan_time
ON product_snapshots (ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_product_snapshots_cc_plan_time
ON product_snapshots (customer_center_id, ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_product_snapshots_product_time
ON product_snapshots (product_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_snapshots_plan_time
ON material_snapshots (ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_snapshots_cc_plan_time
ON material_snapshots (customer_center_id, ad_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_snapshots_material_time
ON material_snapshots (material_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_rollups_snapshot_time
ON material_rollups (snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_rollups_cc_snapshot_time
ON material_rollups (customer_center_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_video_origin_flags_material_time
ON video_origin_flags (material_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_video_origin_flags_cc_material_time
ON video_origin_flags (customer_center_id, material_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_report_snapshots_cc_time
ON material_report_snapshots (customer_center_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_report_snapshots_material
ON material_report_snapshots (customer_center_id, material_type, material_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_material
ON material_relation_edges (customer_center_id, material_key, last_seen_at DESC, advertiser_id, ad_id);

CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_advertiser
ON material_relation_edges (customer_center_id, advertiser_id, last_seen_at DESC, material_key);

CREATE INDEX IF NOT EXISTS idx_material_relation_edges_cc_ad
ON material_relation_edges (customer_center_id, ad_id, last_seen_at DESC, material_key);

CREATE INDEX IF NOT EXISTS idx_extended_sync_runs_cc_time
ON extended_sync_runs (customer_center_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_priority_sync
ON plan_refresh_states (customer_center_id, sync_priority, last_material_sync_at, ad_id);

CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_cold_sync
ON plan_refresh_states (customer_center_id, last_cold_sync_at, ad_id);

CREATE INDEX IF NOT EXISTS idx_plan_refresh_states_cc_next_cold_due
ON plan_refresh_states (customer_center_id, next_cold_due_at, ad_id);

CREATE INDEX IF NOT EXISTS idx_history_refresh_states_stage_date
ON history_refresh_states (stage, target_date, customer_center_id);

CREATE INDEX IF NOT EXISTS idx_history_refresh_states_status_updated
ON history_refresh_states (status, updated_at);

CREATE INDEX IF NOT EXISTS idx_alert_events_status_created
ON alert_events (status, created_at);

CREATE INDEX IF NOT EXISTS idx_notification_dispatch_kind_key
ON notification_dispatch_log (kind, schedule_key);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_updated
ON oauth_tokens (updated_at);

CREATE INDEX IF NOT EXISTS idx_employees_enabled
ON employees (enabled, display_name);

CREATE INDEX IF NOT EXISTS idx_employee_keywords_employee
ON employee_keywords (employee_id, enabled, scope);

CREATE INDEX IF NOT EXISTS idx_employee_manual_bindings_employee
ON employee_manual_bindings (employee_id, object_type);

CREATE INDEX IF NOT EXISTS idx_app_users_role_enabled
ON app_users (role, enabled);

CREATE INDEX IF NOT EXISTS idx_user_account_scopes_user
ON user_account_scopes (user_id);

CREATE INDEX IF NOT EXISTS idx_user_keywords_user
ON user_keywords (user_id, enabled);

CREATE INDEX IF NOT EXISTS idx_material_upload_jobs_user_created
ON material_upload_jobs (created_by_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_material_upload_job_targets_job
ON material_upload_job_targets (job_id, advertiser_id, ad_id);

CREATE INDEX IF NOT EXISTS idx_material_upload_job_files_job
ON material_upload_job_files (job_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_advertiser_material_assets_unique
ON advertiser_material_assets (advertiser_id, file_sha256);

CREATE INDEX IF NOT EXISTS idx_material_upload_job_file_assets_job
ON material_upload_job_file_assets (job_id, file_id, advertiser_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_material_upload_job_target_assets_unique
ON material_upload_job_target_assets (job_id, target_id, file_id);

CREATE INDEX IF NOT EXISTS idx_material_upload_job_target_assets_job
ON material_upload_job_target_assets (job_id, target_id, file_id, status);

CREATE INDEX IF NOT EXISTS idx_account_balances_adv_time
ON account_balances (advertiser_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_account_balances_cc_adv_time
ON account_balances (customer_center_id, advertiser_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_shared_wallets_wallet_time
ON shared_wallets (main_wallet_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_shared_wallets_cc_time
ON shared_wallets (customer_center_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_shared_wallet_account_rel_wallet_adv
ON shared_wallet_account_relations (main_wallet_id, advertiser_id, snapshot_time);

CREATE INDEX IF NOT EXISTS idx_shared_wallet_relations_cc_time
ON shared_wallet_account_relations (customer_center_id, snapshot_time);
