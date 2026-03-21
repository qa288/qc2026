const RANGE_LABELS = {
  day: "今日",
  week: "近 7 天",
  month: "近 30 天",
  custom: "自定义时间段",
};

const state = {
  payload: null,
  rangePayloads: {},
  planAssetCache: {},
  materialPayload: null,
  accountSort: loadSort("account-sort", { key: "stat_cost", dir: "desc" }),
  planSort: loadSort("plan-sort", { key: "order_count", dir: "desc" }),
  employeeSort: loadSort("employee-sort", { key: "pay_amount", dir: "desc" }),
  productSort: loadSort("product-sort", { key: "order_count", dir: "desc" }),
  materialSort: loadSort("material-sort", { key: "order_count", dir: "desc" }),
  activeView: loadPreference("active-view", "overview"),
  performanceFilters: {
    account: loadRangeFilter("account-range-filter", "day"),
    plan: loadRangeFilter("plan-range-filter", "day"),
    breakdown: loadRangeFilter("breakdown-range-filter", "day"),
  },
  selectedPlanId: null,
  selectedEmployeeName: null,
  selectedProductKey: null,
  selectedMaterialKey: null,
};

const kpiGrid = document.getElementById("kpiGrid");
const alertStream = document.getElementById("alertStream");
const accountTable = document.getElementById("accountTable");
const planTable = document.getElementById("planTable");
const employeeTable = document.getElementById("employeeTable");
const productTable = document.getElementById("productTable");
const ruleTable = document.getElementById("ruleTable");
const planDetail = document.getElementById("planDetail");
const employeeDetail = document.getElementById("employeeDetail");
const productDetail = document.getElementById("productDetail");
const planAssetSummary = document.getElementById("planAssetSummary");
const materialTable = document.getElementById("materialTable");
const materialDetail = document.getElementById("materialDetail");
const alertSummary = document.getElementById("alertSummary");
const accountSearch = document.getElementById("accountSearch");
const planSearch = document.getElementById("planSearch");
const employeeSearch = document.getElementById("employeeSearch");
const productSearch = document.getElementById("productSearch");
const materialSearch = document.getElementById("materialSearch");
const planAccountFilter = document.getElementById("planAccountFilter");
const notificationForm = document.getElementById("notificationForm");
const notificationStatus = document.getElementById("notificationStatus");
const ruleForm = document.getElementById("ruleForm");
const syncButton = document.getElementById("syncButton");
const syncExtendedButton = document.getElementById("syncExtendedButton");
const heroStatusText = document.getElementById("heroStatusText");
const heroStatusHint = document.getElementById("heroStatusHint");
const lastSnapshotText = document.getElementById("lastSnapshotText");
const refreshHintText = document.getElementById("refreshHintText");
const systemStatusCard = document.getElementById("systemStatusCard");
const detailSyncCard = document.getElementById("detailSyncCard");
const signalOverview = document.getElementById("signalOverview");
const overviewHeroCard = document.getElementById("overviewHeroCard");
const viewTabs = document.getElementById("viewTabs");
const viewSections = Array.from(document.querySelectorAll(".view-section"));
const accountRangeSwitch = document.getElementById("accountRangeSwitch");
const planRangeSwitch = document.getElementById("planRangeSwitch");
const breakdownRangeSwitch = document.getElementById("breakdownRangeSwitch");
const accountRangeMeta = document.getElementById("accountRangeMeta");
const planRangeMeta = document.getElementById("planRangeMeta");
const breakdownRangeMeta = document.getElementById("breakdownRangeMeta");
const accountDateStart = document.getElementById("accountDateStart");
const accountDateEnd = document.getElementById("accountDateEnd");
const accountDateApply = document.getElementById("accountDateApply");
const planDateStart = document.getElementById("planDateStart");
const planDateEnd = document.getElementById("planDateEnd");
const planDateApply = document.getElementById("planDateApply");
const breakdownDateStart = document.getElementById("breakdownDateStart");
const breakdownDateEnd = document.getElementById("breakdownDateEnd");
const breakdownDateApply = document.getElementById("breakdownDateApply");
const materialSyncMeta = document.getElementById("materialSyncMeta");
const PERFORMANCE_SECTION_CONFIG = {
  account: {
    storageKey: "account-range-filter",
    switchEl: accountRangeSwitch,
    metaEl: accountRangeMeta,
    startEl: accountDateStart,
    endEl: accountDateEnd,
    applyEl: accountDateApply,
  },
  plan: {
    storageKey: "plan-range-filter",
    switchEl: planRangeSwitch,
    metaEl: planRangeMeta,
    startEl: planDateStart,
    endEl: planDateEnd,
    applyEl: planDateApply,
  },
  breakdown: {
    storageKey: "breakdown-range-filter",
    switchEl: breakdownRangeSwitch,
    metaEl: breakdownRangeMeta,
    startEl: breakdownDateStart,
    endEl: breakdownDateEnd,
    applyEl: breakdownDateApply,
  },
};

function loadSort(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch {
    return fallback;
  }
}

function saveSort(key, sort) {
  localStorage.setItem(key, JSON.stringify(sort));
}

function loadPreference(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function savePreference(key, value) {
  localStorage.setItem(key, value);
}

function formatDateInputValue(value) {
  const date = new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function derivePresetDateRange(mode) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  if (mode === "week") {
    start.setDate(start.getDate() - 6);
  } else if (mode === "month") {
    start.setDate(start.getDate() - 29);
  }
  return {
    start: formatDateInputValue(start),
    end: formatDateInputValue(today),
  };
}

function isValidDateInput(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value || "").trim());
}

function normalizeRangeFilter(value, fallbackMode = "day") {
  const nextMode = normalizeRangeKey(value?.mode || fallbackMode);
  if (nextMode !== "custom") {
    return {
      mode: nextMode,
      ...derivePresetDateRange(nextMode),
    };
  }
  const start = String(value?.start || "").trim();
  const end = String(value?.end || "").trim();
  if (!isValidDateInput(start) || !isValidDateInput(end) || start > end) {
    return {
      mode: fallbackMode,
      ...derivePresetDateRange(fallbackMode),
    };
  }
  return { mode: "custom", start, end };
}

function loadRangeFilter(storageKey, fallbackMode = "day") {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) {
      return normalizeRangeFilter({ mode: fallbackMode }, fallbackMode);
    }
    return normalizeRangeFilter(JSON.parse(raw), fallbackMode);
  } catch {
    return normalizeRangeFilter({ mode: fallbackMode }, fallbackMode);
  }
}

function saveRangeFilter(storageKey, value) {
  localStorage.setItem(storageKey, JSON.stringify(value));
}

function formatMoney(value) {
  return Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatRate(value) {
  return Number(value || 0).toFixed(2);
}

function formatDateTime(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 19);
}

function formatAgoFromEpoch(value) {
  const epoch = Number(value || 0);
  if (!epoch) return "未记录";
  const diffSeconds = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (diffSeconds < 60) return `${diffSeconds} 秒前`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)} 分钟前`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)} 小时前`;
  return `${Math.floor(diffSeconds / 86400)} 天前`;
}

function compareValues(left, right, dir) {
  const l = left ?? "";
  const r = right ?? "";
  if (typeof l === "number" && typeof r === "number") {
    return dir === "asc" ? l - r : r - l;
  }
  return dir === "asc" ? String(l).localeCompare(String(r), "zh-CN") : String(r).localeCompare(String(l), "zh-CN");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function metricLabel(metric) {
  const labels = {
    roi: "ROI",
    stat_cost: "消耗",
    order_count: "订单数",
    pay_amount: "支付金额",
  };
  return labels[metric] || metric;
}

function channelLabel(channel) {
  const labels = {
    feishu: "飞书",
    dingtalk: "钉钉",
    slack: "Slack",
    telegram: "Telegram",
    email: "邮箱",
  };
  return labels[String(channel || "").trim().toLowerCase()] || String(channel || "-");
}

function operatorLabel(operator) {
  const labels = {
    gt: ">",
    gte: ">=",
    lt: "<",
    lte: "<=",
  };
  return labels[operator] || operator;
}

function entityLabel(entityType) {
  return entityType === "plan" ? "计划" : "账户";
}

function planStatusTone(statusText) {
  if (statusText === "投放中") return "live";
  if (statusText === "已暂停") return "paused";
  if (statusText === "系统暂停") return "system";
  if (statusText === "已删除") return "deleted";
  return "neutral";
}

function renderPlanStatusBadge(row) {
  const text = row.status_text || "未知状态";
  const tone = planStatusTone(text);
  const title = row.status_code_text || `${row.status || ""} / ${row.opt_status || ""}`.trim();
  const sub = row.opt_status_label && row.opt_status_label !== text ? `<span class="status-sub">${escapeHtml(row.opt_status_label)}</span>` : "";
  return `
    <div class="status-stack" title="${escapeHtml(title)}">
      <span class="pill status-pill ${tone}">${escapeHtml(text)}</span>
      ${sub}
    </div>
  `;
}

function marketingGoalTone(goalText) {
  if (goalText === "商品全域推广") return "product";
  if (goalText === "直播间全域推广") return "live-room";
  return "neutral";
}

function renderMarketingGoalBadge(row) {
  const text = row.marketing_goal_text || row.marketing_goal_label || row.marketing_goal || "未设置";
  const tone = marketingGoalTone(text);
  const title = row.marketing_goal || text;
  return `<span class="pill marketing-goal-pill ${tone}" title="${escapeHtml(title)}">${escapeHtml(text)}</span>`;
}

function notificationChannelOptions(current) {
  const options = ["feishu", "slack", "telegram", "email", "dingtalk"];
  if (current && !options.includes(current)) {
    options.push(current);
  }
  return options;
}

function describeNotificationTarget(settings) {
  const channel = String(settings?.channel || "").trim().toLowerCase();
  const target = String(settings?.target || "").trim();
  if (!target) {
    return {
      label: "未设置",
      detail: "当前还没有配置外发接收对象。",
    };
  }
  if (channel === "feishu") {
    if (target.startsWith("oc_")) {
      return { label: "飞书群聊", detail: "已配置飞书群聊接收目标。" };
    }
    if (target.startsWith("ou_")) {
      return { label: "飞书成员", detail: "已配置飞书成员接收目标。" };
    }
    return { label: "飞书目标", detail: "已配置飞书接收对象。" };
  }
  if (channel === "dingtalk") {
    return { label: "钉钉目标", detail: "已配置钉钉接收对象。" };
  }
  if (channel === "slack") {
    return { label: "Slack 目标", detail: "已配置 Slack 接收对象。" };
  }
  if (channel === "telegram") {
    return { label: "Telegram 目标", detail: "已配置 Telegram 接收对象。" };
  }
  if (channel === "email" || target.includes("@")) {
    return { label: "邮箱接收", detail: "已配置邮箱通知目标。" };
  }
  return { label: "已配置目标", detail: "当前渠道已经设置接收对象。" };
}

function renderNotificationSettings(settings) {
  const channelSelect = notificationForm.querySelector('select[name="channel"]');
  const channelValue = String(settings?.channel || "feishu");
  channelSelect.innerHTML = notificationChannelOptions(channelValue)
    .map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(channelLabel(option))}</option>`)
    .join("");

  notificationForm.querySelector('input[name="enabled"]').checked = Boolean(settings?.enabled);
  channelSelect.value = channelValue;
  notificationForm.querySelector('input[name="account"]').value = settings?.account || "default";
  notificationForm.querySelector('input[name="target"]').value = settings?.target || "";
  notificationForm.querySelector('input[name="alert_enabled"]').checked = Boolean(settings?.alert_enabled);
  notificationForm.querySelector('input[name="alert_batch_size"]').value = settings?.alert_batch_size || 6;

  const targetInfo = describeNotificationTarget(settings);
  notificationStatus.innerHTML = `
    <div class="notify-inline-bar">
      <span class="notify-status-badge ${settings?.enabled ? "on" : "off"}">${settings?.enabled ? "通知开启" : "通知关闭"}</span>
      <span class="pill">${escapeHtml(channelLabel(settings?.channel || "-"))}</span>
      <span class="pill">${escapeHtml(targetInfo.label)}</span>
      <span class="pill">${settings?.alert_enabled ? `告警 ${formatNumber(settings?.alert_batch_size || 6)} 条` : "告警关闭"}</span>
    </div>
    <p class="notify-inline-copy">${escapeHtml(targetInfo.detail)} ${settings?.alert_enabled ? `当前会按每批 ${formatNumber(settings?.alert_batch_size || 6)} 条的方式发送阈值告警。` : "当前只保留页面内提醒，不对外推送。"} </p>
  `;
}

function renderSignalOverview(settings, rules) {
  const enabledRules = (rules || []).filter((item) => item.enabled).length;
  const totalRules = (rules || []).length;
  const planRules = (rules || []).filter((item) => item.enabled && item.entity_type === "plan").length;
  const accountRules = (rules || []).filter((item) => item.enabled && item.entity_type === "account").length;
  const targetInfo = describeNotificationTarget(settings);
  signalOverview.innerHTML = `
    <article class="signal-summary-card">
      <span class="signal-summary-label">通知</span>
      <strong>${settings?.enabled ? "已开启" : "已关闭"}</strong>
      <span class="signal-summary-sub">${escapeHtml(channelLabel(settings?.channel || "-"))} / ${escapeHtml(targetInfo.label)}</span>
    </article>
    <article class="signal-summary-card">
      <span class="signal-summary-label">规则</span>
      <strong class="mono">${formatNumber(enabledRules)}</strong>
      <span class="signal-summary-sub">共 ${formatNumber(totalRules)} 条 · 计划 ${formatNumber(planRules)} · 账户 ${formatNumber(accountRules)}</span>
    </article>
    <article class="signal-summary-card">
      <span class="signal-summary-label">告警</span>
      <strong>${settings?.alert_enabled ? `${formatNumber(settings?.alert_batch_size || 6)} 条` : "关闭"}</strong>
      <span class="signal-summary-sub">${settings?.alert_enabled ? "命中后批量发送" : "仅保留页面提醒"}</span>
    </article>
  `;
}

function normalizeRangeKey(value) {
  return Object.prototype.hasOwnProperty.call(RANGE_LABELS, value) ? value : "day";
}

function performanceFilterKey(filter) {
  const normalized = normalizeRangeFilter(filter);
  if (normalized.mode === "custom") {
    return `custom:${normalized.start}:${normalized.end}`;
  }
  return normalized.mode;
}

function sectionFilter(sectionKey) {
  return normalizeRangeFilter(state.performanceFilters[sectionKey] || { mode: "day" });
}

function setSectionFilter(sectionKey, nextFilter) {
  const config = PERFORMANCE_SECTION_CONFIG[sectionKey];
  if (!config) return;
  const current = sectionFilter(sectionKey);
  const fallbackMode = current.mode === "custom" ? "day" : current.mode;
  const normalized = normalizeRangeFilter(nextFilter, fallbackMode);
  state.performanceFilters[sectionKey] = normalized;
  saveRangeFilter(config.storageKey, normalized);
}

function setActiveView(view) {
  const next = String(view || "overview");
  state.activeView = next;
  savePreference("active-view", next);
  if (viewTabs) {
    viewTabs.querySelectorAll(".view-tab").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === next);
    });
  }
  viewSections.forEach((section) => {
    section.classList.toggle("is-active", section.dataset.view === next);
  });
}

function renderRangeSwitch(container, activeRange) {
  if (!container) return;
  container.querySelectorAll(".range-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.range === activeRange);
  });
}

function syncSectionRangeControls(sectionKey) {
  const config = PERFORMANCE_SECTION_CONFIG[sectionKey];
  if (!config) return;
  const filter = sectionFilter(sectionKey);
  renderRangeSwitch(config.switchEl, filter.mode);
  if (config.startEl && document.activeElement !== config.startEl) config.startEl.value = filter.start || "";
  if (config.endEl && document.activeElement !== config.endEl) config.endEl.value = filter.end || "";
}

function formatDateWindowMeta(payload) {
  if (!payload) {
    return "统计范围：加载中";
  }
  const label = payload.range_label || RANGE_LABELS[payload.range_key] || "当前";
  if (payload.range_key === "custom" && payload.query_start_date && payload.query_end_date) {
    return `统计范围：${label} · ${payload.query_start_date} 至 ${payload.query_end_date}`;
  }
  return `统计范围：${label} · ${payload.window_start} - ${payload.window_end}`;
}

function rangePayload(filter) {
  return state.rangePayloads[performanceFilterKey(filter)] || null;
}

function rangeLabel(filter) {
  const normalized = normalizeRangeFilter(filter);
  if (normalized.mode === "custom") {
    return "所选区间";
  }
  const payload = rangePayload(normalized);
  return payload?.range_label || RANGE_LABELS[normalized.mode] || "当前";
}

function renderAlertSummary(events) {
  if (!events.length) {
    alertSummary.innerHTML = `
      <div class="alert-summary-card spotlight calm">
        <div class="summary-topline">
          <span class="summary-chip">当前状态</span>
          <span class="summary-chip subtle">平稳</span>
        </div>
        <div class="summary-value">暂无异常提醒</div>
        <div class="summary-sub">最近没有命中告警规则，当前更适合关注账户和计划表现变化。</div>
        <div class="summary-metric-row">
          <div><span>待处理</span><strong class="mono">0</strong></div>
          <div><span>最新状态</span><strong>正常</strong></div>
          <div><span>提醒对象</span><strong>-</strong></div>
        </div>
      </div>
      <div class="alert-summary-card stat">
        <div class="summary-label">待处理</div>
        <div class="summary-value mono">0</div>
        <div class="summary-sub">当前没有待外发的提醒</div>
      </div>
      <div class="alert-summary-card stat">
        <div class="summary-label">处理节奏</div>
        <div class="summary-value">观察中</div>
        <div class="summary-sub">等待新触发后再进入重点处理</div>
      </div>
    `;
    return;
  }
  const pendingCount = events.filter((item) => item.status === "pending").length;
  const latest = events[0];
  const latestValue = latest.metric === "roi"
    ? formatRate(latest.current_value)
    : latest.metric === "order_count"
      ? formatNumber(latest.current_value)
      : formatMoney(latest.current_value);
  alertSummary.innerHTML = `
    <div class="alert-summary-card spotlight ${latest.status === "pending" ? "hot" : ""}">
      <div class="summary-topline">
        <span class="summary-chip">${latest.status === "pending" ? "优先处理" : "最近已发送"}</span>
        <span class="summary-chip subtle">${escapeHtml(entityLabel(latest.entity_type))}</span>
      </div>
      <div class="summary-label">当前最值得盯的对象</div>
      <div class="summary-value compact">${escapeHtml(latest.entity_name)}</div>
      <div class="summary-sub">${escapeHtml(metricLabel(latest.metric))} ${escapeHtml(operatorLabel(latest.operator))} ${escapeHtml(latest.threshold)} · ${escapeHtml(latest.created_at)}</div>
      <div class="summary-metric-row">
        <div><span>当前值</span><strong class="mono">${latestValue}</strong></div>
        <div><span>消耗</span><strong class="mono">${formatMoney(latest.stat_cost)}</strong></div>
        <div><span>ROI</span><strong class="mono">${formatRate(latest.roi)}</strong></div>
        <div><span>订单</span><strong class="mono">${formatNumber(latest.order_count)}</strong></div>
      </div>
    </div>
    <div class="alert-summary-card stat">
      <div class="summary-label">待处理</div>
      <div class="summary-value mono">${formatNumber(pendingCount)}</div>
      <div class="summary-sub">${pendingCount ? "建议尽快人工复核" : "当前都已处理或已发送"}</div>
    </div>
    <div class="alert-summary-card stat">
      <div class="summary-label">最近触发</div>
      <div class="summary-value">${escapeHtml(metricLabel(latest.metric))}</div>
      <div class="summary-sub">${escapeHtml(entityLabel(latest.entity_type))} · ${escapeHtml(latest.created_at)}</div>
    </div>
  `;
}

function renderKpis(latest) {
  const summary = latest?.summary || {};
  const cards = [
    ["活跃账户", formatNumber(summary.active_account_count), `总账户 ${formatNumber(summary.account_count)}`],
    ["活跃计划", formatNumber(summary.active_plan_count), `总计划 ${formatNumber(summary.plan_count)}`],
    ["活跃商品", formatNumber(summary.active_product_count), `总商品 ${formatNumber(summary.product_count)}`],
    ["活跃员工", formatNumber(summary.active_employee_count), `总员工 ${formatNumber(summary.employee_count)}`],
  ];
  kpiGrid.innerHTML = cards.map(([label, value, sub]) => `
    <article class="kpi-card">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value mono">${value}</div>
      <div class="kpi-sub">${sub}</div>
    </article>
  `).join("");
}

function renderOverviewHero(latest) {
  if (!overviewHeroCard) return;
  const summary = latest?.summary || {};
  const accountFailures = Number(summary.account_failures || 0);
  const planFailures = Number(summary.plan_failures || 0);
  const accountTone = accountFailures ? "danger" : "ok";
  const planTone = planFailures ? "danger" : "ok";
  overviewHeroCard.innerHTML = `
    <div class="overview-hero-head">
      <div>
        <p class="panel-kicker">经营总览</p>
        <h2>今日投放概况</h2>
        <p class="overview-hero-copy">先看消耗、支付、订单和 ROI，再决定进入哪个账户或计划处理。</p>
      </div>
      <div class="overview-hero-pills">
        <span class="system-pill ${accountTone === "danger" ? "danger" : ""}">${accountFailures ? `账户异常 ${formatNumber(accountFailures)}` : "账户查询正常"}</span>
        <span class="system-pill ${planTone === "danger" ? "danger" : ""}">${planFailures ? `计划异常 ${formatNumber(planFailures)}` : "计划查询正常"}</span>
      </div>
    </div>
    <div class="overview-hero-metrics">
      <article class="overview-hero-metric">
        <span>今日消耗</span>
        <strong class="mono">${formatMoney(summary.stat_cost)}</strong>
      </article>
      <article class="overview-hero-metric">
        <span>支付金额</span>
        <strong class="mono">${formatMoney(summary.pay_amount)}</strong>
      </article>
      <article class="overview-hero-metric">
        <span>订单数</span>
        <strong class="mono">${formatNumber(summary.order_count)}</strong>
      </article>
      <article class="overview-hero-metric accent">
        <span>整体 ROI</span>
        <strong class="mono">${formatRate(summary.roi)}</strong>
      </article>
    </div>
    <div class="overview-hero-foot">
      <div class="overview-foot-stat"><span>活跃账户</span><strong class="mono">${formatNumber(summary.active_account_count)}</strong></div>
      <div class="overview-foot-stat"><span>活跃计划</span><strong class="mono">${formatNumber(summary.active_plan_count)}</strong></div>
      <div class="overview-foot-stat"><span>活跃商品</span><strong class="mono">${formatNumber(summary.active_product_count)}</strong></div>
      <div class="overview-foot-stat"><span>活跃员工</span><strong class="mono">${formatNumber(summary.active_employee_count)}</strong></div>
    </div>
  `;
}

function renderSystemCards(latest, extendedSync, tokenInfo) {
  const summary = latest?.summary || {};
  const hardAccountFailures = Number(summary.account_failures || 0);
  const planFailures = Number(summary.plan_failures || 0);
  const failureTone = hardAccountFailures > 0 || planFailures > 0 ? "danger" : "ok";
  const detailStatus = extendedSync?.status || "未同步";
  const detailTone = detailStatus === "ok" ? "ok" : detailStatus === "partial" ? "warn" : "danger";
  const tokenAgeText = tokenInfo?.updated_at ? formatAgoFromEpoch(tokenInfo.updated_at) : "未记录";

  if (heroStatusText) {
    heroStatusText.textContent = latest?.snapshot_time || "等待首次同步";
  }
  if (heroStatusHint) {
    heroStatusHint.textContent = `1 分钟刷新 · token ${tokenAgeText}`;
  }

  systemStatusCard.innerHTML = `
    <div class="system-card-head">
      <span class="system-card-label">主快照状态</span>
      <span class="system-pill ${failureTone === "danger" ? "danger" : ""}">${hardAccountFailures || planFailures ? "有异常" : "运行正常"}</span>
    </div>
    <div class="system-card-value">${escapeHtml(latest?.snapshot_time || "等待首次同步")}</div>
    <div class="system-card-copy">分钟级主快照是总览页基准，账户汇总异常时会自动回退到计划聚合口径。</div>
    <div class="system-stat-grid">
      <div class="system-stat"><span>账户异常</span><strong class="mono">${formatNumber(hardAccountFailures)}</strong></div>
      <div class="system-stat"><span>计划异常</span><strong class="mono">${formatNumber(planFailures)}</strong></div>
      <div class="system-stat"><span>token 更新</span><strong>${escapeHtml(tokenAgeText)}</strong></div>
      <div class="system-stat"><span>账户汇总</span><strong>${hardAccountFailures ? "已回退" : "直查正常"}</strong></div>
    </div>
  `;

  detailSyncCard.innerHTML = `
    <div class="system-card-head">
      <span class="system-card-label">素材与明细同步</span>
      <span class="system-pill ${detailTone === "warn" ? "warn" : detailTone === "danger" ? "danger" : ""}">${escapeHtml(detailStatus === "ok" ? "完整" : detailStatus === "partial" ? "部分完成" : "未同步")}</span>
    </div>
    <div class="system-card-value">${escapeHtml(extendedSync?.snapshot_time || "等待明细同步")}</div>
    <div class="system-card-copy">计划详情、商品、素材、首发视频标记按 10 分钟级同步，用于计划侧栏和后续素材排名。</div>
    <div class="system-stat-grid">
      <div class="system-stat"><span>计划数</span><strong class="mono">${formatNumber(extendedSync?.plan_count || 0)}</strong></div>
      <div class="system-stat"><span>商品行</span><strong class="mono">${formatNumber(extendedSync?.product_row_count || 0)}</strong></div>
      <div class="system-stat"><span>素材行</span><strong class="mono">${formatNumber(extendedSync?.material_row_count || 0)}</strong></div>
      <div class="system-stat"><span>错误数</span><strong class="mono">${formatNumber(extendedSync?.error_count || 0)}</strong></div>
    </div>
  `;
}

function renderAlerts(events) {
  renderAlertSummary(events);
  if (!events.length) {
    alertStream.className = "alert-stream empty";
    alertStream.textContent = "暂无告警记录";
    return;
  }
  alertStream.className = "alert-stream";
  alertStream.innerHTML = events.slice(0, 8).map((item) => `
    <article class="alert-item ${item.status === "pending" ? "is-pending" : "is-sent"}">
      <div class="alert-topline">
        <div class="alert-badges">
          <span class="alert-kind">${escapeHtml(entityLabel(item.entity_type))}</span>
          <span class="alert-metric">${escapeHtml(metricLabel(item.metric))}</span>
          <span class="alert-status ${item.status === "pending" ? "pending" : "sent"}">${escapeHtml(item.status === "pending" ? "待处理" : "已发送")}</span>
        </div>
        <time class="alert-time mono">${escapeHtml(item.created_at)}</time>
      </div>
      <div class="alert-title-row">
        <h3>${escapeHtml(item.entity_name)}</h3>
        <div class="alert-rule mono">${escapeHtml(metricLabel(item.metric))} ${escapeHtml(operatorLabel(item.operator))} ${escapeHtml(item.threshold)}</div>
      </div>
      <div class="alert-metrics compact">
        <div><span>当前值</span><strong class="mono">${item.metric === "roi" ? formatRate(item.current_value) : item.metric === "order_count" ? formatNumber(item.current_value) : formatMoney(item.current_value)}</strong></div>
        <div><span>消耗</span><strong class="mono">${formatMoney(item.stat_cost)}</strong></div>
        <div><span>ROI</span><strong class="mono">${formatRate(item.roi)}</strong></div>
      </div>
      <div class="alert-footline">
        <span>支付 ${formatMoney(item.pay_amount)}</span>
        <span>订单 ${formatNumber(item.order_count)}</span>
      </div>
      <p class="alert-message">${escapeHtml(item.message)}</p>
    </article>
  `).join("");
}

function makeHeader(columns, sortState, storageKey, onSort) {
  return `
    <thead>
      <tr>
        ${columns.map((column) => {
          const active = sortState.key === column.key;
          const hint = !column.sortable ? "" : active ? (sortState.dir === "asc" ? "↑" : "↓") : "↕";
          return `<th data-key="${column.key}" data-sort-hint="${hint}" class="${column.sortable ? "th-sort" : ""}">${column.label}</th>`;
        }).join("")}
      </tr>
    </thead>
  `;
}

function sortRows(rows, sortState) {
  return [...rows].sort((left, right) => compareValues(left[sortState.key], right[sortState.key], sortState.dir));
}

function toggleSort(current, key, fallbackDir = "desc") {
  if (current.key === key) {
    return { key, dir: current.dir === "desc" ? "asc" : "desc" };
  }
  return { key, dir: fallbackDir };
}

function renderAccountTable(accounts) {
  const query = accountSearch.value.trim().toLowerCase();
  const rows = accounts.filter((row) => row.advertiser_name.toLowerCase().includes(query));
  const columns = [
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "status_text", label: "状态", sortable: false },
  ];
  const sorted = sortRows(rows.map((row) => ({
    ...row,
    status_text: !row.ok ? "查询失败" : String(row.error || "").startsWith("fallback:") ? "计划聚合" : "正常",
  })), state.accountSort);

  accountTable.innerHTML = `
    ${makeHeader(columns, state.accountSort, "account-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr>
          <td>${escapeHtml(row.advertiser_name)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td><span class="pill">${escapeHtml(row.status_text)}</span></td>
        </tr>
      `).join("")}
    </tbody>
  `;

  accountTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.accountSort = toggleSort(state.accountSort, key);
      saveSort("account-sort", state.accountSort);
      renderAccountTable(accounts);
    });
  });
}

function clearEmployeeDetail() {
  employeeDetail.className = "detail-panel empty";
  employeeDetail.textContent = "点击员工行，查看该员工当前负责的计划规模和核心表现。";
}

function clearProductDetail() {
  productDetail.className = "detail-panel empty";
  productDetail.textContent = "点击商品行，查看该商品对应的计划规模、账户覆盖和代表计划。";
}

function renderEmployeeDetail(employeeName) {
  const breakdownFilter = sectionFilter("breakdown");
  const rows = rangePayload(breakdownFilter)?.employees || [];
  const row = rows.find((item) => item.employee_name === employeeName);
  if (!row) return;
  employeeDetail.className = "detail-panel";
  employeeDetail.innerHTML = `
    <div class="detail-stats">
      <div class="detail-stat detail-stat-wide"><span class="label">员工主体</span><span class="value compact">${escapeHtml(row.employee_name)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
      <div class="detail-stat"><span class="label">覆盖账户</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
      <div class="detail-stat"><span class="label">覆盖商品</span><span class="value mono">${formatNumber(row.product_count)}</span></div>
      <div class="detail-stat"><span class="label">总计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
      <div class="detail-stat"><span class="label">活跃计划数</span><span class="value mono">${formatNumber(row.active_plan_count)}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">代表计划</span><span class="value compact">${escapeHtml(row.top_plan_name || "暂无代表计划")}</span></div>
    </div>
  `;
}

function renderProductDetail(productKey) {
  const breakdownFilter = sectionFilter("breakdown");
  const rows = rangePayload(breakdownFilter)?.products || [];
  const row = rows.find((item) => item.product_key === productKey);
  if (!row) return;
  productDetail.className = "detail-panel";
  productDetail.innerHTML = `
    <div class="detail-stats">
      <div class="detail-stat detail-stat-wide"><span class="label">商品名称</span><span class="value compact">${escapeHtml(row.product_name)}</span></div>
      <div class="detail-stat"><span class="label">商品 ID</span><span class="value compact mono">${escapeHtml(row.product_id || "-")}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
      <div class="detail-stat"><span class="label">覆盖账户</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
      <div class="detail-stat"><span class="label">覆盖员工</span><span class="value mono">${formatNumber(row.employee_count)}</span></div>
      <div class="detail-stat"><span class="label">总计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
      <div class="detail-stat"><span class="label">活跃计划数</span><span class="value mono">${formatNumber(row.active_plan_count)}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">代表计划</span><span class="value compact">${escapeHtml(row.top_plan_name || "暂无代表计划")}</span></div>
    </div>
  `;
}

function setSelectedEmployee(employeeName) {
  state.selectedEmployeeName = employeeName;
  if (!employeeName) {
    clearEmployeeDetail();
    return;
  }
  renderEmployeeDetail(employeeName);
}

function setSelectedProduct(productKey) {
  state.selectedProductKey = productKey;
  if (!productKey) {
    clearProductDetail();
    return;
  }
  renderProductDetail(productKey);
}

function syncSelectedEmployee(rows) {
  if (!state.selectedEmployeeName) {
    clearEmployeeDetail();
    return;
  }
  const exists = rows.some((item) => item.employee_name === state.selectedEmployeeName);
  if (!exists) {
    setSelectedEmployee(null);
    return;
  }
  renderEmployeeDetail(state.selectedEmployeeName);
}

function syncSelectedProduct(rows) {
  if (!state.selectedProductKey) {
    clearProductDetail();
    return;
  }
  const exists = rows.some((item) => item.product_key === state.selectedProductKey);
  if (!exists) {
    setSelectedProduct(null);
    return;
  }
  renderProductDetail(state.selectedProductKey);
}

function renderEmployeeInteractions(rows) {
  employeeTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedEmployee(String(rowEl.dataset.employeeName || ""));
      renderEmployeeTable(rows);
    });
  });
}

function renderProductInteractions(rows) {
  productTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedProduct(String(rowEl.dataset.productKey || ""));
      renderProductTable(rows);
    });
  });
}

function renderEmployeeTable(rows) {
  const query = employeeSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = [row.employee_name, row.top_plan_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "employee_name", label: "员工", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
    { key: "product_count", label: "商品数", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.employeeSort);

  employeeTable.innerHTML = `
    ${makeHeader(columns, state.employeeSort, "employee-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-employee-name="${escapeHtml(row.employee_name)}" class="${state.selectedEmployeeName === row.employee_name ? "active-row" : ""}">
          <td>${escapeHtml(row.employee_name)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatNumber(row.advertiser_count)}</td>
          <td class="mono">${formatNumber(row.product_count)}</td>
          <td class="mono">${formatNumber(row.plan_count)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  employeeTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.employeeSort = toggleSort(state.employeeSort, key);
      saveSort("employee-sort", state.employeeSort);
      renderEmployeeTable(rows);
    });
  });

  renderEmployeeInteractions(rows);
}

function renderProductTable(rows) {
  const query = productSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = [row.product_name, row.product_id, row.top_plan_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "product_name", label: "商品", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
    { key: "employee_count", label: "员工数", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.productSort);

  productTable.innerHTML = `
    ${makeHeader(columns, state.productSort, "product-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-product-key="${escapeHtml(row.product_key)}" class="${state.selectedProductKey === row.product_key ? "active-row" : ""}">
          <td>${escapeHtml(row.product_name)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatNumber(row.advertiser_count)}</td>
          <td class="mono">${formatNumber(row.employee_count)}</td>
          <td class="mono">${formatNumber(row.plan_count)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  productTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.productSort = toggleSort(state.productSort, key);
      saveSort("product-sort", state.productSort);
      renderProductTable(rows);
    });
  });

  renderProductInteractions(rows);
}

function clearMaterialDetail() {
  materialDetail.className = "detail-panel empty";
  materialDetail.textContent = "点击素材行，查看该素材覆盖的账户、计划和当前核心表现。";
}

function renderMaterialDetail(materialKey) {
  const rows = state.materialPayload?.items || [];
  const row = rows.find((item) => item.material_key === materialKey);
  if (!row) return;
  materialDetail.className = "detail-panel";
  materialDetail.innerHTML = `
    <div class="detail-stats">
      <div class="detail-stat detail-stat-wide"><span class="label">素材名称</span><span class="value compact">${escapeHtml(row.material_name)}</span></div>
      <div class="detail-stat"><span class="label">素材 ID</span><span class="value compact mono">${escapeHtml(row.material_id || "-")}</span></div>
      <div class="detail-stat"><span class="label">素材类型</span><span class="value compact">${escapeHtml(row.material_type || "-")}</span></div>
      <div class="detail-stat"><span class="label">视频 ID</span><span class="value compact mono">${escapeHtml(row.video_id || "-")}</span></div>
      <div class="detail-stat"><span class="label">最近一次素材同步消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
      <div class="detail-stat"><span class="label">最近一次素材同步支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">最近一次素材同步订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
      <div class="detail-stat"><span class="label">最近一次素材同步 ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
      <div class="detail-stat"><span class="label">覆盖账户数</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
      <div class="detail-stat"><span class="label">覆盖计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
      <div class="detail-stat"><span class="label">首发视频</span><span class="value compact">${row.is_original ? "是" : "否"}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">代表计划 / 账户</span><span class="value compact">${escapeHtml(row.top_plan_name || "-")}<br /><span class="detail-sub">${escapeHtml(row.top_account_name || "-")}</span></span></div>
    </div>
  `;
}

function setSelectedMaterial(materialKey) {
  state.selectedMaterialKey = materialKey;
  if (!materialKey) {
    clearMaterialDetail();
    return;
  }
  renderMaterialDetail(materialKey);
}

function syncSelectedMaterial(rows) {
  if (!state.selectedMaterialKey) {
    clearMaterialDetail();
    return;
  }
  const exists = rows.some((item) => item.material_key === state.selectedMaterialKey);
  if (!exists) {
    setSelectedMaterial(null);
    return;
  }
  renderMaterialDetail(state.selectedMaterialKey);
}

function renderMaterialInteractions(rows) {
  materialTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedMaterial(String(rowEl.dataset.materialKey || ""));
      renderMaterialTable(rows);
    });
  });
}

function renderMaterialTable(rows) {
  const query = materialSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = [row.material_name, row.material_id, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "material_name", label: "素材", sortable: true },
    { key: "material_type", label: "类型", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.materialSort);
  materialTable.innerHTML = `
    ${makeHeader(columns, state.materialSort, "material-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-material-key="${escapeHtml(row.material_key)}" class="${state.selectedMaterialKey === row.material_key ? "active-row" : ""}">
          <td>${escapeHtml(row.material_name)}</td>
          <td><span class="pill">${escapeHtml(row.material_type || "-")}</span></td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatNumber(row.plan_count)}</td>
          <td class="mono">${formatNumber(row.advertiser_count)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  materialTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.materialSort = toggleSort(state.materialSort, key);
      saveSort("material-sort", state.materialSort);
      renderMaterialTable(rows);
    });
  });
  renderMaterialInteractions(rows);
}

async function fetchMaterialRankings(force = false) {
  if (!force && state.materialPayload) {
    return state.materialPayload;
  }
  const response = await fetch("/api/material-rankings");
  if (!response.ok) {
    throw new Error("material rankings fetch failed");
  }
  state.materialPayload = await response.json();
  return state.materialPayload;
}

function fillPlanAccountFilter(accountNames) {
  const current = planAccountFilter.value;
  const options = ['<option value="">全部账户</option>']
    .concat(accountNames.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`));
  planAccountFilter.innerHTML = options.join("");
  if ([...planAccountFilter.options].some((option) => option.value === current)) {
    planAccountFilter.value = current;
  }
}

function clearPlanAssetSummary() {
  planAssetSummary.className = "detail-panel empty";
  planAssetSummary.textContent = "点击计划行，查看该计划最新同步到本地的商品、素材和视频摘要。";
}

function planAssetCacheKey(adId, snapshotTime) {
  return `${snapshotTime || "latest"}:${adId}`;
}

async function fetchPlanAssets(adId) {
  const snapshotTime = state.payload?.latest?.snapshot_time || "";
  const cacheKey = planAssetCacheKey(adId, snapshotTime);
  if (state.planAssetCache[cacheKey]) {
    return state.planAssetCache[cacheKey];
  }
  const query = snapshotTime ? `?snapshot_time=${encodeURIComponent(snapshotTime)}` : "";
  const response = await fetch(`/api/plans/${encodeURIComponent(adId)}/assets${query}`);
  if (!response.ok) {
    throw new Error("assets fetch failed");
  }
  const payload = await response.json();
  state.planAssetCache[cacheKey] = payload;
  return payload;
}

function renderPlanAssetSummaryPayload(payload) {
  const products = payload?.products || [];
  const materials = payload?.materials || [];
  const typeCount = {};
  for (const item of materials) {
    const type = String(item.material_type || "OTHER");
    typeCount[type] = (typeCount[type] || 0) + 1;
  }
  const topProducts = [...products]
    .sort((left, right) => compareValues(left.order_count, right.order_count, "desc") || compareValues(left.pay_amount, right.pay_amount, "desc"))
    .slice(0, 3);
  const topMaterials = [...materials]
    .sort((left, right) => compareValues(left.order_count, right.order_count, "desc") || compareValues(left.pay_amount, right.pay_amount, "desc"))
    .slice(0, 4);
  const typeTags = Object.entries(typeCount)
    .sort((left, right) => Number(right[1]) - Number(left[1]))
    .map(([type, count]) => `<span class="pill">${escapeHtml(type)} ${formatNumber(count)}</span>`)
    .join("");

  planAssetSummary.className = "detail-panel";
  planAssetSummary.innerHTML = `
    <div class="asset-group">
      <div class="asset-group-head">
        <h4>素材与商品摘要</h4>
        <span>基于最近一次明细同步：${escapeHtml(payload?.snapshot_time || "-")}</span>
      </div>
      <div class="asset-card-grid">
        <div class="asset-mini-card"><span>商品行</span><strong class="mono">${formatNumber(products.length)}</strong></div>
        <div class="asset-mini-card"><span>素材行</span><strong class="mono">${formatNumber(materials.length)}</strong></div>
        <div class="asset-mini-card"><span>首发视频</span><strong class="mono">${formatNumber(payload?.originalVideoCount || 0)}</strong></div>
      </div>
    </div>
    <div class="asset-group">
      <div class="asset-group-head">
        <h4>素材类型分布</h4>
        <span>用于判断当前计划主要依赖的视频/图片/标题类型</span>
      </div>
      <div class="asset-tag-row">${typeTags || '<span class="pill">暂无素材</span>'}</div>
    </div>
    <div class="asset-group">
      <div class="asset-group-head">
        <h4>代表商品</h4>
        <span>按订单数排序</span>
      </div>
      <div class="asset-list">
        ${topProducts.length ? topProducts.map((item) => `
          <article class="asset-item">
            <div class="asset-item-top">
              <div class="asset-item-title">${escapeHtml(item.product_name || item.product_id || "未关联商品")}</div>
              <span class="pill">${formatNumber(item.order_count)} 单</span>
            </div>
            <div class="asset-item-meta">
              <span>支付 ${formatMoney(item.pay_amount)}</span>
              <span>ROI ${formatRate(item.roi)}</span>
              <span>消耗 ${formatMoney(item.stat_cost)}</span>
            </div>
          </article>
        `).join("") : '<div class="asset-item">当前没有同步到商品明细。</div>'}
      </div>
    </div>
    <div class="asset-group">
      <div class="asset-group-head">
        <h4>代表素材</h4>
        <span>按订单数排序，视频会标记首发</span>
      </div>
      <div class="asset-list">
        ${topMaterials.length ? topMaterials.map((item) => `
          <article class="asset-item">
            <div class="asset-item-top">
              <div class="asset-item-title">${escapeHtml(item.material_name || item.material_id || "未命名素材")}</div>
              <div class="asset-tag-row">
                <span class="pill">${escapeHtml(item.material_type || "OTHER")}</span>
                ${item.is_original ? '<span class="pill">首发</span>' : ""}
              </div>
            </div>
            <div class="asset-item-meta">
              <span>订单 ${formatNumber(item.order_count)}</span>
              <span>支付 ${formatMoney(item.pay_amount)}</span>
              <span>ROI ${formatRate(item.roi)}</span>
            </div>
          </article>
        `).join("") : '<div class="asset-item">当前没有同步到素材明细。</div>'}
      </div>
    </div>
  `;
}

async function renderPlanAssets(adId) {
  clearPlanAssetSummary();
  try {
    const payload = await fetchPlanAssets(adId);
    renderPlanAssetSummaryPayload(payload);
  } catch {
    planAssetSummary.className = "detail-panel empty";
    planAssetSummary.textContent = "计划素材摘要加载失败，请稍后重试。";
  }
}

async function renderPlanDetail(adId) {
  const planFilter = sectionFilter("plan");
  const rows = rangePayload(planFilter)?.plans || [];
  const row = rows.find((item) => item.ad_id === adId);
  if (!row) return;
  const orderCost = Number(row.order_count || 0) > 0 ? Number(row.stat_cost || 0) / Number(row.order_count || 0) : null;
  const roiGap = Number(row.roi || 0) - Number(row.roi_goal || 0);
  const payGap = Number(row.pay_amount || 0) - Number(row.stat_cost || 0);
  const currentRangeLabel = rangeLabel(planFilter);
  planDetail.className = "detail-panel";
  planDetail.innerHTML = `
    <div class="detail-stats detail-stats-plan">
      <div class="detail-stat detail-stat-wide"><span class="label">计划名称</span><span class="value compact">${escapeHtml(row.ad_name)}</span></div>
      <div class="detail-stat"><span class="label">计划 ID</span><span class="value compact mono">${formatNumber(row.ad_id)}</span></div>
      <div class="detail-stat"><span class="label">账户 / ID</span><span class="value compact">${escapeHtml(row.advertiser_name)}<br /><span class="detail-sub mono">${formatNumber(row.advertiser_id)}</span></span></div>
      <div class="detail-stat"><span class="label">商品 / ID</span><span class="value compact">${escapeHtml(row.product_name || "-")}<br /><span class="detail-sub mono">${escapeHtml(row.product_id || "-")}</span></span></div>
      <div class="detail-stat"><span class="label">主播</span><span class="value compact">${escapeHtml(row.anchor_name || "-")}</span></div>
      <div class="detail-stat"><span class="label">营销目标</span><span class="value">${renderMarketingGoalBadge(row)}</span></div>
      <div class="detail-stat"><span class="label">投放状态</span><span class="value">${renderPlanStatusBadge(row)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(currentRangeLabel)}订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(currentRangeLabel)} ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
      <div class="detail-stat"><span class="label">目标 ROI</span><span class="value mono">${formatRate(row.roi_goal)}</span></div>
      <div class="detail-stat"><span class="label">ROI 差值</span><span class="value mono ${roiGap >= 0 ? "positive" : "negative"}">${roiGap >= 0 ? "+" : ""}${formatRate(roiGap)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(currentRangeLabel)}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
      <div class="detail-stat"><span class="label">${escapeHtml(currentRangeLabel)}支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">单均成本</span><span class="value mono">${orderCost === null ? "-" : formatMoney(orderCost)}</span></div>
      <div class="detail-stat"><span class="label">支付减消耗</span><span class="value mono ${payGap >= 0 ? "positive" : "negative"}">${payGap >= 0 ? "+" : ""}${formatMoney(payGap)}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">计划说明</span><span class="value compact">用于快速复核计划主体、商品、账户归属、目标值和当前表现；右侧同时展示最近一次同步到本地的素材与商品摘要。</span></div>
    </div>
  `;
  await renderPlanAssets(adId);
}

function clearPlanDetail() {
  planDetail.className = "detail-panel empty";
  planDetail.textContent = "点击计划行，查看该计划的投放字段、商品信息和当前状态。";
  clearPlanAssetSummary();
}

function setSelectedPlan(adId) {
  state.selectedPlanId = adId;
  if (!adId) {
    clearPlanDetail();
    return;
  }
  renderPlanDetail(adId);
}

function renderPlanInteractions(plans) {
  planTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedPlan(Number(rowEl.dataset.planId));
      renderPlanTable(plans);
    });
  });
}

function syncSelectedPlan(plans) {
  if (!state.selectedPlanId) {
    clearPlanDetail();
    return;
  }
  const exists = plans.some((item) => item.ad_id === state.selectedPlanId);
  if (!exists) {
    setSelectedPlan(null);
    return;
  }
  renderPlanDetail(state.selectedPlanId);
}

function renderPlanTable(plans) {
  if (state.planSort.key === "status") {
    state.planSort = { ...state.planSort, key: "status_text" };
    saveSort("plan-sort", state.planSort);
  }
  if (state.planSort.key === "marketing_goal") {
    state.planSort = { ...state.planSort, key: "marketing_goal_text" };
    saveSort("plan-sort", state.planSort);
  }
  const query = planSearch.value.trim().toLowerCase();
  const accountFilter = planAccountFilter.value;
  const rows = plans.filter((row) => {
    const haystack = [row.ad_name, row.product_name, row.advertiser_name, row.anchor_name].join(" ").toLowerCase();
    const matchQuery = haystack.includes(query);
    const matchAccount = !accountFilter || row.advertiser_name === accountFilter;
    return matchQuery && matchAccount;
  });
  const columns = [
    { key: "ad_name", label: "计划", sortable: true },
    { key: "product_name", label: "商品", sortable: true },
    { key: "marketing_goal_text", label: "营销目标", sortable: true },
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "anchor_name", label: "主播", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "roi_goal", label: "目标ROI", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "status_text", label: "投放状态", sortable: true },
  ];
  const enrichedRows = rows.map((row) => ({
    ...row,
    marketing_goal_text: row.marketing_goal_text || row.marketing_goal_label || row.marketing_goal || "-",
    status_text: row.status_text || `${row.status || ""}/${row.opt_status || ""}`,
  }));
  const sorted = sortRows(enrichedRows, state.planSort);

  planTable.innerHTML = `
    ${makeHeader(columns, state.planSort, "plan-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-plan-id="${row.ad_id}" class="${state.selectedPlanId === row.ad_id ? "active-row" : ""}">
          <td>${escapeHtml(row.ad_name)}</td>
          <td>${escapeHtml(row.product_name || "-")}</td>
          <td>${renderMarketingGoalBadge(row)}</td>
          <td>${escapeHtml(row.advertiser_name)}</td>
          <td>${escapeHtml(row.anchor_name || "-")}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatRate(row.roi_goal)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td>${renderPlanStatusBadge(row)}</td>
        </tr>
      `).join("")}
    </tbody>
  `;

  planTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.planSort = toggleSort(state.planSort, key);
      saveSort("plan-sort", state.planSort);
      renderPlanTable(plans);
    });
  });

  renderPlanInteractions(plans);
}

function renderRuleTable(rules) {
  ruleTable.innerHTML = `
    <thead>
      <tr>
        <th>对象</th>
        <th>指标</th>
        <th>规则</th>
        <th>最低消耗</th>
        <th>冷却</th>
        <th>状态</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${rules.map((rule) => `
        <tr>
          <td>${escapeHtml(entityLabel(rule.entity_type))}</td>
          <td>${escapeHtml(metricLabel(rule.metric))}</td>
          <td class="mono">${escapeHtml(operatorLabel(rule.operator))} ${escapeHtml(rule.threshold)}</td>
          <td class="mono">${formatMoney(rule.min_spend)}</td>
          <td class="mono">${formatNumber(rule.cooldown_minutes)} 分钟</td>
          <td><span class="pill">${rule.enabled ? "启用" : "关闭"}</span></td>
          <td>
            <button class="button ghost toggle-rule" data-id="${rule.id}">${rule.enabled ? "停用" : "启用"}</button>
            <button class="button ghost delete-rule" data-id="${rule.id}">删除</button>
          </td>
        </tr>
      `).join("")}
    </tbody>
  `;

  ruleTable.querySelectorAll(".toggle-rule").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = Number(button.dataset.id);
      const rule = rules.find((item) => item.id === id);
      if (!rule) return;
      await fetch(`/api/alert-rules/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity_type: rule.entity_type,
          metric: rule.metric,
          operator: rule.operator,
          threshold: rule.threshold,
          min_spend: rule.min_spend,
          cooldown_minutes: rule.cooldown_minutes,
          enabled: !rule.enabled,
          target_id: rule.target_id,
          note: rule.note,
        }),
      });
      await fetchDashboard();
    });
  });

  ruleTable.querySelectorAll(".delete-rule").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = Number(button.dataset.id);
      await fetch(`/api/alert-rules/${id}`, { method: "DELETE" });
      await fetchDashboard();
    });
  });
}

async function fetchPerformance(filter, force = false) {
  const normalized = normalizeRangeFilter(filter);
  const cacheKey = performanceFilterKey(normalized);
  if (!force && state.rangePayloads[cacheKey]) {
    return state.rangePayloads[cacheKey];
  }
  const params = new URLSearchParams();
  params.set("range", normalized.mode);
  if (normalized.mode === "custom") {
    params.set("start_date", normalized.start);
    params.set("end_date", normalized.end);
  }
  const response = await fetch(`/api/performance?${params.toString()}`).catch(() => null);
  if (!response || !response.ok) {
    const errorPayload = response ? await response.json().catch(() => ({})) : {};
    if (state.rangePayloads[cacheKey]) {
      return state.rangePayloads[cacheKey];
    }
    throw new Error(errorPayload.detail || `performance fetch failed for ${cacheKey}`);
  }
  const payload = await response.json();
  state.rangePayloads[cacheKey] = payload;
  return payload;
}

function renderPerformanceSections() {
  syncSectionRangeControls("account");
  syncSectionRangeControls("plan");
  syncSectionRangeControls("breakdown");

  const accountPayload = rangePayload(sectionFilter("account"));
  const planPayload = rangePayload(sectionFilter("plan"));
  const breakdownPayload = rangePayload(sectionFilter("breakdown"));

  accountRangeMeta.textContent = formatDateWindowMeta(accountPayload);
  planRangeMeta.textContent = formatDateWindowMeta(planPayload);
  breakdownRangeMeta.textContent = formatDateWindowMeta(breakdownPayload);

  renderAccountTable(accountPayload?.accounts || []);
  fillPlanAccountFilter((planPayload?.accounts || []).map((row) => row.advertiser_name));
  renderPlanTable(planPayload?.plans || []);
  renderEmployeeTable(breakdownPayload?.employees || []);
  renderProductTable(breakdownPayload?.products || []);
  syncSelectedPlan(planPayload?.plans || []);
  syncSelectedEmployee(breakdownPayload?.employees || []);
  syncSelectedProduct(breakdownPayload?.products || []);
}

async function refreshPerformanceSections(force = false) {
  const uniqueFilters = new Map();
  ["account", "plan", "breakdown"].forEach((sectionKey) => {
    const filter = sectionFilter(sectionKey);
    uniqueFilters.set(performanceFilterKey(filter), filter);
  });
  await Promise.all([...uniqueFilters.values()].map((filter) => fetchPerformance(filter, force)));
  renderPerformanceSections();
}

async function refreshMaterialSection(force = false) {
  const payload = await fetchMaterialRankings(force);
  renderMaterialTable(payload?.items || []);
  syncSelectedMaterial(payload?.items || []);
  const meta = payload?.meta || {};
  const syncText = payload?.snapshot_time
    ? `最近一次明细同步：${payload.snapshot_time} · 素材 ${formatNumber(meta.material_row_count || 0)} 行 · 错误 ${formatNumber(meta.error_count || 0)}`
    : "素材榜基于最近一次明细同步生成。";
  materialSyncMeta.textContent = syncText;
}

async function applyQuickRange(sectionKey, mode) {
  const current = sectionFilter(sectionKey);
  if (current.mode === mode) return;
  setSectionFilter(sectionKey, { mode });
  try {
    await refreshPerformanceSections(true);
  } catch (error) {
    window.alert(error.message || "切换时间范围失败");
  }
}

async function applyCustomRange(sectionKey) {
  const config = PERFORMANCE_SECTION_CONFIG[sectionKey];
  if (!config) return;
  const start = String(config.startEl?.value || "").trim();
  const end = String(config.endEl?.value || "").trim();
  if (!isValidDateInput(start) || !isValidDateInput(end)) {
    window.alert("请选择完整的开始日期和结束日期");
    return;
  }
  if (start > end) {
    window.alert("开始日期不能晚于结束日期");
    return;
  }
  setSectionFilter(sectionKey, { mode: "custom", start, end });
  try {
    await refreshPerformanceSections(true);
  } catch (error) {
    window.alert(error.message || "查询时间段失败");
  }
}

function bindRangeFilterControls(sectionKey) {
  const config = PERFORMANCE_SECTION_CONFIG[sectionKey];
  if (!config) return;
  config.switchEl?.querySelectorAll(".range-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const next = normalizeRangeKey(button.dataset.range);
      if (next === "custom") {
        await applyCustomRange(sectionKey);
        return;
      }
      await applyQuickRange(sectionKey, next);
    });
  });
  config.applyEl?.addEventListener("click", async () => {
    await applyCustomRange(sectionKey);
  });
  [config.startEl, config.endEl].forEach((input) => {
    input?.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      await applyCustomRange(sectionKey);
    });
  });
}

function bindInputs() {
  if (viewTabs) {
    viewTabs.querySelectorAll(".view-tab").forEach((button) => {
      button.addEventListener("click", async () => {
        const view = button.dataset.view || "overview";
        setActiveView(view);
        if (view === "materials" && !state.materialPayload) {
          await refreshMaterialSection(true);
        }
      });
    });
  }

  accountSearch.addEventListener("input", () => renderAccountTable(rangePayload(sectionFilter("account"))?.accounts || []));
  planSearch.addEventListener("input", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));
  employeeSearch.addEventListener("input", () => renderEmployeeTable(rangePayload(sectionFilter("breakdown"))?.employees || []));
  productSearch.addEventListener("input", () => renderProductTable(rangePayload(sectionFilter("breakdown"))?.products || []));
  materialSearch.addEventListener("input", () => renderMaterialTable(state.materialPayload?.items || []));
  planAccountFilter.addEventListener("change", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));

  bindRangeFilterControls("account");
  bindRangeFilterControls("plan");
  bindRangeFilterControls("breakdown");

  notificationForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(notificationForm);
    const payload = {
      enabled: form.get("enabled") === "on",
      channel: String(form.get("channel") || "feishu"),
      account: String(form.get("account") || "").trim(),
      target: String(form.get("target") || "").trim(),
      alert_enabled: form.get("alert_enabled") === "on",
      alert_batch_size: Number(form.get("alert_batch_size") || 6),
      summary_enabled: false,
      summary_times: "",
      summary_account_limit: 6,
      summary_plan_limit: 10,
    };
    const response = await fetch("/api/notification-settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "保存通知设置失败");
      return;
    }
    await fetchDashboard();
  });

  ruleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(ruleForm);
    const payload = {
      entity_type: form.get("entity_type"),
      metric: form.get("metric"),
      operator: form.get("operator"),
      threshold: Number(form.get("threshold")),
      min_spend: Number(form.get("min_spend") || 0),
      cooldown_minutes: Number(form.get("cooldown_minutes") || 60),
      enabled: form.get("enabled") === "on",
      target_id: String(form.get("target_id") || ""),
      note: String(form.get("note") || ""),
    };
    await fetch("/api/alert-rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    ruleForm.reset();
    ruleForm.querySelector('input[name="enabled"]').checked = true;
    await fetchDashboard();
  });

  syncButton.addEventListener("click", async () => {
    syncButton.disabled = true;
    syncButton.textContent = "刷新中...";
    try {
      await fetch("/api/sync", { method: "POST" });
      await fetchDashboard();
    } finally {
      syncButton.disabled = false;
      syncButton.textContent = "立即刷新";
    }
  });

  if (syncExtendedButton) {
    syncExtendedButton.addEventListener("click", async () => {
      syncExtendedButton.disabled = true;
      syncExtendedButton.textContent = "同步中...";
      try {
        await fetch("/api/sync/extended", { method: "POST" });
        await fetchDashboard();
        await refreshMaterialSection(true);
      } finally {
        syncExtendedButton.disabled = false;
        syncExtendedButton.textContent = "刷新素材";
      }
    });
  }
}

async function fetchDashboard() {
  const response = await fetch("/api/dashboard");
  const payload = await response.json();
  state.payload = payload;
  if (!payload.latest) return;
  await render(payload);
}

async function render(payload) {
  const latest = payload.latest;
  renderOverviewHero(latest);
  renderKpis(latest);
  renderSystemCards(latest, payload.extendedSync || latest?.extendedSync, payload.tokenInfo || {});
  renderAlerts(payload.alertEvents || []);
  renderSignalOverview(payload.notificationSettings || {}, payload.alertRules || []);
  renderNotificationSettings(payload.notificationSettings || {});
  renderRuleTable(payload.alertRules || []);
  lastSnapshotText.textContent = latest.snapshot_time;
  refreshHintText.textContent = "采集 1 分钟 · 明细 10 分钟 · 页面 60 秒";
  try {
    await refreshPerformanceSections(true);
  } catch (error) {
    console.error("refreshPerformanceSections failed", error);
  }
  if (state.activeView === "materials") {
    try {
      await refreshMaterialSection(true);
    } catch (error) {
      console.error("refreshMaterialSection failed", error);
    }
  }
  setActiveView(state.activeView);
}

bindInputs();
setActiveView(state.activeView);
fetchDashboard();
window.setInterval(fetchDashboard, 60 * 1000);
