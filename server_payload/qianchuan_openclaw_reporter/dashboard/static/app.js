const RANGE_LABELS = {
  day: "今日",
  yesterday: "昨日",
  week: "本周",
  month: "本月",
  custom: "指定日期范围",
};

const RULE_ENTITY_CONFIG = {
  account: {
    label: "账户",
    metrics: ["stat_cost", "roi", "order_count", "pay_amount"],
    targetLabel: "限定账户",
    targetPlaceholder: "留空表示全部账户",
    targetSource: "accounts",
    supportsMinSpend: true,
    thresholdStep: "0.01",
  },
  plan: {
    label: "计划",
    metrics: ["stat_cost", "roi", "order_count", "pay_amount"],
    targetLabel: "限定计划",
    targetPlaceholder: "留空表示全部计划",
    targetSource: "plans",
    supportsMinSpend: true,
    thresholdStep: "0.01",
  },
  account_balance: {
    label: "账户余额",
    metrics: ["account_balance"],
    targetLabel: "限定账户",
    targetPlaceholder: "留空表示全部账户余额",
    targetSource: "accountBalances",
    supportsMinSpend: false,
    thresholdStep: "0.01",
  },
  shared_wallet: {
    label: "共享钱包",
    metrics: ["wallet_balance"],
    targetLabel: "限定共享钱包",
    targetPlaceholder: "留空表示全部共享钱包",
    targetSource: "sharedWallets",
    supportsMinSpend: false,
    thresholdStep: "0.01",
  },
  burst_plan: {
    label: "爆单计划",
    metrics: ["burst_order_count"],
    targetLabel: "限定计划",
    targetPlaceholder: "留空表示全部计划",
    targetSource: "plans",
    supportsMinSpend: false,
    thresholdStep: "1",
  },
};

const state = {
  payload: null,
  session: null,
  rangePayloads: {},
  planAssetCache: {},
  materialPayloads: {},
  employees: [],
  users: [],
  catalogAccounts: [],
  employeeKeywords: {},
  employeeBindings: {},
  userScopes: {},
  matchPreview: null,
  unassignedPool: null,
  unassignedScope: "all",
  accountSort: loadSort("account-sort", { key: "stat_cost", dir: "desc" }),
  planSort: loadSort("plan-sort", { key: "order_count", dir: "desc" }),
  employeeSort: loadSort("employee-sort", { key: "stat_cost", dir: "desc" }),
  productSort: loadSort("product-sort", { key: "order_count", dir: "desc" }),
  materialSort: loadSort("material-sort", { key: "order_count", dir: "desc" }),
  activeView: loadPreference("active-view", "overview"),
  performanceFilters: {
    account: loadRangeFilter("account-range-filter", "day"),
    plan: loadRangeFilter("plan-range-filter", "day"),
    breakdown: loadRangeFilter("breakdown-range-filter", "day"),
    material: loadRangeFilter("material-range-filter", "day"),
  },
  selectedPlanId: null,
  selectedEmployeeName: null,
  selectedProductKey: null,
  selectedMaterialKey: null,
  selectedEmployeeId: null,
  selectedUserId: null,
  selectedUserScopeIds: [],
  editingRuleId: null,
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
const ruleFormHint = document.getElementById("ruleFormHint");
const ruleFormSubmitButton = document.getElementById("ruleFormSubmitButton");
const ruleFormCancelButton = document.getElementById("ruleFormCancelButton");
const ruleTargetInput = document.getElementById("ruleTargetInput");
const ruleTargetLabel = document.getElementById("ruleTargetLabel");
const ruleTargetOptions = document.getElementById("ruleTargetOptions");
const ruleMinSpendField = document.getElementById("ruleMinSpendField");
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
const materialRangeSwitch = document.getElementById("materialRangeSwitch");
const materialDateStart = document.getElementById("materialDateStart");
const materialDateEnd = document.getElementById("materialDateEnd");
const materialDateApply = document.getElementById("materialDateApply");
const materialSyncMeta = document.getElementById("materialSyncMeta");
const employeeManagerTable = document.getElementById("employeeManagerTable");
const employeeForm = document.getElementById("employeeForm");
const employeeFormReset = document.getElementById("employeeFormReset");
const employeeEditorStatus = document.getElementById("employeeEditorStatus");
const ownershipHeadMeta = document.getElementById("ownershipHeadMeta");
const ownershipReadonlyBanner = document.getElementById("ownershipReadonlyBanner");
const keywordForm = document.getElementById("keywordForm");
const keywordStatus = document.getElementById("keywordStatus");
const keywordTable = document.getElementById("keywordTable");
const matchPreviewForm = document.getElementById("matchPreviewForm");
const matchKeywordInput = document.getElementById("matchKeywordInput");
const matchScopeSelect = document.getElementById("matchScopeSelect");
const matchPreviewMeta = document.getElementById("matchPreviewMeta");
const matchPreviewTable = document.getElementById("matchPreviewTable");
const bindingTable = document.getElementById("bindingTable");
const unassignedScopeSelect = document.getElementById("unassignedScopeSelect");
const unassignedMeta = document.getElementById("unassignedMeta");
const unassignedTable = document.getElementById("unassignedTable");
const userTable = document.getElementById("userTable");
const userForm = document.getElementById("userForm");
const userFormReset = document.getElementById("userFormReset");
const userEditorStatus = document.getElementById("userEditorStatus");
const scopeAccountList = document.getElementById("scopeAccountList");
const saveUserScopesButton = document.getElementById("saveUserScopesButton");
const scopeEditorMeta = document.getElementById("scopeEditorMeta");
const ruleTemplateButtons = Array.from(document.querySelectorAll(".signal-template-button"));
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
  material: {
    storageKey: "material-range-filter",
    switchEl: materialRangeSwitch,
    metaEl: materialSyncMeta,
    startEl: materialDateStart,
    endEl: materialDateEnd,
    applyEl: materialDateApply,
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
  const end = new Date(today);
  if (mode === "yesterday") {
    start.setDate(start.getDate() - 1);
    end.setDate(end.getDate() - 1);
  } else if (mode === "week") {
    const weekdayOffset = (today.getDay() + 6) % 7;
    start.setDate(start.getDate() - weekdayOffset);
  } else if (mode === "month") {
    start.setDate(1);
  }
  return {
    start: formatDateInputValue(start),
    end: formatDateInputValue(end),
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

function truncateMiddle(value, head = 8, tail = 6) {
  const text = String(value || "").trim();
  if (!text) return "--";
  if (text.length <= head + tail + 3) return text;
  return `${text.slice(0, head)}...${text.slice(-tail)}`;
}

function metricLabel(metric) {
  const labels = {
    roi: "ROI",
    stat_cost: "消耗",
    order_count: "订单数",
    pay_amount: "支付金额",
    account_balance: "账户余额",
    wallet_balance: "共享钱包余额",
    burst_order_count: "爆单订单数",
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

function setInlineFeedback(element, text, tone = "neutral") {
  if (!element) return;
  element.textContent = text;
  element.dataset.tone = tone;
}

function focusFirstInput(form, selector) {
  form?.querySelector(selector)?.focus();
}

function entityLabel(entityType) {
  const labels = {
    account: "账户",
    plan: "计划",
    account_balance: "账户余额",
    shared_wallet: "共享钱包",
    burst_plan: "爆单计划",
  };
  return labels[entityType] || "账户";
}

function ruleEntityConfig(entityType) {
  return RULE_ENTITY_CONFIG[String(entityType || "").trim()] || RULE_ENTITY_CONFIG.plan;
}

function ruleMetricOptions(entityType) {
  return ruleEntityConfig(entityType).metrics.map((metric) => ({
    value: metric,
    label: metricLabel(metric),
  }));
}

function entityTargetOptions(entityType) {
  const latest = state.payload?.latest || {};
  const config = ruleEntityConfig(entityType);
  const sourceKey = config.targetSource;
  const items = latest?.[sourceKey] || [];
  if (sourceKey === "accounts") {
    return items.map((item) => ({
      value: String(item.advertiser_id || ""),
      label: `${item.advertiser_name || item.advertiser_id || "账户"} · ${item.advertiser_id || "-"}`,
    }));
  }
  if (sourceKey === "plans") {
    return items.map((item) => ({
      value: String(item.ad_id || ""),
      label: `${item.ad_name || item.ad_id || "计划"} · ${item.advertiser_name || "-"}`,
    }));
  }
  if (sourceKey === "accountBalances") {
    return items.map((item) => ({
      value: String(item.advertiser_id || ""),
      label: `${item.advertiser_name || item.advertiser_id || "账户"} · 余额 ${formatMoney(item.available_balance ?? item.account_balance ?? 0)}`,
    }));
  }
  if (sourceKey === "sharedWallets") {
    return items.map((item) => ({
      value: String(item.main_wallet_id || ""),
      label: `${item.wallet_name || item.main_wallet_id || "共享钱包"} · 余额 ${formatMoney(item.wallet_balance ?? item.valid_balance ?? 0)}`,
    }));
  }
  return [];
}

function targetDisplayLabel(entityType, targetId) {
  const target = String(targetId || "").trim();
  if (!target) return "全部";
  const options = entityTargetOptions(entityType);
  const match = options.find((item) => item.value === target);
  return match?.label || target;
}

function resetRuleFormState() {
  if (!ruleForm) return;
  state.editingRuleId = null;
  ruleForm.reset();
  const ruleIdInput = ruleForm.querySelector('input[name="rule_id"]');
  if (ruleIdInput) ruleIdInput.value = "";
  const enabledInput = ruleForm.querySelector('input[name="enabled"]');
  if (enabledInput) enabledInput.checked = true;
  const cooldownInput = ruleForm.querySelector('input[name="cooldown_minutes"]');
  if (cooldownInput) cooldownInput.value = "60";
  const thresholdInput = ruleForm.querySelector('input[name="threshold"]');
  if (thresholdInput) thresholdInput.value = "";
  const minSpendInput = ruleForm.querySelector('input[name="min_spend"]');
  if (minSpendInput) minSpendInput.value = "0";
  const entitySelect = ruleForm.querySelector('select[name="entity_type"]');
  if (entitySelect) entitySelect.value = "plan";
  const operatorSelect = ruleForm.querySelector('select[name="operator"]');
  if (operatorSelect) operatorSelect.value = "lt";
  if (ruleFormSubmitButton) ruleFormSubmitButton.textContent = "新增规则";
  if (ruleFormCancelButton) ruleFormCancelButton.classList.add("hidden");
  syncRuleFormFields();
  if (ruleFormHint) {
    ruleFormHint.dataset.tone = "neutral";
  }
}

function fillRuleForm(rule) {
  if (!ruleForm || !rule) return;
  state.editingRuleId = Number(rule.id);
  ruleForm.querySelector('input[name="rule_id"]').value = String(rule.id || "");
  ruleForm.querySelector('select[name="entity_type"]').value = String(rule.entity_type || "plan");
  syncRuleFormFields();
  ruleForm.querySelector('select[name="metric"]').value = String(rule.metric || "");
  ruleForm.querySelector('select[name="operator"]').value = String(rule.operator || "lt");
  ruleForm.querySelector('input[name="threshold"]').value = String(rule.threshold ?? "");
  ruleForm.querySelector('input[name="min_spend"]').value = String(rule.min_spend ?? 0);
  ruleForm.querySelector('input[name="cooldown_minutes"]').value = String(rule.cooldown_minutes ?? 60);
  ruleForm.querySelector('input[name="target_id"]').value = String(rule.target_id || "");
  ruleForm.querySelector('input[name="note"]').value = String(rule.note || "");
  ruleForm.querySelector('input[name="enabled"]').checked = Boolean(rule.enabled);
  if (ruleFormSubmitButton) ruleFormSubmitButton.textContent = "保存规则";
  if (ruleFormCancelButton) ruleFormCancelButton.classList.remove("hidden");
  syncRuleFormFields();
}

function syncRuleFormFields() {
  if (!ruleForm) return;
  const entitySelect = ruleForm.querySelector('select[name="entity_type"]');
  const metricSelect = ruleForm.querySelector('select[name="metric"]');
  const thresholdInput = ruleForm.querySelector('input[name="threshold"]');
  const minSpendInput = ruleForm.querySelector('input[name="min_spend"]');
  const entityType = String(entitySelect?.value || "plan");
  const config = ruleEntityConfig(entityType);
  const currentMetric = String(metricSelect?.value || "");
  const metricOptions = ruleMetricOptions(entityType);
  metricSelect.innerHTML = metricOptions
    .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
    .join("");
  metricSelect.value = metricOptions.some((item) => item.value === currentMetric) ? currentMetric : metricOptions[0].value;
  thresholdInput.step = config.thresholdStep || "0.01";
  ruleTargetLabel.textContent = config.targetLabel;
  ruleTargetInput.placeholder = config.targetPlaceholder;
  ruleMinSpendField.classList.toggle("hidden", !config.supportsMinSpend);
  minSpendInput.disabled = !config.supportsMinSpend;
  if (!config.supportsMinSpend) {
    minSpendInput.value = "0";
  }
  const targetOptions = entityTargetOptions(entityType);
  ruleTargetOptions.innerHTML = targetOptions
    .slice(0, 400)
    .map((item) => `<option value="${escapeHtml(item.value)}" label="${escapeHtml(item.label)}"></option>`)
    .join("");
  if (ruleFormHint) {
    const modeLabel = state.editingRuleId ? "当前为编辑模式" : "当前为新增模式";
    const targetLabel = targetOptions.length ? `可选对象 ${formatNumber(targetOptions.length)} 个` : "当前暂无可选对象";
    const minSpendLabel = config.supportsMinSpend ? "支持最低消耗门槛" : "当前对象不使用最低消耗";
    ruleFormHint.textContent = `${modeLabel} · ${config.label}规则 · ${targetLabel} · ${minSpendLabel}`;
    if (!ruleFormHint.dataset.tone || ruleFormHint.dataset.tone === "neutral") {
      ruleFormHint.dataset.tone = "neutral";
    }
  }
}

function keywordScopeLabel(scope) {
  const labels = {
    all: "全部",
    account: "账户",
    plan: "计划",
    product: "商品",
    material: "素材",
  };
  return labels[String(scope || "").trim()] || scope || "-";
}

function bindingTypeLabel(value) {
  const labels = {
    account: "账户",
    plan: "计划",
    product: "商品",
    material: "素材",
  };
  return labels[String(value || "").trim()] || value || "-";
}

function employeeSourceLabel(value) {
  const labels = {
    manual_material: "人工绑定素材",
    manual_product: "人工绑定商品",
    manual_plan: "人工绑定计划",
    manual_account: "人工绑定账户",
    keyword_material: "素材关键词",
    keyword_product: "商品关键词",
    keyword_plan: "计划关键词",
    keyword_account: "账户关键词",
    legacy_anchor: "主播字段兜底",
    unassigned: "未归属",
  };
  return labels[String(value || "").trim()] || value || "未归属";
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
    <p class="notify-inline-copy">${escapeHtml(targetInfo.detail)} ${settings?.alert_enabled ? `当前每批发送 ${formatNumber(settings?.alert_batch_size || 6)} 条阈值告警。` : "当前只保留页面内提醒，外发可后续开启。"} </p>
  `;
}

function renderSignalOverview(settings, rules) {
  const enabledRules = (rules || []).filter((item) => item.enabled).length;
  const totalRules = (rules || []).length;
  const planRules = (rules || []).filter((item) => item.enabled && item.entity_type === "plan").length;
  const accountRules = (rules || []).filter((item) => item.enabled && item.entity_type === "account").length;
  const balanceRules = (rules || []).filter((item) => item.enabled && ["account_balance", "shared_wallet"].includes(item.entity_type)).length;
  const burstRules = (rules || []).filter((item) => item.enabled && item.entity_type === "burst_plan").length;
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
      <span class="signal-summary-label">余额与钱包</span>
      <strong class="mono">${formatNumber(balanceRules)}</strong>
      <span class="signal-summary-sub">账户余额与共享钱包规则</span>
    </article>
    <article class="signal-summary-card">
      <span class="signal-summary-label">爆单</span>
      <strong class="mono">${formatNumber(burstRules)}</strong>
      <span class="signal-summary-sub">${settings?.alert_enabled ? `外发每批 ${formatNumber(settings?.alert_batch_size || 6)} 条` : "先保留页面提醒，可后续开启外发"}</span>
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
  const customInline = config.startEl?.closest(".custom-date-inline");
  if (customInline) {
    customInline.classList.toggle("active", filter.mode === "custom");
  }
  if (config.startEl && document.activeElement !== config.startEl) config.startEl.value = filter.start || "";
  if (config.endEl && document.activeElement !== config.endEl) config.endEl.value = filter.end || "";
}

function formatDateWindowMeta(payload) {
  if (!payload) {
    return "统计范围：加载中";
  }
  const label = payload.range_label || RANGE_LABELS[payload.range_key] || "当前";
  if (payload.query_start_date && payload.query_end_date) {
    if (payload.query_start_date === payload.query_end_date) {
      return `统计范围：${label} · ${payload.query_start_date}`;
    }
    return `统计范围：${label} · ${payload.query_start_date} 至 ${payload.query_end_date}`;
  }
  return `统计范围：${label} · ${payload.window_start} - ${payload.window_end}`;
}

function rangePayload(filter) {
  return state.rangePayloads[performanceFilterKey(filter)] || null;
}

function materialRangePayload(filter) {
  return state.materialPayloads[performanceFilterKey(filter)] || null;
}

function rangeLabel(filter) {
  const normalized = normalizeRangeFilter(filter);
  if (normalized.mode === "custom") {
    return "指定日期范围";
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
        <div class="summary-value">暂无异常</div>
        <div class="summary-sub">最近没有命中规则，先关注账户和计划变化。</div>
        <div class="summary-metric-row">
          <div><span>待处理</span><strong class="mono">0</strong></div>
          <div><span>最新状态</span><strong>正常</strong></div>
          <div><span>提醒对象</span><strong>-</strong></div>
        </div>
      </div>
      <div class="alert-summary-card stat">
        <div class="summary-label">待处理</div>
        <div class="summary-value mono">0</div>
        <div class="summary-sub">当前没有待处理提醒</div>
      </div>
      <div class="alert-summary-card stat">
        <div class="summary-label">处理节奏</div>
        <div class="summary-value">观察中</div>
        <div class="summary-sub">等待新触发</div>
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
    ["活跃归属人", formatNumber(summary.active_employee_count), `总归属人 ${formatNumber(summary.employee_count)}`],
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
        <h2>今日投放概况</h2>
        <p class="overview-hero-copy">先看消耗、支付、订单和 ROI。</p>
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
      <div class="overview-foot-stat"><span>活跃归属人</span><strong class="mono">${formatNumber(summary.active_employee_count)}</strong></div>
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
          <td>
            <div class="cell-primary">${escapeHtml(row.advertiser_name)}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">AID ${escapeHtml(String(row.advertiser_id || "-"))}</span>
            </div>
          </td>
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
  employeeDetail.textContent = "点击归属人行，查看该归属人当前负责的计划规模和核心表现。";
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
      <div class="detail-stat detail-stat-wide"><span class="label">归属人</span><span class="value compact">${escapeHtml(row.employee_name)}</span></div>
      <div class="detail-stat"><span class="label">归属来源</span><span class="value compact">${escapeHtml(employeeSourceLabel(row.employee_source))}</span></div>
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
    { key: "employee_name", label: "归属人", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
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
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
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
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
    { key: "employee_count", label: "归属人数", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.productSort);

  productTable.innerHTML = `
    ${makeHeader(columns, state.productSort, "product-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-product-key="${escapeHtml(row.product_key)}" class="${state.selectedProductKey === row.product_key ? "active-row" : ""}">
          <td>${escapeHtml(row.product_name)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
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
  materialDetail.textContent = "点击素材行，查看覆盖范围和当前表现。";
}

function renderMaterialDetail(materialKey) {
  const rows = materialRangePayload(sectionFilter("material"))?.items || [];
  const row = rows.find((item) => item.material_key === materialKey);
  if (!row) return;
  materialDetail.className = "detail-panel";
  materialDetail.innerHTML = `
    <div class="detail-block-head">
      <h4>素材覆盖与表现</h4>
      <span>补充信息</span>
    </div>
    <div class="detail-stats">
      <div class="detail-stat"><span class="label">素材类型</span><span class="value compact">${escapeHtml(row.material_type || "-")}</span></div>
      <div class="detail-stat"><span class="label">当前统计消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
      <div class="detail-stat"><span class="label">当前统计支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">当前统计订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
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
    const haystack = [row.material_name, row.material_id, row.video_id, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "material_name", label: "素材", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "material_type", label: "类型", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.materialSort);
  materialTable.innerHTML = `
    ${makeHeader(columns, state.materialSort, "material-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-material-key="${escapeHtml(row.material_key)}" class="${state.selectedMaterialKey === row.material_key ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.material_name || "未命名素材")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem" title="素材 ID：${escapeHtml(row.material_id || "-")}">MID ${escapeHtml(truncateMiddle(row.material_id || "-", 8, 6))}</span>
              <span class="cell-subitem" title="视频 ID：${escapeHtml(row.video_id || "-")}">VID ${escapeHtml(truncateMiddle(row.video_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td><span class="pill">${escapeHtml(row.material_type || "-")}</span></td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
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
  const filter = sectionFilter("material");
  const cacheKey = performanceFilterKey(filter);
  if (!force && state.materialPayloads[cacheKey]) {
    return state.materialPayloads[cacheKey];
  }
  const params = new URLSearchParams();
  params.set("range", filter.mode);
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  const response = await fetch(`/api/material-rankings?${params.toString()}`);
  if (!response.ok) {
    throw new Error("material rankings fetch failed");
  }
  const payload = await response.json();
  state.materialPayloads[cacheKey] = payload;
  return payload;
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
      </div>
      <div class="asset-tag-row">${typeTags || '<span class="pill">暂无素材</span>'}</div>
    </div>
    <div class="asset-group">
      <div class="asset-group-head">
        <h4>代表商品</h4>
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
    </div>
  `;
  await renderPlanAssets(adId);
}

function clearPlanDetail() {
  planDetail.className = "detail-panel empty";
  planDetail.textContent = "点击计划行，查看计划字段和当前表现。";
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
    { key: "product_name", label: "商品 / 主播", sortable: true },
    { key: "marketing_goal_text", label: "营销目标", sortable: true },
    { key: "advertiser_name", label: "账户", sortable: true },
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
          <td>
            <div class="cell-primary">${escapeHtml(row.ad_name)}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">PID ${escapeHtml(String(row.ad_id || "-"))}</span>
            </div>
          </td>
          <td>
            <div class="cell-primary">${escapeHtml(row.product_name || "-")}</div>
            <div class="cell-subline">
              ${row.product_id ? `<span class="cell-subitem mono" title="商品 ID：${escapeHtml(row.product_id)}">GID ${escapeHtml(truncateMiddle(row.product_id, 7, 5))}</span>` : ""}
              ${row.anchor_name ? `<span class="cell-subitem">主播 ${escapeHtml(row.anchor_name)}</span>` : ""}
            </div>
          </td>
          <td>${renderMarketingGoalBadge(row)}</td>
          <td>${escapeHtml(row.advertiser_name)}</td>
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
        <th>对象范围</th>
        <th>规则</th>
        <th>最低消耗</th>
        <th>冷却</th>
        <th>状态</th>
        <th>备注</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${rules.length ? rules.map((rule) => `
        <tr>
          <td>${escapeHtml(entityLabel(rule.entity_type))}</td>
          <td>${escapeHtml(metricLabel(rule.metric))}</td>
          <td>${escapeHtml(targetDisplayLabel(rule.entity_type, rule.target_id))}</td>
          <td class="mono">${escapeHtml(operatorLabel(rule.operator))} ${escapeHtml(rule.threshold)}</td>
          <td class="mono">${["account", "plan"].includes(rule.entity_type) ? formatMoney(rule.min_spend) : "--"}</td>
          <td class="mono">${formatNumber(rule.cooldown_minutes)} 分钟</td>
          <td><span class="pill">${rule.enabled ? "启用" : "关闭"}</span></td>
          <td>${escapeHtml(rule.note || "--")}</td>
          <td>
            <button class="button ghost edit-rule" data-id="${rule.id}">编辑</button>
            <button class="button ghost toggle-rule" data-id="${rule.id}">${rule.enabled ? "停用" : "启用"}</button>
            <button class="button ghost delete-rule" data-id="${rule.id}">删除</button>
          </td>
        </tr>
      `).join("") : '<tr><td colspan="9" class="empty-cell">还没有预警规则，先从账户余额、共享钱包、消耗或爆单规则开始。</td></tr>'}
    </tbody>
  `;

  ruleTable.querySelectorAll(".edit-rule").forEach((button) => {
    button.addEventListener("click", () => {
      const id = Number(button.dataset.id);
      const rule = rules.find((item) => Number(item.id) === id);
      if (!rule) return;
      fillRuleForm(rule);
      setActiveView("signals");
      ruleForm.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

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

function isAdmin() {
  return state.session?.role === "admin";
}

function setFormReadOnly(formEl, readOnly) {
  if (!formEl) return;
  formEl.querySelectorAll("input, select, textarea, button").forEach((field) => {
    if (field.type === "hidden") return;
    field.disabled = Boolean(readOnly);
  });
}

function applyRoleViewPolicy() {
  const admin = isAdmin();
  const accessTab = viewTabs?.querySelector('[data-view="access"]');
  if (accessTab) {
    accessTab.classList.toggle("hidden", !admin);
  }
  if (!admin && state.activeView === "access") {
    setActiveView("overview");
  }
  ownershipReadonlyBanner?.classList.toggle("hidden", admin);
  if (ownershipHeadMeta) {
    ownershipHeadMeta.innerHTML = admin
      ? "<span>归属人、关键词和人工绑定会直接影响公开页与后台排名。</span>"
      : "<span>当前账号可查看归属结果与命中情况，规则由管理员维护。</span>";
  }
  setFormReadOnly(employeeForm, !admin);
  setFormReadOnly(keywordForm, !admin);
  matchPreviewForm?.querySelectorAll("button").forEach((button) => {
    button.disabled = false;
  });
  employeeFormReset && (employeeFormReset.disabled = !admin);
  userFormReset && (userFormReset.disabled = !admin);
}

function selectedEmployeeRecord() {
  return state.employees.find((item) => Number(item.id) === Number(state.selectedEmployeeId)) || null;
}

function selectedUserRecord() {
  return state.users.find((item) => Number(item.id) === Number(state.selectedUserId)) || null;
}

function resetEmployeeFormState() {
  state.selectedEmployeeId = null;
  if (employeeForm) employeeForm.reset();
  const enabledInput = employeeForm?.querySelector('input[name="enabled"]');
  if (enabledInput) enabledInput.checked = true;
  setInlineFeedback(
    employeeEditorStatus,
    isAdmin() ? "新建归属人后，再继续配置关键词和人工绑定。" : "当前账号只读，可查看归属结果与命中明细。",
    "neutral",
  );
  setInlineFeedback(keywordStatus, "选择归属人后，再添加关键词。", "neutral");
  keywordTable.innerHTML = '<tbody><tr><td colspan="6" class="empty-cell">先选择归属人，再维护关键词。</td></tr></tbody>';
  bindingTable.innerHTML = '<tbody><tr><td colspan="5" class="empty-cell">先选择归属人，再维护人工绑定。</td></tr></tbody>';
  if (isAdmin()) focusFirstInput(employeeForm, 'input[name="display_name"]');
}

function fillEmployeeForm(employee) {
  if (!employeeForm) return;
  employeeForm.querySelector('input[name="display_name"]').value = employee?.display_name || "";
  employeeForm.querySelector('input[name="note"]').value = employee?.note || "";
  employeeForm.querySelector('input[name="enabled"]').checked = Boolean(employee?.enabled);
  setInlineFeedback(
    employeeEditorStatus,
    employee
      ? `${isAdmin() ? "当前编辑" : "当前查看"}：${employee.display_name} · 关键词 ${formatNumber(employee.keyword_count || 0)} · 绑定 ${formatNumber(employee.binding_count || 0)}`
      : (isAdmin() ? "新建归属人后，再继续配置关键词和人工绑定。" : "当前账号只读，可查看归属结果与命中明细。"),
    "neutral",
  );
  setInlineFeedback(
    keywordStatus,
    employee ? `正在为 ${employee.display_name} 维护关键词。` : "选择归属人后，再添加关键词。",
    "neutral",
  );
}

function renderEmployeeManagerTable() {
  if (!employeeManagerTable) return;
  employeeManagerTable.innerHTML = `
    <thead>
      <tr>
        <th>归属人</th>
        <th>关键词</th>
        <th>绑定</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      ${state.employees.length ? state.employees.map((item) => `
        <tr data-employee-id="${item.id}" class="${Number(state.selectedEmployeeId) === Number(item.id) ? "active-row" : ""}">
          <td>${escapeHtml(item.display_name)}</td>
          <td class="mono">${formatNumber(item.keyword_count || 0)}</td>
          <td class="mono">${formatNumber(item.binding_count || 0)}</td>
          <td><span class="pill">${item.enabled ? "启用" : "停用"}</span></td>
        </tr>
      `).join("") : '<tr><td colspan="4" class="empty-cell">还没有归属人，请先创建。</td></tr>'}
    </tbody>
  `;
  employeeManagerTable.querySelectorAll("tbody tr[data-employee-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      await selectEmployeeManager(Number(row.dataset.employeeId));
    });
  });
}

function renderKeywordTable() {
  const employee = selectedEmployeeRecord();
  const rows = employee ? state.employeeKeywords[employee.id] || [] : [];
  keywordTable.innerHTML = `
    <thead>
      <tr>
        <th>关键词</th>
        <th>范围</th>
        <th>优先级</th>
        <th>状态</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${employee ? (rows.length ? rows.map((item) => `
        <tr>
          <td>${escapeHtml(item.keyword)}</td>
          <td>${escapeHtml(keywordScopeLabel(item.scope))}</td>
          <td class="mono">${formatNumber(item.priority)}</td>
          <td><span class="pill">${item.enabled ? "启用" : "停用"}</span></td>
          <td>
            ${isAdmin() ? `<button type="button" class="button ghost delete-keyword" data-id="${item.id}">删除</button>` : '<span class="detail-sub">只读</span>'}
          </td>
        </tr>
      `).join("") : '<tr><td colspan="5" class="empty-cell">当前归属人还没有关键词。</td></tr>') : '<tr><td colspan="5" class="empty-cell">先选择归属人。</td></tr>'}
    </tbody>
  `;
  keywordTable.querySelectorAll(".delete-keyword").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(`/api/employee-keywords/${button.dataset.id}`, { method: "DELETE" });
      if (employee) {
        await fetchEmployeeKeywords(employee.id, true);
        await fetchEmployees(true);
        fillEmployeeForm(selectedEmployeeRecord());
        renderEmployeeManagerTable();
        await fetchDashboard();
        setInlineFeedback(keywordStatus, `已删除关键词，${employee.display_name} 的归属规则已刷新。`, "success");
      }
    });
  });
}

function renderBindingTable() {
  const employee = selectedEmployeeRecord();
  const rows = employee ? state.employeeBindings[employee.id] || [] : [];
  bindingTable.innerHTML = `
    <thead>
      <tr>
        <th>类型</th>
        <th>对象</th>
        <th>标识</th>
        <th>备注</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${employee ? (rows.length ? rows.map((item) => `
        <tr>
          <td>${escapeHtml(bindingTypeLabel(item.object_type))}</td>
          <td>${escapeHtml(item.object_label || "--")}</td>
          <td class="mono">${escapeHtml(item.object_key)}</td>
          <td>${escapeHtml(item.note || "--")}</td>
          <td>${isAdmin() ? `<button type="button" class="button ghost delete-binding" data-id="${item.id}">删除</button>` : '<span class="detail-sub">只读</span>'}</td>
        </tr>
      `).join("") : '<tr><td colspan="5" class="empty-cell">当前归属人还没有人工绑定。</td></tr>') : '<tr><td colspan="5" class="empty-cell">先选择归属人。</td></tr>'}
    </tbody>
  `;
  bindingTable.querySelectorAll(".delete-binding").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(`/api/employee-bindings/${button.dataset.id}`, { method: "DELETE" });
      if (employee) {
        await fetchEmployeeBindings(employee.id, true);
        await fetchEmployees(true);
        fillEmployeeForm(selectedEmployeeRecord());
        renderEmployeeManagerTable();
        await fetchDashboard();
        setInlineFeedback(matchPreviewMeta, `已删除人工绑定，${employee.display_name} 的归属结果已刷新。`, "success");
      }
    });
  });
}

function flattenMatchPreview(preview) {
  if (!preview?.items) return [];
  const sections = [
    ["account", preview.items.accounts || []],
    ["plan", preview.items.plans || []],
    ["product", preview.items.products || []],
    ["material", preview.items.materials || []],
  ];
  return sections.flatMap(([objectType, rows]) => rows.map((row) => ({
    object_type: objectType,
    object_key: objectType === "account"
      ? String(row.advertiser_id)
      : objectType === "plan"
        ? String(row.ad_id)
        : objectType === "product"
          ? String(row.product_key || row.product_id || row.product_name || "")
          : String(row.material_key || row.material_id || row.material_name || ""),
    object_label: objectType === "account"
      ? String(row.advertiser_name || "")
      : objectType === "plan"
        ? String(row.ad_name || "")
        : objectType === "product"
          ? String(row.product_name || row.product_id || "")
          : String(row.material_name || row.material_id || ""),
    account_name: String(row.advertiser_name || ""),
    plan_name: String(row.ad_name || ""),
  })));
}

function renderMatchPreview() {
  const employee = selectedEmployeeRecord();
  const rows = flattenMatchPreview(state.matchPreview);
  setInlineFeedback(
    matchPreviewMeta,
    employee
      ? `当前归属人：${employee.display_name} · 当前命中 ${formatNumber(rows.length)} 条，可直接人工绑定。`
      : "先选择归属人，再预览命中结果。",
    "neutral",
  );
  matchPreviewTable.innerHTML = `
    <thead>
      <tr>
        <th>类型</th>
        <th>对象</th>
        <th>所属账户 / 计划</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${rows.length ? rows.map((row) => `
        <tr>
          <td>${escapeHtml(bindingTypeLabel(row.object_type))}</td>
          <td>${escapeHtml(row.object_label || "--")}<br /><span class="detail-sub mono">${escapeHtml(row.object_key || "--")}</span></td>
          <td>${escapeHtml([row.account_name, row.plan_name].filter(Boolean).join(" / ") || "--")}</td>
          <td>
            ${employee && isAdmin() ? `<button type="button" class="button ghost bind-preview" data-type="${escapeHtml(row.object_type)}" data-key="${escapeHtml(row.object_key)}" data-label="${escapeHtml(row.object_label)}">绑定到当前归属人</button>` : employee ? '<span class="detail-sub">当前账号只读</span>' : '<span class="detail-sub">先选择归属人</span>'}
          </td>
        </tr>
      `).join("") : '<tr><td colspan="4" class="empty-cell">输入关键词并预览后，这里会展示命中的账户、计划、商品和素材。</td></tr>'}
    </tbody>
  `;
  matchPreviewTable.querySelectorAll(".bind-preview").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!employee) return;
      const payload = {
        object_type: button.dataset.type,
        object_key: button.dataset.key,
        object_label: button.dataset.label,
        note: "由命中预览一键绑定",
      };
      const response = await fetch(`/api/employees/${employee.id}/bindings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        window.alert(errorPayload.detail || "人工绑定失败");
        return;
      }
      await fetchEmployeeBindings(employee.id, true);
      await fetchEmployees(true);
      fillEmployeeForm(selectedEmployeeRecord());
      renderEmployeeManagerTable();
      await fetchDashboard();
      setInlineFeedback(matchPreviewMeta, `已绑定到 ${employee.display_name}，榜单会按新归属刷新。`, "success");
    });
  });
}

async function fetchUnassignedPool(force = false) {
  const filter = sectionFilter("plan");
  const params = new URLSearchParams({ range: filter.mode, scope: state.unassignedScope || "all" });
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  if (!force && state.unassignedPool && state.unassignedPool.cacheKey === params.toString()) {
    return state.unassignedPool;
  }
  const response = await fetch(`/api/unassigned-candidates?${params.toString()}`);
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.detail || "未归属池加载失败");
  }
  const payload = await response.json();
  state.unassignedPool = { ...payload, cacheKey: params.toString() };
  return state.unassignedPool;
}

async function bindUnassignedCandidate(option) {
  const employee = selectedEmployeeRecord();
  if (!employee) {
    window.alert("请先选择归属人");
    return;
  }
  const response = await fetch(`/api/employees/${employee.id}/bindings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      object_type: option.object_type,
      object_key: option.object_key,
      object_label: option.object_label,
      note: "由未归属池一键绑定",
    }),
  });
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => ({}));
    window.alert(errorPayload.detail || "绑定失败");
    return;
  }
  await fetchEmployeeBindings(employee.id, true);
  await fetchEmployees(true);
  fillEmployeeForm(selectedEmployeeRecord());
  renderEmployeeManagerTable();
  await fetchDashboard();
  if (state.activeView === "ownership") {
    await ensureOwnershipData(true);
  }
  setInlineFeedback(matchPreviewMeta, `已绑定到 ${employee.display_name}，未归属池已刷新。`, "success");
}

function renderUnassignedTable() {
  const employee = selectedEmployeeRecord();
  const items = state.unassignedPool?.items || [];
  const rangeText = state.unassignedPool?.range_label || rangeLabel(sectionFilter("plan"));
  if (!state.employees.length) {
    unassignedMeta.textContent = "当前还没有归属人。请先创建归属人，再配置关键词或人工绑定；未归属池会基于这些规则生成。";
  } else {
    unassignedMeta.textContent = `按计划页当前时间范围查看未命中归属规则的数据 · ${rangeText} · 未归属计划 ${formatNumber(state.unassignedPool?.total_plan_count || 0)} 条 · 当前对象 ${formatNumber(state.unassignedPool?.item_count || 0)} 条`;
  }
  unassignedTable.innerHTML = `
    <thead>
      <tr>
        <th>对象</th>
        <th>账户 / 代表计划</th>
        <th>消耗</th>
        <th>支付</th>
        <th>订单</th>
        <th>ROI</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${items.length ? items.map((row, index) => `
        <tr>
          <td>
            <div class="cell-primary">${escapeHtml(row.object_label || "--")}</div>
            <div class="cell-subline">
              <span class="cell-subitem">${escapeHtml(row.object_type_label || "--")}</span>
              <span class="cell-subitem mono">${escapeHtml(row.object_key || "--")}</span>
            </div>
          </td>
          <td>
            <div class="cell-primary">${escapeHtml(row.advertiser_name || "-")}</div>
            <div class="cell-subline">
              <span class="cell-subitem">${escapeHtml(row.plan_name || "暂无代表计划")}</span>
              ${row.product_name ? `<span class="cell-subitem">${escapeHtml(row.product_name)}</span>` : ""}
              ${row.material_type ? `<span class="cell-subitem">${escapeHtml(row.material_type)}</span>` : ""}
            </div>
          </td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td>
            <div class="inline-button-row">
              ${row.binding_options?.length && employee && isAdmin()
                ? row.binding_options.map((option, optionIndex) => `
                  <button
                    type="button"
                    class="button ghost bind-unassigned"
                    data-row-index="${index}"
                    data-option-index="${optionIndex}"
                  >${escapeHtml(option.action_label || "绑定")}</button>
                `).join("")
                : employee
                  ? '<span class="detail-sub">当前账号只读</span>'
                  : '<span class="detail-sub">先选择归属人</span>'}
            </div>
          </td>
        </tr>
      `).join("") : '<tr><td colspan="7" class="empty-cell">当前时间范围内没有未归属对象。</td></tr>'}
    </tbody>
  `;

  unassignedTable.querySelectorAll(".bind-unassigned").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = items[Number(button.dataset.rowIndex)];
      const option = row?.binding_options?.[Number(button.dataset.optionIndex)];
      if (!option) return;
      await bindUnassignedCandidate(option);
    });
  });
}

async function fetchEmployees(force = false) {
  if (!force && state.employees.length) return state.employees;
  const response = await fetch("/api/employees");
  const payload = await response.json();
  state.employees = payload.items || [];
  if (state.selectedEmployeeId && !state.employees.some((item) => Number(item.id) === Number(state.selectedEmployeeId))) {
    state.selectedEmployeeId = null;
  }
  if (!state.selectedEmployeeId && state.employees.length) {
    state.selectedEmployeeId = Number(state.employees[0].id);
  }
  return state.employees;
}

async function fetchEmployeeKeywords(employeeId, force = false) {
  if (!employeeId) return [];
  if (!force && state.employeeKeywords[employeeId]) return state.employeeKeywords[employeeId];
  const response = await fetch(`/api/employees/${employeeId}/keywords`);
  const payload = await response.json();
  state.employeeKeywords[employeeId] = payload.items || [];
  renderKeywordTable();
  renderEmployeeManagerTable();
  return state.employeeKeywords[employeeId];
}

async function fetchEmployeeBindings(employeeId, force = false) {
  if (!employeeId) return [];
  if (!force && state.employeeBindings[employeeId]) return state.employeeBindings[employeeId];
  const response = await fetch(`/api/employees/${employeeId}/bindings`);
  const payload = await response.json();
  state.employeeBindings[employeeId] = payload.items || [];
  renderBindingTable();
  return state.employeeBindings[employeeId];
}

async function selectEmployeeManager(employeeId) {
  state.selectedEmployeeId = employeeId;
  const employee = selectedEmployeeRecord();
  fillEmployeeForm(employee);
  renderEmployeeManagerTable();
  await Promise.all([fetchEmployeeKeywords(employeeId, true), fetchEmployeeBindings(employeeId, true)]);
  renderMatchPreview();
}

async function ensureOwnershipData(force = false) {
  await fetchEmployees(force);
  renderEmployeeManagerTable();
  if (state.selectedEmployeeId) {
    fillEmployeeForm(selectedEmployeeRecord());
    await Promise.all([
      fetchEmployeeKeywords(state.selectedEmployeeId, force),
      fetchEmployeeBindings(state.selectedEmployeeId, force),
    ]);
  } else {
    resetEmployeeFormState();
  }
  await fetchUnassignedPool(force);
  renderUnassignedTable();
  renderMatchPreview();
}

function resetUserFormState() {
  state.selectedUserId = null;
  state.selectedUserScopeIds = [];
  if (userForm) userForm.reset();
  const enabledInput = userForm?.querySelector('input[name="enabled"]');
  if (enabledInput) enabledInput.checked = true;
  setInlineFeedback(
    userEditorStatus,
    isAdmin() ? "创建运营账号后，再勾选允许访问的账户范围。" : "只有管理员可以配置后台账号。",
    "neutral",
  );
  setInlineFeedback(
    scopeEditorMeta,
    isAdmin() ? "管理员默认全量可见；运营需要明确勾选账户范围。" : "当前账号无权修改账户范围。",
    "neutral",
  );
  renderScopeChecklist();
  if (isAdmin()) focusFirstInput(userForm, 'input[name="username"]');
}

function fillUserForm(user) {
  if (!userForm) return;
  userForm.querySelector('input[name="username"]').value = user?.username || "";
  userForm.querySelector('input[name="display_name"]').value = user?.display_name || "";
  userForm.querySelector('select[name="role"]').value = user?.role || "operator";
  userForm.querySelector('input[name="password"]').value = "";
  userForm.querySelector('input[name="enabled"]').checked = Boolean(user?.enabled);
  setInlineFeedback(
    userEditorStatus,
    user ? `当前编辑：${user.username} · ${user.role === "admin" ? "管理员" : "运营"}` : "创建运营账号后，再勾选允许访问的账户范围。",
    "neutral",
  );
}

function renderUserTable() {
  if (!userTable) return;
  if (!isAdmin()) {
    userTable.innerHTML = '<tbody><tr><td class="empty-cell">当前账号为只读角色，不能配置后台账号。</td></tr></tbody>';
    return;
  }
  userTable.innerHTML = `
    <thead>
      <tr>
        <th>用户名</th>
        <th>显示名</th>
        <th>角色</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      ${state.users.length ? state.users.map((item) => `
        <tr data-user-id="${item.id}" class="${Number(state.selectedUserId) === Number(item.id) ? "active-row" : ""}">
          <td>${escapeHtml(item.username)}</td>
          <td>${escapeHtml(item.display_name || "--")}</td>
          <td>${escapeHtml(item.role === "admin" ? "管理员" : "运营")}</td>
          <td><span class="pill">${item.enabled ? "启用" : "停用"}</span></td>
        </tr>
      `).join("") : '<tr><td colspan="4" class="empty-cell">还没有后台账号。</td></tr>'}
    </tbody>
  `;
  userTable.querySelectorAll("tbody tr[data-user-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      await selectUserManager(Number(row.dataset.userId));
    });
  });
}

function renderScopeChecklist() {
  if (!scopeAccountList) return;
  const user = selectedUserRecord();
  if (!isAdmin()) {
    scopeAccountList.innerHTML = '<div class="empty-cell">只有管理员可以配置账户范围。</div>';
    return;
  }
  if (!user) {
    scopeAccountList.innerHTML = '<div class="empty-cell">先选择后台账号，再配置账户范围。</div>';
    return;
  }
  if (user.role === "admin") {
    scopeAccountList.innerHTML = '<div class="empty-cell">管理员默认可查看全部账户，不需要单独勾选。</div>';
    return;
  }
  if (!state.catalogAccounts.length) {
    scopeAccountList.innerHTML = '<div class="empty-cell">还没有可分配的账户数据。</div>';
    return;
  }
  const selected = new Set((state.selectedUserScopeIds || []).map((item) => Number(item)));
  scopeAccountList.innerHTML = state.catalogAccounts.map((item) => `
    <label class="scope-check">
      <input type="checkbox" value="${item.advertiser_id}" ${selected.has(Number(item.advertiser_id)) ? "checked" : ""} />
      <span>${escapeHtml(item.advertiser_name || String(item.advertiser_id))}</span>
      <span class="scope-check-id mono">${formatNumber(item.advertiser_id)}</span>
    </label>
  `).join("");
}

async function fetchUsers(force = false) {
  if (!isAdmin()) {
    state.users = [];
    return [];
  }
  if (!force && state.users.length) return state.users;
  const response = await fetch("/api/users");
  const payload = await response.json();
  state.users = payload.items || [];
  if (state.selectedUserId && !state.users.some((item) => Number(item.id) === Number(state.selectedUserId))) {
    state.selectedUserId = null;
  }
  if (!state.selectedUserId && state.users.length) {
    state.selectedUserId = Number(state.users[0].id);
  }
  return state.users;
}

async function fetchCatalogAccounts(force = false) {
  if (!force && state.catalogAccounts.length) return state.catalogAccounts;
  const response = await fetch("/api/catalog/accounts");
  const payload = await response.json();
  state.catalogAccounts = payload.items || [];
  return state.catalogAccounts;
}

async function fetchUserScopes(userId, force = false) {
  if (!userId) return [];
  if (!isAdmin()) return [];
  if (!force && state.userScopes[userId]) return state.userScopes[userId];
  const response = await fetch(`/api/users/${userId}/account-scopes`);
  const payload = await response.json();
  state.userScopes[userId] = payload.advertiser_ids || [];
  return state.userScopes[userId];
}

async function selectUserManager(userId) {
  state.selectedUserId = userId;
  const user = selectedUserRecord();
  fillUserForm(user);
  renderUserTable();
  if (user && user.role !== "admin") {
    state.selectedUserScopeIds = await fetchUserScopes(userId, true);
  } else {
    state.selectedUserScopeIds = [];
  }
  renderScopeChecklist();
  if (isAdmin() && user && user.role !== "admin") {
    scopeAccountList.querySelector('input[type="checkbox"]')?.focus();
  }
}

async function ensureAccessData(force = false) {
  await Promise.all([fetchUsers(force), fetchCatalogAccounts(force)]);
  renderUserTable();
  if (state.selectedUserId) {
    fillUserForm(selectedUserRecord());
    const user = selectedUserRecord();
    if (user && user.role !== "admin" && isAdmin()) {
      state.selectedUserScopeIds = await fetchUserScopes(state.selectedUserId, force);
    } else {
      state.selectedUserScopeIds = [];
    }
  } else {
    resetUserFormState();
  }
  renderScopeChecklist();
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
  if (state.activeView === "ownership") {
    await fetchUnassignedPool(true);
    renderUnassignedTable();
  }
}

async function refreshMaterialSection(force = false) {
  syncSectionRangeControls("material");
  const payload = await fetchMaterialRankings(force);
  renderMaterialTable(payload?.items || []);
  syncSelectedMaterial(payload?.items || []);
  const meta = payload?.meta || {};
  const rangeText = formatDateWindowMeta(payload);
  const syncText = payload?.snapshot_time
    ? `${rangeText} · 汇总 ${formatNumber(payload?.snapshot_count || 0)} 个日快照 · 最近明细同步 ${payload.snapshot_time} · 素材 ${formatNumber(meta.material_count || meta.material_row_count || 0)} 行 · 错误 ${formatNumber(meta.error_count || 0)}`
    : `${rangeText} · 当前时间范围内暂无素材快照`;
  materialSyncMeta.textContent = syncText;
}

async function applyQuickRange(sectionKey, mode) {
  const current = sectionFilter(sectionKey);
  if (current.mode === mode) return;
  setSectionFilter(sectionKey, { mode });
  try {
    if (sectionKey === "material") {
      await refreshMaterialSection(true);
      return;
    }
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
    if (sectionKey === "material") {
      await refreshMaterialSection(true);
      return;
    }
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
        if (view === "materials") {
          await refreshMaterialSection(true);
        }
        if (view === "ownership") {
          await ensureOwnershipData(true);
        }
        if (view === "access") {
          await ensureAccessData(true);
        }
      });
    });
  }

  accountSearch.addEventListener("input", () => renderAccountTable(rangePayload(sectionFilter("account"))?.accounts || []));
  planSearch.addEventListener("input", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));
  employeeSearch.addEventListener("input", () => renderEmployeeTable(rangePayload(sectionFilter("breakdown"))?.employees || []));
  productSearch.addEventListener("input", () => renderProductTable(rangePayload(sectionFilter("breakdown"))?.products || []));
  materialSearch.addEventListener("input", () => renderMaterialTable(materialRangePayload(sectionFilter("material"))?.items || []));
  planAccountFilter.addEventListener("change", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));

  bindRangeFilterControls("account");
  bindRangeFilterControls("plan");
  bindRangeFilterControls("breakdown");
  bindRangeFilterControls("material");

  employeeForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(employeeForm);
    const payload = {
      display_name: String(form.get("display_name") || "").trim(),
      note: String(form.get("note") || "").trim(),
      enabled: form.get("enabled") === "on",
    };
    const url = state.selectedEmployeeId ? `/api/employees/${state.selectedEmployeeId}` : "/api/employees";
    const method = state.selectedEmployeeId ? "PUT" : "POST";
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "保存归属人失败");
      return;
    }
    const item = await response.json();
    await fetchEmployees(true);
    if (item?.id) {
      await selectEmployeeManager(Number(item.id));
      setInlineFeedback(employeeEditorStatus, `已保存归属人：${item.display_name || payload.display_name}。`, "success");
      setInlineFeedback(keywordStatus, "可以继续添加关键词，或先预览命中结果。", "success");
      focusFirstInput(keywordForm, 'input[name="keyword"]');
    } else {
      await ensureOwnershipData(true);
    }
    await fetchDashboard();
  });

  employeeFormReset?.addEventListener("click", () => {
    resetEmployeeFormState();
    renderEmployeeManagerTable();
    renderMatchPreview();
  });

  keywordForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.selectedEmployeeId) {
      window.alert("请先选择归属人");
      return;
    }
    const form = new FormData(keywordForm);
    const payload = {
      keyword: String(form.get("keyword") || "").trim(),
      scope: String(form.get("scope") || "all"),
      priority: Number(form.get("priority") || 100),
      enabled: form.get("enabled") === "on",
    };
    const response = await fetch(`/api/employees/${state.selectedEmployeeId}/keywords`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "新增关键词失败");
      return;
    }
    keywordForm.reset();
    keywordForm.querySelector('input[name="enabled"]').checked = true;
    keywordForm.querySelector('input[name="priority"]').value = "100";
    await fetchEmployeeKeywords(state.selectedEmployeeId, true);
    await fetchEmployees(true);
    fillEmployeeForm(selectedEmployeeRecord());
    renderEmployeeManagerTable();
    await fetchDashboard();
    setInlineFeedback(keywordStatus, `已新增关键词“${payload.keyword}”。`, "success");
    setInlineFeedback(matchPreviewMeta, "可继续预览命中，或等待榜单按新规则刷新。", "success");
    focusFirstInput(keywordForm, 'input[name="keyword"]');
  });

  matchPreviewForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const keyword = String(matchKeywordInput?.value || "").trim();
    const scope = String(matchScopeSelect?.value || "all");
    if (!keyword) {
      window.alert("请输入要预览的关键词");
      return;
    }
    const response = await fetch(`/api/employee-match-preview?keyword=${encodeURIComponent(keyword)}&scope=${encodeURIComponent(scope)}`);
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "关键词预览失败");
      return;
    }
    state.matchPreview = await response.json();
    renderMatchPreview();
  });

  unassignedScopeSelect?.addEventListener("change", async () => {
    state.unassignedScope = String(unassignedScopeSelect.value || "all");
    try {
      await fetchUnassignedPool(true);
      renderUnassignedTable();
    } catch (error) {
      window.alert(error.message || "未归属池加载失败");
    }
  });

  ruleForm?.querySelector('select[name="entity_type"]')?.addEventListener("change", () => {
    syncRuleFormFields();
  });

  ruleFormCancelButton?.addEventListener("click", () => {
    resetRuleFormState();
  });

  ruleTemplateButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const entityType = String(button.dataset.entity || "plan");
      const metric = String(button.dataset.metric || "");
      const operator = String(button.dataset.operator || "gte");
      const threshold = String(button.dataset.threshold || "");
      const minSpend = String(button.dataset.minSpend || "0");
      const note = String(button.dataset.note || "");
      ruleForm.querySelector('select[name="entity_type"]').value = entityType;
      syncRuleFormFields();
      ruleForm.querySelector('select[name="metric"]').value = metric || ruleForm.querySelector('select[name="metric"]').value;
      ruleForm.querySelector('select[name="operator"]').value = operator;
      ruleForm.querySelector('input[name="threshold"]').value = threshold;
      ruleForm.querySelector('input[name="min_spend"]').value = minSpend;
      ruleForm.querySelector('input[name="note"]').value = note;
      ruleForm.querySelector('input[name="target_id"]').value = "";
      if (ruleFormHint) {
        ruleFormHint.textContent = `已套用 ${button.textContent.trim()} 模板，可继续补充具体对象和阈值。`;
        ruleFormHint.dataset.tone = "neutral";
      }
    });
  });

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
    const ruleId = String(form.get("rule_id") || "").trim();
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
    const method = ruleId ? "PUT" : "POST";
    const url = ruleId ? `/api/alert-rules/${encodeURIComponent(ruleId)}` : "/api/alert-rules";
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "保存规则失败");
      return;
    }
    const savedLabel = payload.entity_type ? entityLabel(payload.entity_type) : String(form.get("entity_type") || "规则");
    resetRuleFormState();
    await fetchDashboard();
    if (ruleFormHint) {
      ruleFormHint.textContent = `已保存${savedLabel}规则。继续新增规则，或到下方列表调整状态。`;
      ruleFormHint.dataset.tone = "success";
    }
  });

  syncButton.addEventListener("click", async () => {
    syncButton.disabled = true;
    syncButton.textContent = "刷新中...";
    try {
      const response = await fetch("/api/sync", { method: "POST" });
      if (!response.ok) {
        throw new Error("刷新任务提交失败");
      }
      syncButton.textContent = "已加入队列";
      window.setTimeout(() => {
        fetchDashboard().catch(() => {});
      }, 1500);
    } finally {
      window.setTimeout(() => {
        syncButton.disabled = false;
        syncButton.textContent = "立即刷新";
      }, 1200);
    }
  });

  if (syncExtendedButton) {
    syncExtendedButton.addEventListener("click", async () => {
      syncExtendedButton.disabled = true;
      syncExtendedButton.textContent = "同步中...";
      try {
        const response = await fetch("/api/sync/extended", { method: "POST" });
        if (!response.ok) {
          throw new Error("明细同步任务提交失败");
        }
        syncExtendedButton.textContent = "已加入队列";
        window.setTimeout(() => {
          fetchDashboard().catch(() => {});
          refreshMaterialSection(true).catch(() => {});
        }, 2000);
      } finally {
        window.setTimeout(() => {
          syncExtendedButton.disabled = false;
          syncExtendedButton.textContent = "刷新素材";
        }, 1200);
      }
    });
  }

  userForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!isAdmin()) return;
    const form = new FormData(userForm);
    const payload = {
      username: String(form.get("username") || "").trim(),
      display_name: String(form.get("display_name") || "").trim(),
      role: String(form.get("role") || "operator"),
      password: String(form.get("password") || ""),
      enabled: form.get("enabled") === "on",
    };
    const url = state.selectedUserId ? `/api/users/${state.selectedUserId}` : "/api/users";
    const method = state.selectedUserId ? "PUT" : "POST";
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "保存账号失败");
      return;
    }
    const item = await response.json();
    await fetchUsers(true);
    if (item?.id) {
      await selectUserManager(Number(item.id));
      setInlineFeedback(userEditorStatus, `已保存账号：${item.username || payload.username}。`, "success");
      if (item.role !== "admin") {
        setInlineFeedback(scopeEditorMeta, "下一步勾选该账号允许访问的账户范围。", "success");
        scopeAccountList.querySelector('input[type="checkbox"]')?.focus();
      }
    } else {
      await ensureAccessData(true);
    }
  });

  userFormReset?.addEventListener("click", () => {
    resetUserFormState();
    renderUserTable();
  });

  saveUserScopesButton?.addEventListener("click", async () => {
    if (!isAdmin() || !state.selectedUserId) return;
    const user = selectedUserRecord();
    if (!user || user.role === "admin") {
      window.alert("管理员默认拥有全部权限，无需设置账户范围。");
      return;
    }
    const advertiserIds = [...scopeAccountList.querySelectorAll('input[type="checkbox"]:checked')].map((item) => Number(item.value));
    const response = await fetch(`/api/users/${state.selectedUserId}/account-scopes`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ advertiser_ids: advertiserIds }),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "保存账户范围失败");
      return;
    }
    const payload = await response.json();
    state.userScopes[state.selectedUserId] = payload.advertiser_ids || [];
    state.selectedUserScopeIds = state.userScopes[state.selectedUserId];
    renderScopeChecklist();
    setInlineFeedback(scopeEditorMeta, `已保存账户范围，共 ${formatNumber(state.selectedUserScopeIds.length)} 个账户。`, "success");
  });

  resetRuleFormState();
}

async function fetchDashboard() {
  const response = await fetch("/api/dashboard");
  const payload = await response.json();
  state.payload = payload;
  state.session = payload.session || null;
  if (!payload.latest) return;
  await render(payload);
}

async function render(payload) {
  const latest = payload.latest;
  applyRoleViewPolicy();
  renderOverviewHero(latest);
  renderKpis(latest);
  renderSystemCards(latest, payload.extendedSync || latest?.extendedSync, payload.tokenInfo || {});
  renderAlerts(payload.alertEvents || []);
  renderSignalOverview(payload.notificationSettings || {}, payload.alertRules || []);
  renderNotificationSettings(payload.notificationSettings || {});
  renderRuleTable(payload.alertRules || []);
  syncRuleFormFields();
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
  if (state.activeView === "ownership") {
    try {
      await ensureOwnershipData(true);
    } catch (error) {
      console.error("ensureOwnershipData failed", error);
    }
  }
  if (state.activeView === "access") {
    try {
      await ensureAccessData(true);
    } catch (error) {
      console.error("ensureAccessData failed", error);
    }
  }
  setActiveView(state.activeView);
}

bindInputs();
setActiveView(state.activeView);
fetchDashboard();
window.setInterval(fetchDashboard, 60 * 1000);
