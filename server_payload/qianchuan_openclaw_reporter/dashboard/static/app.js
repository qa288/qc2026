const RANGE_LABELS = {
  day: "今日",
  yesterday: "昨日",
  week: "近7天",
  month: "近30天",
  custom: "指定日期范围",
};

const DISPLAY_SCOPE_CURRENT = "current";
const DISPLAY_SCOPE_ALL = "all";
const DISPLAY_SCOPE_PREFERENCE_KEY = "dashboard-display-scope";
const DISPLAY_SCOPE_MIGRATION_KEY = "dashboard-display-scope-default-all-v1";

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

const MATERIAL_PAGE_SIZE = 100;
const MATERIAL_CACHE_TTL_MS = 55 * 1000;
const MATERIAL_SEARCH_DEBOUNCE_MS = 180;
const COMMENT_PAGE_SIZE = 50;
const COMMENT_CACHE_TTL_MS = 30 * 1000;
const COMMENT_SEARCH_DEBOUNCE_MS = 180;
const MATERIAL_TOTAL_PAY_TYPES = new Set(["VIDEO", "IMAGE", "TITLE"]);
const MATERIAL_SETTLED_TYPES = new Set(["VIDEO", "IMAGE"]);

const state = {
  payload: null,
  alertRules: [],
  session: null,
  oceanEngineConfig: null,
  oceanEnginePreview: null,
  oceanEnginePopoverOpen: false,
  oceanEnginePendingCustomerCenterId: "",
  rangePayloads: {},
  planAssetCache: {},
  materialPayloads: {},
  materialPayloadFetchedAt: {},
  teamMaterialPayloads: {},
  teamMaterialPayloadFetchedAt: {},
  commentPayloads: {},
  commentPayloadFetchedAt: {},
  materialPreviewCurveCache: {},
  users: [],
  catalogAccounts: [],
  userScopes: {},
  userKeywords: {},
  userMatchedMaterials: {},
  uploadTargets: null,
  uploadJobs: [],
  uploadSelectedPlanIds: [],
  uploadFiles: [],
  uploadRetryingJobId: null,
  uploadDeletingJobId: null,
  displayScope: DISPLAY_SCOPE_ALL,
  unassignedScope: "all",
  accountSort: loadSort("account-sort", { key: "stat_cost", dir: "desc" }),
  planSort: loadSort("plan-sort", { key: "order_count", dir: "desc" }),
  employeeSort: loadSort("employee-sort", { key: "stat_cost", dir: "desc" }),
  productSort: loadSort("product-sort", { key: "order_count", dir: "desc" }),
  materialSort: loadSort("material-sort", { key: "create_time", dir: "desc" }),
  teamMaterialSort: loadSort("team-material-sort", { key: "create_time", dir: "desc" }),
  commentSort: loadSort("comment-sort", { key: "create_time", dir: "desc" }),
  activeView: loadPreference("active-view", "overview"),
  ruleTargetOptions: [],
  performanceFilters: {
    account: loadRangeFilter("account-range-filter", "day"),
    plan: loadRangeFilter("plan-range-filter", "day"),
    breakdown: loadRangeFilter("breakdown-range-filter", "day"),
    material: loadRangeFilter("material-range-filter", "day"),
    teamMaterial: loadRangeFilter("team-material-range-filter", "day"),
    comment: loadRangeFilter("comment-range-filter", "day"),
  },
  rangeEditorOpen: {},
  materialPage: 1,
  teamMaterialPage: 1,
  commentPage: 1,
  selectedEmployeeName: null,
  selectedPlanId: null,
  selectedProductKey: null,
  selectedMaterialKey: null,
  commentReplyTarget: null,
  materialPreviewRequestToken: 0,
  selectedUserId: null,
  selectedUserScopeIds: [],
  editingRuleId: null,
};

const kpiGrid = document.getElementById("kpiGrid");
const alertStream = document.getElementById("alertStream");
const accountTable = document.getElementById("accountTable");
const planTable = document.getElementById("planTable");
const employeeTable = document.getElementById("employeeTable");
const ruleTable = document.getElementById("ruleTable");
const materialTable = document.getElementById("materialTable");
const materialTablePager = document.getElementById("materialTablePager");
const teamMaterialTable = document.getElementById("teamMaterialTable");
const teamMaterialTablePager = document.getElementById("teamMaterialTablePager");
const commentTable = document.getElementById("commentTable");
const commentTablePager = document.getElementById("commentTablePager");
const alertSummary = document.getElementById("alertSummary");
const accountSearch = document.getElementById("accountSearch");
const planSearch = document.getElementById("planSearch");
const employeeSearch = document.getElementById("employeeSearch");
const productSearch = document.getElementById("productSearch");
const breakdownTitle = document.getElementById("breakdownTitle");
const teamPanelTitle = document.getElementById("teamPanelTitle");
const materialSearch = document.getElementById("materialSearch");
const teamMaterialSearch = document.getElementById("teamMaterialSearch");
const commentSearch = document.getElementById("commentSearch");
const productTable = document.getElementById("productTable");
const employeeDetail = document.getElementById("employeeDetail");
const productDetail = document.getElementById("productDetail");
const productRankPanel = document.getElementById("productRankPanel");
const planDetailStage = document.getElementById("planDetailStage");
const planDetail = document.getElementById("planDetail");
const planAssetSummary = document.getElementById("planAssetSummary");
const materialDetailStage = document.getElementById("materialDetailStage");
const materialDetail = document.getElementById("materialDetail");
const planAccountFilter = document.getElementById("planAccountFilter");
const notificationForm = document.getElementById("notificationForm");
const notificationStatus = document.getElementById("notificationStatus");
const notificationGuide = document.getElementById("notificationGuide");
const ruleForm = document.getElementById("ruleForm");
const ruleFormHint = document.getElementById("ruleFormHint");
const rulePreviewCard = document.getElementById("rulePreviewCard");
const ruleFormSubmitButton = document.getElementById("ruleFormSubmitButton");
const ruleFormCancelButton = document.getElementById("ruleFormCancelButton");
const ruleTargetInput = document.getElementById("ruleTargetInput");
const ruleTargetSearchInput = document.getElementById("ruleTargetSearchInput");
const ruleTargetLabel = document.getElementById("ruleTargetLabel");
const ruleTargetOptions = document.getElementById("ruleTargetOptions");
const ruleTargetMeta = document.getElementById("ruleTargetMeta");
const ruleMinSpendField = document.getElementById("ruleMinSpendField");
const ruleStatusFilter = document.getElementById("ruleStatusFilter");
const ruleSearchInput = document.getElementById("ruleSearchInput");
const ruleListMeta = document.getElementById("ruleListMeta");
const syncButton = document.getElementById("syncButton");
const syncExtendedButton = document.getElementById("syncExtendedButton");
const customerCenterChip = document.getElementById("customerCenterChip");
const heroStatusText = document.getElementById("heroStatusText");
const heroStatusHint = document.getElementById("heroStatusHint");
const heroCopy = document.getElementById("heroCopy");
const lastSnapshotText = document.getElementById("lastSnapshotText");
const refreshHintText = document.getElementById("refreshHintText");
const systemStatusCard = document.getElementById("systemStatusCard");
const detailSyncCard = document.getElementById("detailSyncCard");
const signalOverview = document.getElementById("signalOverview");
const overviewHeroCard = document.getElementById("overviewHeroCard");
const overviewBoardGrid = document.getElementById("overviewBoardGrid");
const overviewAlertTitle = document.getElementById("overviewAlertTitle");
const overviewAlertMeta = document.getElementById("overviewAlertMeta");
const overviewSystemRail = document.querySelector(".system-rail");
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
const materialsPanelTitle = document.getElementById("materialsPanelTitle");
const teamMaterialRangeSwitch = document.getElementById("teamMaterialRangeSwitch");
const teamMaterialDateStart = document.getElementById("teamMaterialDateStart");
const teamMaterialDateEnd = document.getElementById("teamMaterialDateEnd");
const teamMaterialDateApply = document.getElementById("teamMaterialDateApply");
const teamMaterialSyncMeta = document.getElementById("teamMaterialSyncMeta");
const teamMaterialsPanelTitle = document.getElementById("teamMaterialsPanelTitle");
const commentsPanelTitle = document.getElementById("commentsPanelTitle");
const commentRangeSwitch = document.getElementById("commentRangeSwitch");
const commentDateStart = document.getElementById("commentDateStart");
const commentDateEnd = document.getElementById("commentDateEnd");
const commentDateApply = document.getElementById("commentDateApply");
const commentSyncMeta = document.getElementById("commentSyncMeta");
const commentAccountFilter = document.getElementById("commentAccountFilter");
const commentRefreshButton = document.getElementById("commentRefreshButton");
const userTable = document.getElementById("userTable");
const userForm = document.getElementById("userForm");
const userFormReset = document.getElementById("userFormReset");
const accessOverview = document.getElementById("accessOverview");
const oceanEngineConfigCard = document.getElementById("oceanEngineConfigCard");
const oceanEngineConfigForm = document.getElementById("oceanEngineConfigForm");
const oceanEngineConfigStatus = document.getElementById("oceanEngineConfigStatus");
const oceanEngineConfigMeta = document.getElementById("oceanEngineConfigMeta");
const oceanEngineConfigPreview = document.getElementById("oceanEngineConfigPreview");
const oceanEngineBoundAccounts = document.getElementById("oceanEngineBoundAccounts");
const oceanEngineBoundAccountsMeta = document.getElementById("oceanEngineBoundAccountsMeta");
const userEditorStatus = document.getElementById("userEditorStatus");
const uploadPermissionField = document.getElementById("uploadPermissionField");
const operatorKeywordSeedField = document.getElementById("operatorKeywordSeedField");
const scopeControls = document.getElementById("scopeControls");
const scopeSearchInput = document.getElementById("scopeSearchInput");
const scopeSelectVisibleButton = document.getElementById("scopeSelectVisibleButton");
const scopeClearSelectedButton = document.getElementById("scopeClearSelectedButton");
const scopeSelectionSummary = document.getElementById("scopeSelectionSummary");
const scopeAccountList = document.getElementById("scopeAccountList");
const saveUserScopesButton = document.getElementById("saveUserScopesButton");
const scopeEditorMeta = document.getElementById("scopeEditorMeta");
const operatorKeywordSection = document.getElementById("operatorKeywordSection");
const operatorKeywordStatus = document.getElementById("operatorKeywordStatus");
const operatorKeywordForm = document.getElementById("operatorKeywordForm");
const operatorKeywordTable = document.getElementById("operatorKeywordTable");
const operatorMaterialSection = document.getElementById("operatorMaterialSection");
const operatorMaterialStatus = document.getElementById("operatorMaterialStatus");
const toggleOperatorMaterialsButton = document.getElementById("toggleOperatorMaterialsButton");
const operatorMaterialContent = document.getElementById("operatorMaterialContent");
const operatorMaterialSearch = document.getElementById("operatorMaterialSearch");
const operatorMaterialTable = document.getElementById("operatorMaterialTable");
const uploadSearchForm = document.getElementById("uploadSearchForm");
const uploadScopeSelect = document.getElementById("uploadScopeSelect");
const uploadKeywordInput = document.getElementById("uploadKeywordInput");
const uploadTargetMeta = document.getElementById("uploadTargetMeta");
const uploadSelectAll = document.getElementById("uploadSelectAll");
const uploadTargetSummary = document.getElementById("uploadTargetSummary");
const uploadTargetTable = document.getElementById("uploadTargetTable");
const uploadJobForm = document.getElementById("uploadJobForm");
const uploadFileInput = document.getElementById("uploadFileInput");
const uploadFileSummary = document.getElementById("uploadFileSummary");
const uploadJobStatus = document.getElementById("uploadJobStatus");
const uploadJobSubmit = document.getElementById("uploadJobSubmit");
const uploadJobTable = document.getElementById("uploadJobTable");
const materialPreviewModal = document.getElementById("materialPreviewModal");
const materialPreviewTitle = document.getElementById("materialPreviewTitle");
const materialPreviewMeta = document.getElementById("materialPreviewMeta");
const materialPreviewBody = document.getElementById("materialPreviewBody");
const commentReplyModal = document.getElementById("commentReplyModal");
const commentReplyTitle = document.getElementById("commentReplyTitle");
const commentReplyMeta = document.getElementById("commentReplyMeta");
const commentReplyInput = document.getElementById("commentReplyInput");
const commentReplyStatus = document.getElementById("commentReplyStatus");
const commentReplySubmit = document.getElementById("commentReplySubmit");
const relationDetailModal = document.getElementById("relationDetailModal");
const relationDetailTitle = document.getElementById("relationDetailTitle");
const relationDetailMeta = document.getElementById("relationDetailMeta");
const relationDetailBody = document.getElementById("relationDetailBody");
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
  teamMaterial: {
    storageKey: "team-material-range-filter",
    switchEl: teamMaterialRangeSwitch,
    metaEl: teamMaterialSyncMeta,
    startEl: teamMaterialDateStart,
    endEl: teamMaterialDateEnd,
    applyEl: teamMaterialDateApply,
  },
  comment: {
    storageKey: "comment-range-filter",
    switchEl: commentRangeSwitch,
    metaEl: commentSyncMeta,
    startEl: commentDateStart,
    endEl: commentDateEnd,
    applyEl: commentDateApply,
  },
};

Object.entries(state.performanceFilters).forEach(([sectionKey, filter]) => {
  state.rangeEditorOpen[sectionKey] = filter.mode === "custom";
});

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

function normalizeDisplayScope(value) {
  return String(value || "").trim().toLowerCase() === DISPLAY_SCOPE_ALL
    ? DISPLAY_SCOPE_ALL
    : DISPLAY_SCOPE_CURRENT;
}

function loadDisplayScopePreference() {
  try {
    const saved = localStorage.getItem(DISPLAY_SCOPE_PREFERENCE_KEY);
    const migrated = localStorage.getItem(DISPLAY_SCOPE_MIGRATION_KEY);
    if (!migrated) {
      localStorage.setItem(DISPLAY_SCOPE_PREFERENCE_KEY, DISPLAY_SCOPE_ALL);
      localStorage.setItem(DISPLAY_SCOPE_MIGRATION_KEY, "1");
      return DISPLAY_SCOPE_ALL;
    }
    return normalizeDisplayScope(saved || DISPLAY_SCOPE_ALL);
  } catch {
    return DISPLAY_SCOPE_ALL;
  }
}

state.displayScope = loadDisplayScopePreference();

function requestDisplayScope() {
  if (!isAdmin()) {
    return DISPLAY_SCOPE_CURRENT;
  }
  return normalizeDisplayScope(state.displayScope);
}

function usingAllCustomerCenters() {
  return requestDisplayScope() === DISPLAY_SCOPE_ALL;
}

function setDisplayScope(nextScope, options = {}) {
  const normalized = normalizeDisplayScope(nextScope);
  const previous = normalizeDisplayScope(state.displayScope);
  state.displayScope = normalized;
  if (options.persist !== false) {
    savePreference(DISPLAY_SCOPE_PREFERENCE_KEY, normalized);
    savePreference(DISPLAY_SCOPE_MIGRATION_KEY, "1");
  }
  if (options.clearCaches !== false && previous !== normalized) {
    clearDashboardDataCaches();
  }
}

function appendDisplayScopeParam(params) {
  params.set("display_scope", requestDisplayScope());
  return params;
}

function debounce(callback, waitMs) {
  let timeoutId = 0;
  return (...args) => {
    window.clearTimeout(timeoutId);
    timeoutId = window.setTimeout(() => callback(...args), waitMs);
  };
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
    start.setDate(start.getDate() - 6);
  } else if (mode === "month") {
    start.setDate(start.getDate() - 29);
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

function formatPercent(value) {
  return `${Number(value || 0).toFixed(2)}%`;
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
    wechat: "微信",
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

function parseKeywordSeedInput(value) {
  return [...new Set(
    String(value || "")
      .split(/[\n,，、;；]+/)
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  )];
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

function ruleTargetLookupMaps(options) {
  const byLabel = new Map();
  const byValue = new Map();
  for (const item of options || []) {
    const label = String(item.label || "").trim();
    const value = String(item.value || "").trim();
    if (!label || !value) continue;
    byLabel.set(label, value);
    byValue.set(value, label);
  }
  return { byLabel, byValue };
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
  if (ruleTargetSearchInput) ruleTargetSearchInput.value = "";
  if (ruleTargetInput) ruleTargetInput.value = "";
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
  renderRulePreview();
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
  if (ruleTargetSearchInput) {
    ruleTargetSearchInput.value = targetDisplayLabel(String(rule.entity_type || "plan"), String(rule.target_id || ""));
  }
  ruleForm.querySelector('input[name="note"]').value = String(rule.note || "");
  ruleForm.querySelector('input[name="enabled"]').checked = Boolean(rule.enabled);
  if (ruleFormSubmitButton) ruleFormSubmitButton.textContent = "保存规则";
  if (ruleFormCancelButton) ruleFormCancelButton.classList.remove("hidden");
  syncRuleFormFields();
  if (ruleFormHint) {
    ruleFormHint.textContent = `正在编辑 ${entityLabel(rule.entity_type)}规则，可直接调整阈值、范围或启停状态。`;
    ruleFormHint.dataset.tone = "neutral";
  }
  renderRulePreview();
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
  ruleTargetSearchInput.placeholder = config.targetPlaceholder;
  ruleMinSpendField.classList.toggle("hidden", !config.supportsMinSpend);
  minSpendInput.disabled = !config.supportsMinSpend;
  if (!config.supportsMinSpend) {
    minSpendInput.value = "0";
  }
  const targetOptions = entityTargetOptions(entityType);
  state.ruleTargetOptions = targetOptions;
  ruleTargetOptions.innerHTML = targetOptions
    .slice(0, 400)
    .map((item) => `<option value="${escapeHtml(item.label)}"></option>`)
    .join("");
  const targetMaps = ruleTargetLookupMaps(targetOptions);
  const currentTargetId = String(ruleTargetInput.value || "").trim();
  if (currentTargetId) {
    const currentLabel = targetMaps.byValue.get(currentTargetId);
    if (currentLabel) {
      ruleTargetSearchInput.value = currentLabel;
    } else {
      ruleTargetInput.value = "";
      ruleTargetSearchInput.value = "";
    }
  }
  if (ruleTargetMeta) {
    const targetScopeHelp = config.targetSource === "sharedWallets"
      ? "支持按钱包名称关键词搜索"
      : config.targetSource === "accountBalances"
        ? "支持按账户名称关键词搜索"
        : config.targetSource === "plans"
          ? "支持按计划名称关键词搜索"
          : "支持按账户名称关键词搜索";
    ruleTargetMeta.textContent = `输入关键词筛选候选对象，并从下拉项中选择；留空表示全部。${targetScopeHelp}。`;
    if (!ruleTargetMeta.dataset.tone || ruleTargetMeta.dataset.tone === "neutral") {
      ruleTargetMeta.dataset.tone = "neutral";
    }
  }
  if (ruleFormHint) {
    const modeLabel = state.editingRuleId ? "当前为编辑模式" : "当前为新增模式";
    const targetLabel = targetOptions.length ? `可选对象 ${formatNumber(targetOptions.length)} 个` : "当前暂无可选对象";
    const minSpendLabel = config.supportsMinSpend ? "支持最低消耗门槛" : "当前对象不使用最低消耗";
    ruleFormHint.textContent = `${modeLabel} · ${config.label}规则 · ${targetLabel} · ${minSpendLabel}`;
    if (!ruleFormHint.dataset.tone || ruleFormHint.dataset.tone === "neutral") {
      ruleFormHint.dataset.tone = "neutral";
    }
  }
  renderRulePreview();
}

function syncRuleTargetSelectionFromSearch() {
  if (!ruleTargetSearchInput || !ruleTargetInput) return;
  const text = String(ruleTargetSearchInput.value || "").trim();
  if (!text) {
    ruleTargetInput.value = "";
    if (ruleTargetMeta) {
      ruleTargetMeta.textContent = "留空表示全部对象；输入关键词后请从候选项中选择具体对象。";
      ruleTargetMeta.dataset.tone = "neutral";
    }
    renderRulePreview();
    return;
  }
  const targetMaps = ruleTargetLookupMaps(state.ruleTargetOptions || []);
  const resolved = targetMaps.byLabel.get(text);
  if (resolved) {
    ruleTargetInput.value = resolved;
    if (ruleTargetMeta) {
      ruleTargetMeta.textContent = `已选中：${text}`;
      ruleTargetMeta.dataset.tone = "success";
    }
    renderRulePreview();
    return;
  }
  ruleTargetInput.value = "";
  if (ruleTargetMeta) {
    ruleTargetMeta.textContent = "请输入关键词后，从下拉候选项中选择一个具体对象；留空表示全部。";
    ruleTargetMeta.dataset.tone = "neutral";
  }
  renderRulePreview();
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

function planSourceTone(source) {
  if (source === "STANDARD") return "standard";
  if (source === "UNI_PROMOTION") return "uni";
  return "neutral";
}

function renderPlanSourceBadge(row) {
  const source = String(row?.plan_source || "").trim().toUpperCase();
  const deliveryType = String(row?.plan_delivery_type || "").trim().toUpperCase();
  const text = row?.plan_source_text || (deliveryType === "CUBIC" ? "\u4e58\u65b9\u6295\u653e" : "\u5168\u57df\u6295\u653e");
  const tone = planSourceTone(source);
  const title = source || text;
  return `<span class="pill plan-source-pill ${tone}" title="${escapeHtml(title)}">${escapeHtml(text)}</span>`;
}

function enrichPlanRow(row) {
  const statCost = Number(row?.stat_cost || 0);
  const totalPayAmount = Number(row?.total_pay_amount || 0);
  const settledPayAmount = Number(row?.settled_pay_amount || 0);
  const orderCount = Number(row?.order_count || 0);
  const settledOrderCount = Number(row?.settled_order_count || 0);
  const refundAmount1h = Number(row?.refund_amount_1h || 0);
  return {
    ...row,
    plan_source_text: row?.plan_source_text || (String(row?.plan_delivery_type || "").trim().toUpperCase() === "CUBIC" ? "\u4e58\u65b9\u6295\u653e" : "\u5168\u57df\u6295\u653e"),
    marketing_goal_text: row?.marketing_goal_text || row?.marketing_goal_label || row?.marketing_goal || "-",
    status_text: row?.status_text || `${row?.status || ""}/${row?.opt_status || ""}`,
    settled_roi: statCost > 0 ? Number((settledPayAmount / statCost).toFixed(2)) : Number(row?.settled_roi || 0),
    settled_order_count: settledOrderCount,
    pay_order_cost: orderCount > 0 ? Number((statCost / orderCount).toFixed(2)) : Number(row?.pay_order_cost || 0),
    settled_amount_rate: totalPayAmount > 0
      ? Number((settledPayAmount / totalPayAmount * 100).toFixed(2))
      : Number(row?.settled_amount_rate || 0),
    refund_rate_1h: totalPayAmount > 0
      ? Number((refundAmount1h / totalPayAmount * 100).toFixed(2))
      : Number(row?.refund_rate_1h || 0),
  };
}

function materialTypeKey(row) {
  return String(row?.material_type || "").trim().toUpperCase();
}

function materialSupportsTotalPayMetrics(row) {
  return MATERIAL_TOTAL_PAY_TYPES.has(materialTypeKey(row));
}

function materialSupportsSettledMetrics(row) {
  return MATERIAL_SETTLED_TYPES.has(materialTypeKey(row));
}

function enrichMaterialRow(row) {
  const statCost = Number(row?.stat_cost || 0);
  const totalPayAmount = Number(row?.total_pay_amount || 0);
  const settledPayAmount = Number(row?.settled_pay_amount || 0);
  const orderCount = Number(row?.order_count || 0);
  const settledOrderCount = Number(row?.settled_order_count || 0);
  const overallShowCount = Number(row?.overall_show_count || 0);
  const overallClickCount = Number(row?.overall_click_count || 0);
  return {
    ...row,
    create_time: String(row?.create_time || "").trim(),
    product_info_text: String(row?.product_info_text || "").trim(),
    top_anchor_name: String(row?.top_anchor_name || "").trim(),
    overall_show_count: overallShowCount,
    overall_click_count: overallClickCount,
    overall_ctr: overallShowCount > 0
      ? Number((overallClickCount / overallShowCount * 100).toFixed(2))
      : Number(row?.overall_ctr || 0),
    total_pay_amount: totalPayAmount,
    settled_pay_amount: settledPayAmount,
    settled_order_count: settledOrderCount,
    settled_roi: statCost > 0 ? Number((settledPayAmount / statCost).toFixed(2)) : Number(row?.settled_roi || 0),
    pay_order_cost: orderCount > 0 ? Number((statCost / orderCount).toFixed(2)) : Number(row?.pay_order_cost || 0),
    settled_amount_rate: totalPayAmount > 0
      ? Number((settledPayAmount / totalPayAmount * 100).toFixed(2))
      : Number(row?.settled_amount_rate || 0),
  };
}

function enrichOperatorRow(row) {
  const statCost = Number(row?.stat_cost || 0);
  const totalPayAmount = Number(row?.total_pay_amount || 0);
  const settledPayAmount = Number(row?.settled_pay_amount || 0);
  const orderCount = Number(row?.order_count || 0);
  const settledOrderCount = Number(row?.settled_order_count || 0);
  const refundAmount1h = Number(row?.refund_amount_1h || 0);
  const refundRateAvailable = row?.refund_rate_1h !== null && row?.refund_rate_1h !== undefined;
  return {
    ...row,
    total_pay_amount: totalPayAmount,
    settled_pay_amount: settledPayAmount,
    settled_order_count: settledOrderCount,
    settled_roi: statCost > 0 ? Number((settledPayAmount / statCost).toFixed(2)) : Number(row?.settled_roi || 0),
    pay_order_cost: orderCount > 0 ? Number((statCost / orderCount).toFixed(2)) : Number(row?.pay_order_cost || 0),
    settled_amount_rate: totalPayAmount > 0
      ? Number((settledPayAmount / totalPayAmount * 100).toFixed(2))
      : Number(row?.settled_amount_rate || 0),
    refund_amount_1h: refundAmount1h,
    refund_rate_1h: refundRateAvailable ? Number(row?.refund_rate_1h || 0) : null,
    refund_rate_1h_available: refundRateAvailable,
    material_count: Number(row?.material_count ?? row?.plan_count ?? 0),
    advertiser_count: Number(row?.advertiser_count || 0),
    keyword_count: Number(row?.keyword_count || 0),
    plan_count: Number(row?.plan_count || 0),
  };
}

function buildAccountMetricsFromPlans(plans) {
  const metrics = new Map();
  plans.map((row) => enrichPlanRow(row)).forEach((row) => {
    const advertiserId = Number(row?.advertiser_id || 0);
    if (!advertiserId) return;
    const group = metrics.get(advertiserId) || {
      advertiser_id: advertiserId,
      stat_cost: 0,
      pay_amount: 0,
      total_pay_amount: 0,
      settled_pay_amount: 0,
      order_count: 0,
      settled_order_count: 0,
      refund_amount_1h: 0,
      plan_count: 0,
      top_plan_name: "",
      top_plan_orders: -1,
      top_plan_pay_amount: -1,
    };
    const statCost = Number(row?.stat_cost || 0);
    const payAmount = Number(row?.pay_amount || 0);
    const totalPayAmount = Number(row?.total_pay_amount || 0);
    const settledPayAmount = Number(row?.settled_pay_amount || 0);
    const orderCount = Number(row?.order_count || 0);
    const settledOrderCount = Number(row?.settled_order_count || 0);
    const refundAmount1h = Number(row?.refund_amount_1h || 0);
    group.stat_cost = Number((group.stat_cost + statCost).toFixed(2));
    group.pay_amount = Number((group.pay_amount + payAmount).toFixed(2));
    group.total_pay_amount = Number((group.total_pay_amount + totalPayAmount).toFixed(2));
    group.settled_pay_amount = Number((group.settled_pay_amount + settledPayAmount).toFixed(2));
    group.order_count += orderCount;
    group.settled_order_count += settledOrderCount;
    group.refund_amount_1h = Number((group.refund_amount_1h + refundAmount1h).toFixed(2));
    group.plan_count += 1;
    if (
      orderCount > group.top_plan_orders
      || (orderCount === group.top_plan_orders && payAmount > group.top_plan_pay_amount)
    ) {
      group.top_plan_name = String(row?.ad_name || "").trim();
      group.top_plan_orders = orderCount;
      group.top_plan_pay_amount = payAmount;
    }
    metrics.set(advertiserId, group);
  });
  return metrics;
}

function enrichAccountRow(row, accountMetrics) {
  const advertiserId = Number(row?.advertiser_id || 0);
  const metrics = accountMetrics.get(advertiserId) || {};
  const statCost = Number(metrics.stat_cost ?? row?.stat_cost ?? 0);
  const payAmount = Number(metrics.pay_amount ?? row?.pay_amount ?? 0);
  const totalPayAmount = Number(metrics.total_pay_amount || 0);
  const settledPayAmount = Number(metrics.settled_pay_amount || 0);
  const orderCount = Number(metrics.order_count ?? row?.order_count ?? 0);
  const settledOrderCount = Number(metrics.settled_order_count || 0);
  const refundAmount1h = Number(metrics.refund_amount_1h || 0);
  return {
    ...row,
    stat_cost: statCost,
    pay_amount: payAmount,
    total_pay_amount: totalPayAmount,
    settled_pay_amount: settledPayAmount,
    order_count: orderCount,
    settled_order_count: settledOrderCount,
    refund_amount_1h: refundAmount1h,
    plan_count: Number(metrics.plan_count || 0),
    top_plan_name: String(metrics.top_plan_name || "").trim(),
    roi: statCost > 0 ? Number((payAmount / statCost).toFixed(2)) : Number(row?.roi || 0),
    settled_roi: statCost > 0 ? Number((settledPayAmount / statCost).toFixed(2)) : Number(row?.settled_roi || 0),
    pay_order_cost: orderCount > 0 ? Number((statCost / orderCount).toFixed(2)) : Number(row?.pay_order_cost || 0),
    settled_amount_rate: totalPayAmount > 0
      ? Number((settledPayAmount / totalPayAmount * 100).toFixed(2))
      : Number(row?.settled_amount_rate || 0),
    refund_rate_1h: totalPayAmount > 0
      ? Number((refundAmount1h / totalPayAmount * 100).toFixed(2))
      : Number(row?.refund_rate_1h || 0),
  };
}

function productKeyForItem(item) {
  const productId = String(item?.product_id || "").trim();
  const productName = String(item?.product_name || "").trim();
  if (productId) return `id:${productId}`;
  if (productName) return `name:${productName}`;
  return "unlinked";
}

function buildPlanRelationItems(plans) {
  return plans
    .map((row) => enrichPlanRow(row))
    .sort((left, right) => {
      const orderDelta = Number(right.order_count || 0) - Number(left.order_count || 0);
      if (orderDelta) return orderDelta;
      const payDelta = Number(right.pay_amount || 0) - Number(left.pay_amount || 0);
      if (payDelta) return payDelta;
      const costDelta = Number(right.stat_cost || 0) - Number(left.stat_cost || 0);
      if (costDelta) return costDelta;
      return Number(left.ad_id || 0) - Number(right.ad_id || 0);
    });
}

function buildAccountRelationItemsFromPlans(plans) {
  const groups = new Map();
  plans.map((row) => enrichPlanRow(row)).forEach((row) => {
    const advertiserId = Number(row?.advertiser_id || 0);
    if (!advertiserId) return;
    const group = groups.get(advertiserId) || {
      advertiser_id: advertiserId,
      advertiser_name: String(row?.advertiser_name || "").trim(),
      stat_cost: 0,
      pay_amount: 0,
      order_count: 0,
      plan_count: 0,
      top_plan_name: "",
      top_plan_orders: -1,
      top_plan_pay_amount: -1,
    };
    const statCost = Number(row?.stat_cost || 0);
    const payAmount = Number(row?.pay_amount || 0);
    const orderCount = Number(row?.order_count || 0);
    group.stat_cost = Number((group.stat_cost + statCost).toFixed(2));
    group.pay_amount = Number((group.pay_amount + payAmount).toFixed(2));
    group.order_count += orderCount;
    group.plan_count += 1;
    if (
      orderCount > group.top_plan_orders
      || (orderCount === group.top_plan_orders && payAmount > group.top_plan_pay_amount)
    ) {
      group.top_plan_name = String(row?.ad_name || "").trim();
      group.top_plan_orders = orderCount;
      group.top_plan_pay_amount = payAmount;
    }
    groups.set(advertiserId, group);
  });
  return [...groups.values()].sort((left, right) => {
    const costDelta = Number(right.stat_cost || 0) - Number(left.stat_cost || 0);
    if (costDelta) return costDelta;
    const planDelta = Number(right.plan_count || 0) - Number(left.plan_count || 0);
    if (planDelta) return planDelta;
    const orderDelta = Number(right.order_count || 0) - Number(left.order_count || 0);
    if (orderDelta) return orderDelta;
    return Number(left.advertiser_id || 0) - Number(right.advertiser_id || 0);
  });
}

function loadedPlanLookup() {
  const lookup = new Map();
  Object.values(state.rangePayloads || {}).forEach((payload) => {
    (payload?.plans || []).forEach((row) => {
      const plan = enrichPlanRow(row);
      const adId = Number(plan.ad_id || 0);
      if (!adId || lookup.has(adId)) return;
      lookup.set(adId, plan);
    });
  });
  return lookup;
}

function loadedAccountLookup() {
  const lookup = new Map();
  Object.values(state.rangePayloads || {}).forEach((payload) => {
    (payload?.accounts || []).forEach((row) => {
      const advertiserId = Number(row?.advertiser_id || 0);
      if (!advertiserId || lookup.has(advertiserId)) return;
      lookup.set(advertiserId, row);
    });
  });
  (state.catalogAccounts || []).forEach((row) => {
    const advertiserId = Number(row?.advertiser_id || 0);
    if (!advertiserId || lookup.has(advertiserId)) return;
    lookup.set(advertiserId, row);
  });
  return lookup;
}

function resolvePlanRelationItemsByIds(planIds) {
  const lookup = loadedPlanLookup();
  const uniquePlanIds = [...new Set((planIds || []).map((item) => Number(item || 0)).filter((item) => item > 0))];
  return uniquePlanIds
    .map((planId) => {
      const plan = lookup.get(planId);
      if (plan) return enrichPlanRow(plan);
      return {
        ad_id: planId,
        ad_name: "",
        advertiser_name: "",
      };
    })
    .sort((left, right) => Number(left.ad_id || 0) - Number(right.ad_id || 0));
}

function resolveAccountRelationItemsByIds(advertiserIds) {
  const lookup = loadedAccountLookup();
  const uniqueAdvertiserIds = [...new Set((advertiserIds || []).map((item) => Number(item || 0)).filter((item) => item > 0))];
  return uniqueAdvertiserIds
    .map((advertiserId) => {
      const row = lookup.get(advertiserId);
      if (row) {
        return {
          advertiser_id: advertiserId,
          advertiser_name: String(row.advertiser_name || "").trim(),
          plan_count: row.plan_count,
          stat_cost: row.stat_cost,
          pay_amount: row.pay_amount,
          order_count: row.order_count,
          top_plan_name: String(row.top_plan_name || "").trim(),
        };
      }
      return {
        advertiser_id: advertiserId,
        advertiser_name: "",
      };
    })
    .sort((left, right) => Number(left.advertiser_id || 0) - Number(right.advertiser_id || 0));
}

function formatMaterialTotalPayAmount(row) {
  return materialSupportsTotalPayMetrics(row) ? formatMoney(row.total_pay_amount) : "-";
}

function formatMaterialSettledPayAmount(row) {
  return materialSupportsSettledMetrics(row) ? formatMoney(row.settled_pay_amount) : "-";
}

function formatMaterialSettledRoi(row) {
  return materialSupportsSettledMetrics(row) ? formatRate(row.settled_roi) : "-";
}

function formatMaterialSettledAmountRate(row) {
  return materialSupportsSettledMetrics(row) && Number(row.total_pay_amount || 0) > 0
    ? formatPercent(row.settled_amount_rate)
    : "-";
}

function renderDetailEmptyState(panel, eyebrow, title, hint) {
  if (!panel) return;
  panel.className = "detail-panel empty";
  panel.innerHTML = `
    <div class="detail-empty-state">
      <span class="detail-eyebrow">${escapeHtml(eyebrow)}</span>
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(hint)}</p>
    </div>
  `;
}

function detailMetaPill(content, className = "") {
  return `<span class="detail-meta-pill ${className}">${content}</span>`;
}

function detailHighlightCard(label, value, valueClass = "") {
  return `
    <div class="detail-highlight">
      <span class="label">${label}</span>
      <strong class="value ${valueClass}">${value}</strong>
    </div>
  `;
}

function detailMetricCard(label, value, valueClass = "", cardClass = "") {
  return `
    <div class="detail-stat ${cardClass}">
      <span class="label">${label}</span>
      <span class="value ${valueClass}">${value}</span>
    </div>
  `;
}

function detailNoteCard(label, content) {
  return `
    <div class="detail-note-card">
      <span class="label">${label}</span>
      <div class="value compact">${content}</div>
    </div>
  `;
}

function notificationChannelOptions(current) {
  const options = ["feishu", "dingtalk", "wechat"];
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
  if (channel === "wechat") {
    return { label: "微信目标", detail: "已配置微信接收对象。" };
  }
  return { label: "已配置目标", detail: "当前渠道已经设置接收对象。" };
}

function notificationTargetPlaceholder(channel) {
  if (channel === "feishu") return "填写群会话 ID、成员 open_id，或机器人目标";
  if (channel === "dingtalk") return "填写钉钉机器人 webhook 或群目标";
  if (channel === "wechat") return "填写企业微信机器人或接收对象标识";
  return "填写接收对象标识";
}

function renderNotificationGuide(settings) {
  if (!notificationGuide) return;
  const channel = String(settings?.channel || "feishu");
  const target = String(settings?.target || "").trim();
  const enabled = Boolean(settings?.enabled);
  const alertEnabled = Boolean(settings?.alert_enabled);
  const steps = [
    enabled ? "1. 外发已开启" : "1. 先决定是否开启外发",
    `2. 当前渠道：${channelLabel(channel)}`,
    target ? "3. 已配置接收目标" : "3. 还没配置接收目标",
    alertEnabled ? `4. 阈值告警每批 ${formatNumber(settings?.alert_batch_size || 6)} 条` : "4. 当前只保留页面提醒",
  ];
  notificationGuide.innerHTML = `
    <div class="signal-channel-guide-head">
      <strong>${enabled ? "通知已进入可外发状态" : "通知仍处于页面内提醒模式"}</strong>
      <span>${notificationTargetPlaceholder(channel)}</span>
    </div>
    <div class="signal-channel-guide-steps">
      ${steps.map((item) => `<span class="signal-guide-pill">${escapeHtml(item)}</span>`).join("")}
    </div>
  `;
}

function syncNotificationFormFields() {
  if (!notificationForm) return;
  const enabledInput = notificationForm.querySelector('input[name="enabled"]');
  const alertEnabledInput = notificationForm.querySelector('input[name="alert_enabled"]');
  const channelSelect = notificationForm.querySelector('select[name="channel"]');
  const targetInput = notificationForm.querySelector('input[name="target"]');
  const accountInput = notificationForm.querySelector('input[name="account"]');
  const batchInput = notificationForm.querySelector('input[name="alert_batch_size"]');
  const channel = String(channelSelect?.value || "feishu");
  const enabled = Boolean(enabledInput?.checked);
  const alertEnabled = Boolean(alertEnabledInput?.checked);
  if (targetInput) {
    targetInput.placeholder = notificationTargetPlaceholder(channel);
  }
  if (batchInput) {
    batchInput.disabled = !enabled || !alertEnabled;
  }
  if (accountInput) {
    accountInput.placeholder = enabled ? "default" : "通知关闭时可先留空";
  }
  renderNotificationGuide({
    enabled,
    alert_enabled: alertEnabled,
    channel,
    target: targetInput?.value || "",
    alert_batch_size: Number(batchInput?.value || 6),
  });
}

function renderRulePreview() {
  if (!rulePreviewCard || !ruleForm) return;
  const form = new FormData(ruleForm);
  const entityType = String(form.get("entity_type") || "plan");
  const metric = String(form.get("metric") || "");
  const operator = String(form.get("operator") || "lt");
  const threshold = String(form.get("threshold") || "").trim();
  const cooldownMinutes = String(form.get("cooldown_minutes") || "60").trim() || "60";
  const minSpend = String(form.get("min_spend") || "0").trim() || "0";
  const enabled = form.get("enabled") === "on";
  const targetId = String(form.get("target_id") || "").trim();
  const targetSearchValue = String(ruleTargetSearchInput?.value || "").trim();
  const config = ruleEntityConfig(entityType);
  const targetLabel = targetId
    ? targetDisplayLabel(entityType, targetId)
    : targetSearchValue
      ? `${targetSearchValue}（待确认）`
      : "全部对象";
  const thresholdLabel = threshold
    ? `${metricLabel(metric)} ${operatorLabel(operator)} ${threshold}`
    : `等待填写${metricLabel(metric)}阈值`;
  const spendLabel = config.supportsMinSpend ? `最低消耗 ${formatMoney(minSpend)}` : "无需最低消耗门槛";
  rulePreviewCard.innerHTML = `
    <div class="signal-rule-preview-head">
      <div>
        <span class="signal-rule-preview-label">${state.editingRuleId ? "编辑预览" : "新增预览"}</span>
        <strong>${escapeHtml(entityLabel(entityType))} · ${escapeHtml(metricLabel(metric))}</strong>
      </div>
      <span class="signal-rule-preview-badge ${enabled ? "on" : "off"}">${enabled ? "启用后立即生效" : "保存后保持关闭"}</span>
    </div>
    <div class="signal-rule-preview-body">
      <div class="signal-rule-preview-item">
        <span>作用对象</span>
        <strong>${escapeHtml(targetLabel)}</strong>
      </div>
      <div class="signal-rule-preview-item">
        <span>触发条件</span>
        <strong>${escapeHtml(thresholdLabel)}</strong>
      </div>
      <div class="signal-rule-preview-item">
        <span>冷却周期</span>
        <strong>${escapeHtml(cooldownMinutes)} 分钟</strong>
      </div>
      <div class="signal-rule-preview-item">
        <span>补充限制</span>
        <strong>${escapeHtml(spendLabel)}</strong>
      </div>
    </div>
  `;
}

function filteredAlertRules(rules) {
  const status = String(ruleStatusFilter?.value || "all");
  const query = String(ruleSearchInput?.value || "").trim().toLowerCase();
  return (rules || []).filter((rule) => {
    const enabled = Boolean(rule?.enabled);
    if (status === "enabled" && !enabled) return false;
    if (status === "disabled" && enabled) return false;
    if (!query) return true;
    const haystack = [
      entityLabel(rule?.entity_type),
      metricLabel(rule?.metric),
      targetDisplayLabel(rule?.entity_type, rule?.target_id),
      String(rule?.note || ""),
      String(rule?.threshold ?? ""),
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
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
  notificationStatus.dataset.tone = "neutral";
  syncNotificationFormFields();
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
      <span class="signal-summary-label">启用规则</span>
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
  const prefix = requestDisplayScope();
  if (normalized.mode === "custom") {
    return `${prefix}:custom:${normalized.start}:${normalized.end}`;
  }
  return `${prefix}:${normalized.mode}`;
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
  const normalizedView = String(view || "overview");
  const next = normalizedView === "ownership" ? "access" : normalizedView;
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

function setRangeEditorOpen(sectionKey, open) {
  state.rangeEditorOpen[sectionKey] = Boolean(open);
}

function syncSectionRangeControls(sectionKey) {
  const config = PERFORMANCE_SECTION_CONFIG[sectionKey];
  if (!config) return;
  const filter = sectionFilter(sectionKey);
  renderRangeSwitch(config.switchEl, filter.mode);
  const customInline = config.startEl?.closest(".custom-date-inline");
  if (customInline) {
    const expanded = filter.mode === "custom" || Boolean(state.rangeEditorOpen[sectionKey]);
    customInline.classList.toggle("active", filter.mode === "custom");
    customInline.classList.toggle("expanded", expanded);
    const toggle = customInline.querySelector('[data-role="custom-range-toggle"]');
    if (toggle) {
      toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }
  if (config.startEl && document.activeElement !== config.startEl) config.startEl.value = filter.start || "";
  if (config.endEl && document.activeElement !== config.endEl) config.endEl.value = filter.end || "";
}

function formatDateWindowMeta(payload) {
  if (!payload) {
    return "统计范围：加载中";
  }
  const queued =
    payload.history_backfill_pending
    && Number(payload.missing_history_days || 0) > 0
    && Boolean(payload.history_backfill_queued);
  const label = payload.range_label || RANGE_LABELS[payload.range_key] || "当前";
  const backfillHint =
    payload.history_backfill_pending && Number(payload.missing_history_days || 0) > 0
      ? ` · 历史补齐中（缺 ${Number(payload.missing_history_days || 0)} 天${queued ? "，已排队" : ""}）`
      : "";
  if (payload.query_start_date && payload.query_end_date) {
    if (payload.query_start_date === payload.query_end_date) {
      return `统计范围：${label} · ${payload.query_start_date}${backfillHint}`;
    }
    return `统计范围：${label} · ${payload.query_start_date} 至 ${payload.query_end_date}${backfillHint}`;
  }
  return `统计范围：${label} · ${payload.window_start} - ${payload.window_end}${backfillHint}`;
}

function rangePayload(filter) {
  return state.rangePayloads[performanceFilterKey(filter)] || null;
}

function materialRangePayload(filter) {
  return state.materialPayloads[performanceFilterKey(filter)] || null;
}

function teamMaterialRangePayload(filter) {
  return state.teamMaterialPayloads[performanceFilterKey(filter)] || null;
}

function commentRequestAdvertiserId() {
  return Number(commentAccountFilter?.value || 0) || 0;
}

function commentCacheKey(filter, advertiserId = commentRequestAdvertiserId()) {
  return `${performanceFilterKey(filter)}:${Number(advertiserId || 0)}`;
}

function commentRangePayload(filter, advertiserId = commentRequestAdvertiserId()) {
  return state.commentPayloads[commentCacheKey(filter, advertiserId)] || null;
}

function latestMaterialSnapshotToken() {
  return String(state.payload?.extendedSync?.snapshot_time || state.payload?.latest?.extendedSync?.snapshot_time || "").trim();
}

function materialRowsForCurrentFilter() {
  return (materialRangePayload(sectionFilter("material"))?.items || []).map((row) => enrichMaterialRow(row));
}

function teamMaterialRowsForCurrentFilter() {
  return (teamMaterialRangePayload(sectionFilter("teamMaterial"))?.items || []).map((row) => enrichMaterialRow(row));
}

function commentRowsForCurrentFilter() {
  return commentRangePayload(sectionFilter("comment"))?.items || [];
}

function rangeLabel(filter) {
  const normalized = normalizeRangeFilter(filter);
  if (normalized.mode === "custom") {
    return "指定日期范围";
  }
  const payload = rangePayload(normalized);
  return payload?.range_label || RANGE_LABELS[normalized.mode] || "当前";
}

function canUseUploadModule() {
  return Boolean(state.session?.can_upload_materials);
}

function selectedUploadPlans() {
  const planIds = new Set(state.uploadSelectedPlanIds || []);
  return (state.uploadTargets?.plans || []).filter((item) => planIds.has(Number(item.ad_id)));
}

function uploadScopeLabel(scope) {
  return scope === "account" ? "账户" : "计划";
}

function normalizeUploadJobNote(note) {
  const text = String(note || "").trim();
  if (!text) return "--";
  if (text.includes("permission") && text.includes("/file/video/ad/get/")) {
    return "当前应用缺少 /file/video/ad/get/ 权限。视频上传本身可能已成功，但系统无法查询视频封面并自动补齐图片素材。";
  }
  if (
    text.includes("permission") &&
    (text.includes("/local/file/video/upload/") || text.includes("/file/video/ad/"))
  ) {
    return "当前应用还没有该广告主的视频上传权限，请先补齐应用授权或接口权限。";
  }
  return text;
}

function uploadJobStatusLabel(status) {
  const value = String(status || "").trim().toLowerCase();
  if (value === "ok" || value === "success") return "完成";
  if (value === "running") return "进行中";
  if (value === "partial") return "部分完成";
  if (value === "failed") return "失败";
  if (value === "prepared" || value === "queued") return "待执行";
  return status || "--";
}

function uploadJobStatusClass(status) {
  const value = String(status || "").trim().toLowerCase();
  if (value === "ok" || value === "success") return "live";
  if (value === "running" || value === "prepared" || value === "queued") return "paused";
  if (value === "partial" || value === "failed") return "system";
  return "neutral";
}

function canRetryUploadJob(item) {
  const status = String(item?.status || "").trim().toLowerCase();
  if (status === "queued" || status === "running") return false;
  return Number(item?.failed_files || 0) > 0 || Number(item?.failed_targets || 0) > 0 || status === "failed" || status === "partial";
}

function uploadRetryButtonLabel(item) {
  return Number(state.uploadRetryingJobId || 0) === Number(item?.id || 0) ? "重试中..." : "重试失败项";
}

function canDeleteUploadJob(item) {
  const status = String(item?.status || "").trim().toLowerCase();
  return status !== "queued" && status !== "running";
}

function uploadDeleteButtonLabel(item) {
  return Number(state.uploadDeletingJobId || 0) === Number(item?.id || 0)
    ? "\u5220\u9664\u4e2d..."
    : "\u5220\u9664\u8bb0\u5f55";
}

function uploadFailureStageLabel(stage) {
  return String(stage || "").trim().toLowerCase() === "bind" ? "????" : "????";
}

function formatUploadFailureItem(row) {
  const stageLabel = uploadFailureStageLabel(row?.failure_stage);
  const advertiserLabel = String(row?.advertiser_name || "").trim() || (Number(row?.advertiser_id || 0) ? `?? ${row.advertiser_id}` : "");
  const planLabel = String(row?.ad_name || "").trim() || (Number(row?.ad_id || 0) ? `?? ${row.ad_id}` : "");
  const materialLabel = String(row?.original_name || "").trim() || "--";
  const parts = [stageLabel, advertiserLabel];
  if (String(row?.failure_stage || "").trim().toLowerCase() === "bind" && planLabel) parts.push(planLabel);
  parts.push(materialLabel);
  const reason = normalizeUploadJobNote(row?.message);
  return reason && reason !== "--" ? `${parts.filter(Boolean).join(" / ")}: ${reason}` : parts.filter(Boolean).join(" / ");
}

function renderUploadJobNote(item) {
  const base = normalizeUploadJobNote(item.note);
  const failedItems = Array.isArray(item.failed_items) ? item.failed_items : [];
  if (!failedItems.length) {
    return escapeHtml(base);
  }
  const previewItems = failedItems.slice(0, 5).map((row) => formatUploadFailureItem(row));
  const extraCount = Math.max(0, failedItems.length - previewItems.length);
  return `
    <div class="cell-primary">${escapeHtml(base)}</div>
    <div class="cell-subline"><span class="cell-subitem">???? ${formatNumber(failedItems.length)} ?</span></div>
    ${previewItems.map((line) => `<div class="cell-subline"><span class="cell-subitem">${escapeHtml(line)}</span></div>`).join("")}
    ${extraCount ? `<div class="cell-subline"><span class="cell-subitem">?? ${formatNumber(extraCount)} ????</span></div>` : ""}
  `;
}

function renderUploadTargetSummary() {
  if (!uploadTargetSummary) return;
  const selected = selectedUploadPlans();
  if (!selected.length) {
    uploadTargetSummary.textContent = "未选择计划";
    return;
  }
  const accountCount = new Set(selected.map((item) => Number(item.advertiser_id))).size;
  uploadTargetSummary.textContent = `已选 ${selected.length} 个计划，覆盖 ${accountCount} 个账户`;
}

function renderUploadFileSummary() {
  if (!uploadFileSummary) return;
  if (!state.uploadFiles.length) {
    uploadFileSummary.textContent = "未选择文件";
    return;
  }
  const totalSize = state.uploadFiles.reduce((sum, file) => sum + Number(file.size || 0), 0);
  uploadFileSummary.textContent = `已选 ${state.uploadFiles.length} 个视频，约 ${(totalSize / 1024 / 1024).toFixed(1)} MB`;
}

function renderUploadTargetTable() {
  if (!uploadTargetTable) return;
  const payload = state.uploadTargets;
  const items = payload?.plans || [];
  if (!items.length) {
    uploadTargetTable.innerHTML = '<tbody><tr><td colspan="7" class="empty-cell">先按账户或计划搜索，再勾选目标计划。</td></tr></tbody>';
    renderUploadTargetSummary();
    return;
  }
  uploadTargetTable.innerHTML = `
    <thead>
      <tr>
        <th class="check-col">选择</th>
        <th>账户</th>
        <th>计划</th>
        <th>商品 / 主播</th>
        <th class="mono">消耗</th>
        <th class="mono">支付</th>
        <th class="mono">订单</th>
      </tr>
    </thead>
    <tbody>
      ${items.map((item) => {
        const checked = state.uploadSelectedPlanIds.includes(Number(item.ad_id)) ? "checked" : "";
        return `
          <tr>
            <td class="check-col"><input type="checkbox" class="upload-target-checkbox" data-plan-id="${item.ad_id}" ${checked} /></td>
            <td>${escapeHtml(item.advertiser_name || "-")}</td>
            <td>
              <div class="entity-cell">
                <span class="entity-title">${escapeHtml(item.ad_name || "-")}</span>
                <span class="entity-sub mono">PID ${escapeHtml(item.ad_id)}</span>
              </div>
            </td>
            <td>${escapeHtml([item.product_name, item.anchor_name].filter(Boolean).join(" / ") || "--")}</td>
            <td class="mono">${formatMoney(item.stat_cost)}</td>
            <td class="mono">${formatMoney(item.pay_amount)}</td>
            <td class="mono">${formatNumber(item.order_count)}</td>
          </tr>
        `;
      }).join("")}
    </tbody>
  `;
  renderUploadTargetSummary();
}

function renderUploadJobTable() {
  if (!uploadJobTable) return;
  const items = state.uploadJobs || [];
  if (!items.length) {
    uploadJobTable.innerHTML = '<tbody><tr><td colspan="9" class="empty-cell">还没有上传任务。</td></tr></tbody>';
    return;
  }
  uploadJobTable.innerHTML = `
    <thead>
      <tr>
        <th>任务</th>
        <th>状态</th>
        <th>范围</th>
        <th class="mono">文件进度</th>
        <th class="mono">计划进度</th>
        <th>失败</th>
        <th>时间</th>
        <th>备注</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${items.map((item) => `
        <tr>
          <td>
            <div class="cell-primary mono">#${escapeHtml(item.id)}</div>
            <div class="cell-subline">
              <span class="cell-subitem">${escapeHtml(item.created_by_label || "--")}</span>
            </div>
          </td>
          <td><span class="status-pill ${uploadJobStatusClass(item.status)}">${escapeHtml(uploadJobStatusLabel(item.status))}</span></td>
          <td>
            <div class="cell-primary">${escapeHtml(uploadScopeLabel(item.scope || "plan"))}</div>
            <div class="cell-subline">
              <span class="cell-subitem">${formatNumber(item.total_targets || 0)} 个计划</span>
            </div>
          </td>
          <td class="mono">${formatNumber(item.success_files || item.uploaded_files || 0)} / ${formatNumber(item.total_files || 0)}</td>
          <td class="mono">${formatNumber(item.processed_targets || 0)} / ${formatNumber(item.total_targets || 0)}</td>
          <td>
            <div class="cell-primary mono">${formatNumber(item.failed_files || 0)}</div>
            <div class="cell-subline">
              <span class="cell-subitem">计划失败 ${formatNumber(item.failed_targets || 0)}</span>
            </div>
          </td>
          <td>${escapeHtml(item.created_at || "--")}</td>
          <td>${renderUploadJobNote(item)}</td>
          <td>
            ${(() => {
              const actions = [];
              if (canRetryUploadJob(item)) {
                actions.push(
                  `<button type="button" class="button ghost compact" data-action="retry-upload-job" data-job-id="${escapeHtml(item.id)}" ${Number(state.uploadRetryingJobId || 0) === Number(item.id || 0) || Number(state.uploadDeletingJobId || 0) === Number(item.id || 0) ? "disabled" : ""}>${escapeHtml(uploadRetryButtonLabel(item))}</button>`,
                );
              }
              if (canDeleteUploadJob(item)) {
                actions.push(
                  `<button type="button" class="button ghost danger compact" data-action="delete-upload-job" data-job-id="${escapeHtml(item.id)}" ${Number(state.uploadDeletingJobId || 0) === Number(item.id || 0) || Number(state.uploadRetryingJobId || 0) === Number(item.id || 0) ? "disabled" : ""}>${escapeHtml(uploadDeleteButtonLabel(item))}</button>`,
                );
              }
              return actions.length ? `<div class="upload-job-actions">${actions.join("")}</div>` : '<span class="cell-subitem">--</span>';
            })()}
          </td>
        </tr>
      `).join("")}
    </tbody>
  `;
}

async function fetchUploadTargets(force = false) {
  if (!canUseUploadModule()) return;
  const scope = String(uploadScopeSelect?.value || "plan");
  const query = String(uploadKeywordInput?.value || "").trim();
  if (!force && state.uploadTargets && state.uploadTargets.scope === scope && state.uploadTargets.query === query) {
    renderUploadTargetTable();
    return;
  }
  setInlineFeedback(uploadTargetMeta, `正在按${uploadScopeLabel(scope)}搜索…`, "neutral");
  const params = new URLSearchParams({ scope, q: query });
  const response = await fetch(`/api/upload/targets?${params.toString()}`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    window.alert(payload.detail || "加载上传目标失败");
    return;
  }
  state.uploadTargets = await response.json();
  state.uploadSelectedPlanIds = [];
  if (uploadSelectAll) uploadSelectAll.checked = false;
  renderUploadTargetTable();
  setInlineFeedback(
    uploadTargetMeta,
    `命中 ${formatNumber(state.uploadTargets.plan_count || 0)} 个计划，覆盖 ${formatNumber(state.uploadTargets.account_count || 0)} 个账户。`,
    "success",
  );
}

async function fetchUploadJobs() {
  if (!canUseUploadModule()) return;
  const response = await fetch("/api/upload/jobs");
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    window.alert(payload.detail || "加载上传任务失败");
    return;
  }
  const payload = await response.json();
  state.uploadJobs = payload.items || [];
  renderUploadJobTable();
}

async function retryUploadJob(jobId) {
  const normalizedJobId = Number(jobId || 0);
  if (!normalizedJobId || state.uploadRetryingJobId === normalizedJobId) return;
  state.uploadRetryingJobId = normalizedJobId;
  renderUploadJobTable();
  setInlineFeedback(uploadJobStatus, `正在重试任务 #${normalizedJobId}…`, "neutral");
  try {
    const response = await fetch(`/api/upload/jobs/${encodeURIComponent(String(normalizedJobId))}/retry`, { method: "POST" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      window.alert(payload.detail || "重试上传任务失败");
      setInlineFeedback(uploadJobStatus, "重试上传任务失败。", "warn");
      return;
    }
    setInlineFeedback(
      uploadJobStatus,
      `已创建重试任务 #${payload.id}，来源任务 #${payload.source_job_id || normalizedJobId}。`,
      "success",
    );
    await fetchUploadJobs();
  } finally {
    state.uploadRetryingJobId = null;
    renderUploadJobTable();
  }
}

async function deleteUploadJob(jobId) {
  const normalizedJobId = Number(jobId || 0);
  if (!normalizedJobId || state.uploadDeletingJobId === normalizedJobId) return;
  const job = (state.uploadJobs || []).find((item) => Number(item?.id || 0) === normalizedJobId);
  if (!job) return;
  if (!canDeleteUploadJob(job)) {
    window.alert("\u5f53\u524d\u4efb\u52a1\u4ecd\u5728\u6267\u884c\u4e2d\uff0c\u5b8c\u6210\u540e\u624d\u80fd\u5220\u9664\u8bb0\u5f55\u3002");
    return;
  }
  if (
    !window.confirm(
      `\u786e\u8ba4\u5220\u9664\u4efb\u52a1 #${normalizedJobId} \u7684\u8bb0\u5f55\u5417\uff1f\u8fd9\u4f1a\u540c\u65f6\u79fb\u9664\u8be5\u4efb\u52a1\u7684\u6700\u8fd1\u4efb\u52a1\u660e\u7ec6\u3002`,
    )
  ) {
    return;
  }
  state.uploadDeletingJobId = normalizedJobId;
  renderUploadJobTable();
  setInlineFeedback(
    uploadJobStatus,
    `\u6b63\u5728\u5220\u9664\u4efb\u52a1 #${normalizedJobId} \u7684\u8bb0\u5f55...`,
    "neutral",
  );
  try {
    const response = await fetch(`/api/upload/jobs/${encodeURIComponent(String(normalizedJobId))}`, { method: "DELETE" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      window.alert(payload.detail || "\u5220\u9664\u4e0a\u4f20\u4efb\u52a1\u8bb0\u5f55\u5931\u8d25");
      setInlineFeedback(uploadJobStatus, "\u5220\u9664\u4e0a\u4f20\u4efb\u52a1\u8bb0\u5f55\u5931\u8d25\u3002", "warn");
      return;
    }
    state.uploadJobs = (state.uploadJobs || []).filter((item) => Number(item?.id || 0) !== normalizedJobId);
    renderUploadJobTable();
    setInlineFeedback(
      uploadJobStatus,
      `\u5df2\u5220\u9664\u4efb\u52a1 #${normalizedJobId} \u7684\u8bb0\u5f55\u3002`,
      "success",
    );
  } finally {
    state.uploadDeletingJobId = null;
    renderUploadJobTable();
  }
}

function renderAlertSummary(events) {
  if (!events.length) {
    alertSummary.innerHTML = `
      <div class="alert-summary-card spotlight calm">
        <div class="summary-topline">
          <span class="summary-chip">状态</span>
          <span class="summary-chip subtle">平稳</span>
        </div>
        <div class="summary-value">暂无异常</div>
        <div class="summary-sub">最近没有命中规则。</div>
        <div class="summary-metric-row">
          <div><span>待处理</span><strong class="mono">0</strong></div>
          <div><span>最新状态</span><strong>正常</strong></div>
          <div><span>提醒对象</span><strong>-</strong></div>
        </div>
      </div>
      <div class="alert-summary-card stat">
      <div class="summary-label">待处理</div>
      <div class="summary-value mono">0</div>
      <div class="summary-sub">当前没有待处理</div>
      </div>
      <div class="alert-summary-card stat">
      <div class="summary-label">状态</div>
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
      <div class="summary-label">重点</div>
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
      <div class="summary-sub">${pendingCount ? "待复核" : "暂无待处理"}</div>
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
  const teamLabel = "运营账号";
  const activeTeamCount = formatNumber(summary.active_operator_count);
  const totalTeamCount = formatNumber(summary.operator_count);
  const cards = [
    ["活跃账户", formatNumber(summary.active_account_count), `总账户 ${formatNumber(summary.account_count)}`],
    ["活跃计划", formatNumber(summary.active_plan_count), `总计划 ${formatNumber(summary.plan_count)}`],
    ["活跃商品", formatNumber(summary.active_product_count), `总商品 ${formatNumber(summary.product_count)}`],
    [`活跃${teamLabel}`, activeTeamCount, `总${teamLabel} ${totalTeamCount}`],
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
  const admin = isAdmin();
  const supervisor = isSupervisor();
  const operatorMode = isOperator();
  const teamLabel = "运营账号";
  const activeTeamCount = formatNumber(summary.active_operator_count);
  const accountFailures = Number(summary.account_failures || 0);
  const planFailures = Number(summary.plan_failures || 0);
  const accountTone = accountFailures ? "danger" : "ok";
  const planTone = planFailures ? "danger" : "ok";
  const title = operatorMode ? "今日总览" : supervisor ? "范围总览" : "今日概况";
  const copy = operatorMode
    ? "只看关键词命中的素材和团队表现。"
    : supervisor
      ? "只看授权范围内的账户、计划和素材。"
      : "先看消耗、支付、订单和 ROI。";
  const pillMarkup = admin
    ? `
        <span class="system-pill ${accountTone === "danger" ? "danger" : ""}">${accountFailures ? `账户异常 ${formatNumber(accountFailures)}` : "账户查询正常"}</span>
        <span class="system-pill ${planTone === "danger" ? "danger" : ""}">${planFailures ? `计划异常 ${formatNumber(planFailures)}` : "计划查询正常"}</span>
      `
    : supervisor
      ? `<span class="system-pill">账户范围 ${formatNumber(state.session?.scope_count || 0)}</span>`
      : `<span class="system-pill">关键词归属视图</span>`;
  overviewHeroCard.innerHTML = `
    <div class="overview-hero-head">
      <div>
        <h2>${title}</h2>
        <p class="overview-hero-copy">${copy}</p>
      </div>
      <div class="overview-hero-pills">
        ${pillMarkup}
      </div>
    </div>
    <div class="overview-hero-stage">
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
        <div class="overview-foot-stat"><span>活跃${escapeHtml(teamLabel)}</span><strong class="mono">${activeTeamCount}</strong></div>
      </div>
    </div>
  `;
}

function breakdownUsesOperators(payload) {
  return true;
}

function breakdownRows(payload) {
  return payload?.operators || [];
}

function breakdownEntityName(row) {
  return String(row?.operator_name || row?.employee_name || "");
}

function breakdownEntityLabel(payload) {
  return "运营账号";
}

function breakdownSearchPlaceholder(payload) {
  return "搜索运营 / 计划";
}

function breakdownDetailEmptyCopy(payload) {
  return `点击${breakdownEntityLabel(payload)}行，查看该${breakdownEntityLabel(payload)}当前负责的计划规模和核心表现。`;
}

function breakdownSearchPlaceholder(payload) {
  return "搜索运营 / 素材";
}

function breakdownDetailEmptyCopy(payload) {
  return `点击${breakdownEntityLabel(payload)}行，查看该${breakdownEntityLabel(payload)}当前命中素材的汇总和核心表现。`;
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
    heroStatusHint.textContent = `1 分钟 · token ${tokenAgeText}`;
  }

  systemStatusCard.innerHTML = `
    <div class="system-card-head">
      <span class="system-card-label">主快照状态</span>
      <span class="system-pill ${failureTone === "danger" ? "danger" : ""}">${hardAccountFailures || planFailures ? "有异常" : "运行正常"}</span>
    </div>
    <div class="system-card-value">${escapeHtml(latest?.snapshot_time || "等待首次同步")}</div>
    <div class="system-card-copy">按分钟级主快照更新，异常时自动回退。</div>
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
    <div class="system-card-copy">明细按 10 分钟级同步。</div>
    <div class="system-stat-grid">
      <div class="system-stat"><span>计划数</span><strong class="mono">${formatNumber(extendedSync?.plan_count || 0)}</strong></div>
      <div class="system-stat"><span>商品行</span><strong class="mono">${formatNumber(extendedSync?.product_row_count || 0)}</strong></div>
      <div class="system-stat"><span>素材行</span><strong class="mono">${formatNumber(extendedSync?.material_row_count || 0)}</strong></div>
      <div class="system-stat"><span>错误数</span><strong class="mono">${formatNumber(extendedSync?.error_count || 0)}</strong></div>
    </div>
  `;
}

function clearDashboardDataCaches() {
  state.rangePayloads = {};
  state.planAssetCache = {};
  state.materialPayloads = {};
  state.materialPayloadFetchedAt = {};
  state.teamMaterialPayloads = {};
  state.teamMaterialPayloadFetchedAt = {};
  state.commentPayloads = {};
  state.commentPayloadFetchedAt = {};
  state.materialPreviewCurveCache = {};
  state.catalogAccounts = [];
}

function syncOceanEnginePopoverState() {
  const admin = isAdmin();
  const open = admin && Boolean(state.oceanEnginePopoverOpen);
  if (customerCenterChip) {
    customerCenterChip.classList.toggle("is-interactive", admin);
    customerCenterChip.classList.toggle("is-active", open);
    customerCenterChip.setAttribute("aria-expanded", open ? "true" : "false");
    customerCenterChip.setAttribute("aria-disabled", admin ? "false" : "true");
    customerCenterChip.tabIndex = admin ? 0 : -1;
    customerCenterChip.title = admin ? "点击查看已授权账号" : "";
  }
  if (oceanEngineConfigCard) {
    oceanEngineConfigCard.classList.toggle("hidden", !open);
  }
}

function setOceanEnginePopoverOpen(nextOpen) {
  state.oceanEnginePopoverOpen = Boolean(nextOpen) && isAdmin();
  syncOceanEnginePopoverState();
}

function renderOceanEngineConfigPreview(preview) {
  if (!oceanEngineConfigPreview) return;
  const accountCount = Number(preview?.account_count || 0);
  const sampleAccounts = Array.isArray(preview?.sample_accounts) ? preview.sample_accounts : [];
  if (!preview) {
    oceanEngineConfigPreview.classList.add("hidden");
    oceanEngineConfigPreview.innerHTML = "";
    return;
  }
  oceanEngineConfigPreview.classList.remove("hidden");
  oceanEngineConfigPreview.innerHTML = `
    <div class="runtime-config-preview-meta">校验通过。当前 CC 可访问 ${formatNumber(accountCount)} 个账号，以下展示前 ${formatNumber(sampleAccounts.length)} 个样例。</div>
    <div class="runtime-config-preview-list">
      ${sampleAccounts.length
        ? sampleAccounts.map((item) => `
          <span class="runtime-config-preview-item">
            <strong>${escapeHtml(item.advertiser_name || "--")}</strong>
            <span class="mono">${escapeHtml(String(item.advertiser_id || "--"))}</span>
          </span>
        `).join("")
        : '<span class="runtime-config-preview-item">当前 CC 没有返回可见账号。</span>'}
    </div>
  `;
}

function oceanEngineBoundCustomerCenters(config) {
  return Array.isArray(config?.bound_customer_centers) ? config.bound_customer_centers : [];
}

function oceanEngineAllScopeSummary(items) {
  return (items || []).reduce(
    (summary, item) => {
      summary.accountCount += Number(item?.account_count || 0);
      summary.activeAccountCount += Number(item?.active_account_count || 0);
      summary.planCount += Number(item?.plan_count || 0);
      summary.materialCount += Number(item?.detail_material_row_count || 0);
      const snapshotTime = String(item?.latest_snapshot_time || "").trim();
      const detailSnapshotTime = String(item?.latest_detail_snapshot_time || "").trim();
      if (snapshotTime > summary.latestSnapshotTime) {
        summary.latestSnapshotTime = snapshotTime;
      }
      if (detailSnapshotTime > summary.latestDetailSnapshotTime) {
        summary.latestDetailSnapshotTime = detailSnapshotTime;
      }
      return summary;
    },
    {
      accountCount: 0,
      activeAccountCount: 0,
      planCount: 0,
      materialCount: 0,
      latestSnapshotTime: "",
      latestDetailSnapshotTime: "",
    },
  );
}

async function switchOceanEngineDisplayScope(nextScope) {
  const normalizedScope = normalizeDisplayScope(nextScope);
  if (normalizedScope === requestDisplayScope()) {
    return;
  }
  setDisplayScope(normalizedScope);
  renderOceanEngineConfig(state.oceanEngineConfig);
  const currentCc = String(state.oceanEngineConfig?.customer_center_id || "").trim();
  const message = normalizedScope === DISPLAY_SCOPE_ALL
    ? "已切换到全部账号视图，正在加载汇总数据。"
    : `已切回当前账号 CC ${currentCc || "--"} 视图。`;
  setInlineFeedback(oceanEngineConfigStatus, message, "success");
  try {
    await fetchDashboard();
  } catch (error) {
    setInlineFeedback(oceanEngineConfigStatus, error.message || "切换展示范围失败。", "error");
    throw error;
  }
}

function renderOceanEngineBoundAccounts(config) {
  if (!oceanEngineBoundAccounts) return;
  const items = oceanEngineBoundCustomerCenters(config);
  const allScopeSummary = oceanEngineAllScopeSummary(items);
  const hasPendingSwitch = Boolean(state.oceanEnginePendingCustomerCenterId);
  const allScopeAvailable = items.length > 1;
  const allScopeActive = allScopeAvailable && usingAllCustomerCenters();
  if (oceanEngineBoundAccountsMeta) {
    oceanEngineBoundAccountsMeta.textContent = items.length
      ? `共 ${formatNumber(items.length)} 个`
      : "暂无";
  }
  if (!items.length) {
    oceanEngineBoundAccounts.innerHTML = `
      <div class="customer-center-bound-empty">
        暂无已授权并写入 token 的账号。
      </div>
    `;
    return;
  }
  const cards = [];
  if (allScopeAvailable) {
    const snapshotMeta = allScopeSummary.latestSnapshotTime
      ? `汇总快照 ${escapeHtml(allScopeSummary.latestSnapshotTime)} · 账户 ${formatNumber(allScopeSummary.accountCount)} / 活跃 ${formatNumber(allScopeSummary.activeAccountCount)} · 计划 ${formatNumber(allScopeSummary.planCount)}`
      : "暂无汇总快照";
    const detailMeta = allScopeSummary.latestDetailSnapshotTime
      ? `汇总明细 ${escapeHtml(allScopeSummary.latestDetailSnapshotTime)} · 素材 ${formatNumber(allScopeSummary.materialCount)}`
      : "暂无汇总明细";
    cards.push(`
      <button
        type="button"
        class="customer-center-bound-button ${allScopeActive ? "is-active" : ""}"
        data-action="switch-display-scope-all"
        ${hasPendingSwitch ? "disabled" : ""}
      >
        <div class="customer-center-bound-top">
          <strong>显示全部</strong>
          <span class="customer-center-bound-badge subtle">聚合 ${formatNumber(items.length)} 个账号</span>
        </div>
        <div class="customer-center-bound-meta">展示所有已授权账号的账户、计划、素材与运营汇总。</div>
        <div class="customer-center-bound-stats">${snapshotMeta}</div>
        <div class="customer-center-bound-stats">${detailMeta}</div>
      </button>
    `);
  }
  cards.push(...items.map((item) => {
    const customerCenterId = String(item.customer_center_id || "").trim();
    const isCurrent = Boolean(item.is_current);
    const isPending = customerCenterId && customerCenterId === state.oceanEnginePendingCustomerCenterId;
    const badges = allScopeActive
      ? ""
      : [
        isCurrent ? '<span class="customer-center-bound-badge">当前</span>' : "",
        item.is_override_customer_center ? '<span class="customer-center-bound-badge subtle">运行中</span>' : "",
        item.is_base_customer_center ? '<span class="customer-center-bound-badge subtle">默认</span>' : "",
      ].filter(Boolean).join("");
    const tokenMeta = `Token ${item.token_updated_at ? formatAgoFromEpoch(item.token_updated_at) : "未记录"}${item.token_source ? ` / ${escapeHtml(item.token_source)}` : ""}`;
    const snapshotMeta = item.latest_snapshot_time
      ? `主快照 ${escapeHtml(item.latest_snapshot_time)} · 账号 ${formatNumber(item.account_count || 0)} / 活跃 ${formatNumber(item.active_account_count || 0)} · 计划 ${formatNumber(item.plan_count || 0)}`
      : "暂无主快照";
    const detailMeta = item.latest_detail_snapshot_time
      ? `明细 ${escapeHtml(item.latest_detail_snapshot_time)}${item.detail_status ? ` / ${escapeHtml(item.detail_status)}` : ""} · 素材 ${formatNumber(item.detail_material_row_count || 0)}`
      : "暂无明细快照";
    return `
      <button
        type="button"
        class="customer-center-bound-button ${isCurrent && !allScopeActive ? "is-active" : ""}"
        data-action="switch-bound-customer-center"
        data-customer-center-id="${escapeHtml(customerCenterId)}"
        ${(isCurrent && !allScopeActive) || hasPendingSwitch || isPending ? "disabled" : ""}
      >
        <div class="customer-center-bound-top">
          <strong class="mono">CC ${escapeHtml(customerCenterId || "--")}</strong>
          ${badges}
        </div>
        <div class="customer-center-bound-meta">${tokenMeta}</div>
        <div class="customer-center-bound-stats">${snapshotMeta}</div>
        <div class="customer-center-bound-stats">${detailMeta}</div>
      </button>
    `;
  }));
  oceanEngineBoundAccounts.innerHTML = cards.join("");
}

async function switchOceanEngineCustomerCenter(targetCc, sourceLabel = "已授权 token") {
  const normalizedTargetCc = String(targetCc || "").trim();
  const currentCc = String(state.oceanEngineConfig?.customer_center_id || "").trim();
  const submitButton = oceanEngineConfigForm?.querySelector('button[type="submit"]');
  if (!/^\d+$/.test(normalizedTargetCc)) {
    setInlineFeedback(oceanEngineConfigStatus, "账号 ID 格式不正确。", "error");
    oceanEngineConfigForm?.querySelector('input[name="customer_center_id"]')?.focus();
    return;
  }
  if (normalizedTargetCc === currentCc) {
    if (usingAllCustomerCenters()) {
      await switchOceanEngineDisplayScope(DISPLAY_SCOPE_CURRENT);
      return;
    }
    setInlineFeedback(oceanEngineConfigStatus, `CC ${normalizedTargetCc} 已经是当前账号。`, "neutral");
    return;
  }

  state.oceanEnginePendingCustomerCenterId = normalizedTargetCc;
  if (submitButton) submitButton.disabled = true;
  renderOceanEngineConfig(state.oceanEngineConfig);
  setInlineFeedback(
    oceanEngineConfigStatus,
    `正在校验 ${sourceLabel} 并切换到 CC ${normalizedTargetCc}...`,
    "neutral",
  );
  try {
    const response = await fetch("/api/system/integrations/ocean-engine/runtime-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_center_id: normalizedTargetCc,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "切换授权账号失败。");
    }
    state.oceanEngineConfig = payload.config || state.oceanEngineConfig;
    state.oceanEnginePreview = payload.preview || null;
    setDisplayScope(DISPLAY_SCOPE_CURRENT, { clearCaches: false });
    clearDashboardDataCaches();
    renderOceanEngineConfig(state.oceanEngineConfig);
    setInlineFeedback(oceanEngineConfigStatus, `已切换到 CC ${normalizedTargetCc}，正在提交主快照同步。`, "success");

    const syncResponse = await fetch("/api/sync", { method: "POST" });
    const syncPayload = await syncResponse.json().catch(() => ({}));
    if (!syncResponse.ok) {
      throw new Error(syncPayload.detail || "账号已切换，但主快照同步提交失败。");
    }
    setInlineFeedback(
      oceanEngineConfigStatus,
      `已切换到 CC ${normalizedTargetCc}，主快照同步已入队。新快照完成前，页面可能短暂显示旧数据。`,
      "success",
    );
    await fetchDashboard();
    window.setTimeout(() => {
      fetchDashboard().catch(() => {});
    }, 1800);
  } catch (error) {
    setInlineFeedback(oceanEngineConfigStatus, error.message || "切换授权账号失败。", "error");
    window.alert(error.message || "切换授权账号失败。");
  } finally {
    state.oceanEnginePendingCustomerCenterId = "";
    if (submitButton) submitButton.disabled = false;
    renderOceanEngineConfig(state.oceanEngineConfig);
  }
}

function renderOceanEngineConfig(config) {
  const boundItems = oceanEngineBoundCustomerCenters(config);
  if (boundItems.length <= 1 && usingAllCustomerCenters()) {
    setDisplayScope(DISPLAY_SCOPE_CURRENT, { clearCaches: false });
  }
  if (customerCenterChip) {
    customerCenterChip.textContent = usingAllCustomerCenters() && boundItems.length > 1
      ? "全部账号"
      : `CC ${config?.customer_center_id || "--"}`;
  }
  if (!oceanEngineConfigCard) return;
  const admin = isAdmin();
  if (!admin) {
    state.oceanEnginePopoverOpen = false;
  }
  syncOceanEnginePopoverState();
  if (!admin || !config) {
    renderOceanEngineBoundAccounts(null);
    renderOceanEngineConfigPreview(null);
    return;
  }

  const baseCc = String(config.base_customer_center_id || "").trim();
  const overrideCc = String(config.override_customer_center_id || "").trim();
  const tokenAgeText = config?.token_updated_at ? formatAgoFromEpoch(config.token_updated_at) : "未记录";
  const modeText = config?.has_customer_center_override
    ? `当前生效账号：CC ${overrideCc}。服务器默认账号：CC ${baseCc}。`
    : `当前使用服务器默认账号：CC ${baseCc}。`;
  const effectiveModeText = usingAllCustomerCenters() && boundItems.length > 1
    ? `当前显示全部已授权账号（${formatNumber(boundItems.length)} 个账号），当前运行账号为 CC ${config?.customer_center_id || "--"}。`
    : modeText;
  if (oceanEngineConfigMeta) {
    oceanEngineConfigMeta.textContent = `${effectiveModeText} token ${tokenAgeText}${config?.token_source ? ` / ${config.token_source}` : ""}`;
  }
  if (!oceanEngineConfigStatus?.textContent) {
    setInlineFeedback(
      oceanEngineConfigStatus,
      "点击下方已授权账号即可切换，系统会自动提交一次主快照同步。",
      "neutral",
    );
  }
  renderOceanEngineBoundAccounts(config);
}

function renderAlerts(events) {
  const pendingCount = events.filter((item) => item.status === "pending").length;
  if (overviewAlertMeta) {
    const latestCreatedAt = events[0]?.created_at || "暂无";
    overviewAlertMeta.innerHTML = `
      <div class="overview-alert-meta-item">
        <strong class="mono">${formatNumber(events.length)}</strong>
        <span>最近记录</span>
      </div>
      <div class="overview-alert-meta-item">
        <strong class="mono">${formatNumber(pendingCount)}</strong>
        <span>待处理</span>
      </div>
      <div class="overview-alert-meta-item is-wide">
        <strong class="mono">${escapeHtml(latestCreatedAt)}</strong>
        <span>最新触发</span>
      </div>
    `;
  }
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
  const accountPayload = rangePayload(sectionFilter("account"));
  const accountMetrics = buildAccountMetricsFromPlans(accountPayload?.plans || []);
  const query = accountSearch.value.trim().toLowerCase();
  const columns = [
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "total_pay_amount", label: "整体成交", sortable: true },
    { key: "settled_pay_amount", label: "净成交", sortable: true },
    { key: "roi", label: "支付ROI", sortable: true },
    { key: "settled_roi", label: "净ROI", sortable: true },
    { key: "order_count", label: "整体订单", sortable: true },
    { key: "settled_order_count", label: "净订单", sortable: true },
    { key: "pay_order_cost", label: "订单成本", sortable: true },
    { key: "settled_amount_rate", label: "结算率", sortable: true },
    { key: "refund_rate_1h", label: "1h退款率", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
    { key: "status_text", label: "状态", sortable: false },
  ];
  const enrichedRows = accounts.map((row) => ({
    ...enrichAccountRow(row, accountMetrics),
    status_text: !row.ok ? "查询失败" : String(row.error || "").startsWith("fallback:") ? "计划聚合" : "正常",
  }));
  const rows = enrichedRows.filter((row) => {
    const haystack = [
      row.advertiser_name,
      row.advertiser_id,
      row.top_plan_name,
      row.status_text,
      row.error,
    ].join(" " ).toLowerCase();
    return haystack.includes(query);
  });
  const activeSort = columns.some((column) => column.key === state.accountSort.key)
    ? state.accountSort
    : { key: "stat_cost", dir: "desc" };
  if (activeSort.key !== state.accountSort.key || activeSort.dir !== state.accountSort.dir) {
    state.accountSort = activeSort;
    saveSort("account-sort", state.accountSort);
  }
  const sorted = sortRows(rows, activeSort);

  accountTable.innerHTML = `
    ${makeHeader(columns, activeSort, "account-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr>
          <td>
            <div class="cell-primary">${escapeHtml(row.advertiser_name)}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">AID ${escapeHtml(String(row.advertiser_id || "-"))}</span>
              ${row.top_plan_name ? `<span class="cell-subitem">代表计划 ${escapeHtml(row.top_plan_name)}</span>` : ""}
            </div>
          </td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatMoney(row.total_pay_amount)}</td>
          <td class="mono">${formatMoney(row.settled_pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatRate(row.settled_roi)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatNumber(row.settled_order_count)}</td>
          <td class="mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}</td>
          <td class="mono">
            ${Number(row.plan_count || 0) > 0
              ? `<button type="button" class="relation-trigger mono" data-action="open-account-plan-detail" data-advertiser-id="${row.advertiser_id}">${formatNumber(row.plan_count)}</button>`
              : formatNumber(row.plan_count)}
          </td>
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
      state.accountSort = toggleSort(activeSort, key);
      saveSort("account-sort", state.accountSort);
      renderAccountTable(accounts);
    });
  });

  accountTable.querySelectorAll('[data-action="open-account-plan-detail"]').forEach((button) => {
    const advertiserId = Number(button.dataset.advertiserId || 0);
    const row = sorted.find((item) => Number(item.advertiser_id || 0) === advertiserId);
    if (!row) return;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openAccountPlanRelationDetail(row);
    });
  });
}

function clearEmployeeDetail() {
  if (!employeeDetail) return;
  employeeDetail.className = "detail-panel empty";
  employeeDetail.textContent = breakdownDetailEmptyCopy(rangePayload(sectionFilter("breakdown")));
}

function clearProductDetail() {
  if (!productDetail) return;
  productDetail.className = "detail-panel empty";
  productDetail.textContent = "点击商品行，查看该商品对应的计划规模、账户覆盖和代表计划。";
}

function renderEmployeeDetail(employeeName) {
  if (!employeeDetail) return;
  const breakdownFilter = sectionFilter("breakdown");
  const payload = rangePayload(breakdownFilter);
  const rows = breakdownRows(payload);
  const sourceRow = rows.find((item) => breakdownEntityName(item) === employeeName);
  if (!sourceRow) return;
  const operatorMode = breakdownUsesOperators(payload);
  const entityLabel = breakdownEntityLabel(payload);
  const row = operatorMode ? enrichOperatorRow(sourceRow) : sourceRow;
  employeeDetail.className = "detail-panel";
  if (operatorMode) {
    const refundRateText = row.refund_rate_1h_available ? formatPercent(row.refund_rate_1h) : "-";
    employeeDetail.innerHTML = `
      <div class="detail-stats">
        <div class="detail-stat detail-stat-wide"><span class="label">${escapeHtml(entityLabel)}</span><span class="value compact">${escapeHtml(row.operator_name || "-")}</span></div>
        <div class="detail-stat"><span class="label">登录账号</span><span class="value compact mono">${escapeHtml(row.operator_username || "-")}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
        <div class="detail-stat"><span class="label">整体成交</span><span class="value mono">${formatMoney(row.total_pay_amount)}</span></div>
        <div class="detail-stat"><span class="label">净成交</span><span class="value mono">${formatMoney(row.settled_pay_amount)}</span></div>
        <div class="detail-stat"><span class="label">支付ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
        <div class="detail-stat"><span class="label">净ROI</span><span class="value mono">${formatRate(row.settled_roi)}</span></div>
        <div class="detail-stat"><span class="label">整体订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
        <div class="detail-stat"><span class="label">净订单</span><span class="value mono">${formatNumber(row.settled_order_count)}</span></div>
        <div class="detail-stat"><span class="label">订单成本</span><span class="value mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</span></div>
        <div class="detail-stat"><span class="label">结算率</span><span class="value mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</span></div>
        <div class="detail-stat"><span class="label">1h退款率</span><span class="value mono">${refundRateText}</span></div>
        <div class="detail-stat"><span class="label">账户数</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
        <div class="detail-stat"><span class="label">关键词数</span><span class="value mono">${formatNumber(row.keyword_count)}</span></div>
        <div class="detail-stat"><span class="label">素材数</span><span class="value mono">${formatNumber(row.material_count)}</span></div>
        <div class="detail-stat"><span class="label">计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
        <div class="detail-stat detail-stat-wide"><span class="label">代表素材</span><span class="value compact">${escapeHtml(row.top_material_name || "暂无代表素材")}</span></div>
      </div>
    `;
    return;
  }
  if (operatorMode) {
    const materialCount = Number(row.material_count ?? row.plan_count ?? 0);
    employeeDetail.innerHTML = `
      <div class="detail-stats">
        <div class="detail-stat detail-stat-wide"><span class="label">${escapeHtml(entityLabel)}</span><span class="value compact">${escapeHtml(row.operator_name || "-")}</span></div>
        <div class="detail-stat"><span class="label">登录账号</span><span class="value compact mono">${escapeHtml(row.operator_username || "-")}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
        <div class="detail-stat"><span class="label">覆盖账户</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
        <div class="detail-stat"><span class="label">关键词数</span><span class="value mono">${formatNumber(row.keyword_count)}</span></div>
        <div class="detail-stat"><span class="label">素材数</span><span class="value mono">${formatNumber(materialCount)}</span></div>
        <div class="detail-stat"><span class="label">覆盖计划</span><span class="value mono">${formatNumber(row.plan_count || 0)}</span></div>
        <div class="detail-stat detail-stat-wide"><span class="label">代表素材</span><span class="value compact">${escapeHtml(row.top_material_name || row.top_plan_name || "暂无代表素材")}</span></div>
      </div>
    `;
    return;
  }
  if (operatorMode) {
    employeeDetail.innerHTML = `
      <div class="detail-stats">
        <div class="detail-stat detail-stat-wide"><span class="label">${escapeHtml(entityLabel)}</span><span class="value compact">${escapeHtml(row.operator_name || "-")}</span></div>
        <div class="detail-stat"><span class="label">登录账号</span><span class="value compact mono">${escapeHtml(row.operator_username || "-")}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}消耗</span><span class="value mono">${formatMoney(row.stat_cost)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}支付</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}订单</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
        <div class="detail-stat"><span class="label">${escapeHtml(rangeLabel(breakdownFilter))}ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
        <div class="detail-stat"><span class="label">覆盖账户</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
        <div class="detail-stat"><span class="label">关键词数</span><span class="value mono">${formatNumber(row.keyword_count)}</span></div>
        <div class="detail-stat"><span class="label">总计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
        <div class="detail-stat detail-stat-wide"><span class="label">代表计划</span><span class="value compact">${escapeHtml(row.top_plan_name || "暂无代表计划")}</span></div>
      </div>
    `;
    return;
  }
  employeeDetail.innerHTML = `
    <div class="detail-stats">
      <div class="detail-stat detail-stat-wide"><span class="label">${escapeHtml(entityLabel)}</span><span class="value compact">${escapeHtml(row.employee_name)}</span></div>
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
  if (!productDetail) return;
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
  if (!employeeDetail) return;
  if (!employeeName) {
    clearEmployeeDetail();
    return;
  }
  renderEmployeeDetail(employeeName);
}

function setSelectedProduct(productKey) {
  state.selectedProductKey = productKey;
  if (!productDetail) return;
  if (!productKey) {
    clearProductDetail();
    return;
  }
  renderProductDetail(productKey);
}

function syncSelectedEmployee(rows) {
  if (!employeeDetail) return;
  if (!state.selectedEmployeeName) {
    clearEmployeeDetail();
    return;
  }
  const exists = rows.some((item) => breakdownEntityName(item) === state.selectedEmployeeName);
  if (!exists) {
    setSelectedEmployee(null);
    return;
  }
  renderEmployeeDetail(state.selectedEmployeeName);
}

function syncSelectedProduct(rows) {
  if (!productDetail) return;
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
  if (!employeeDetail) return;
  employeeTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedEmployee(String(rowEl.dataset.employeeName || ""));
      renderEmployeeTable(rows);
    });
  });
}

function renderProductInteractions(rows) {
  if (!productDetail || !productTable) return;
  productTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedProduct(String(rowEl.dataset.productKey || ""));
      renderProductTable(rows);
    });
  });
}

function renderEmployeeTable(rows) {
  const payload = rangePayload(sectionFilter("breakdown"));
  const operatorMode = breakdownUsesOperators(payload);
  const entityLabel = breakdownEntityLabel(payload);
  const compactOperatorRanking = isOperator();
  if (operatorMode) {
    const enrichedRows = rows.map((row) => enrichOperatorRow(row));
    const query = employeeSearch.value.trim().toLowerCase();
    const visibleRows = enrichedRows.filter((row) => {
      const haystack = [
        row.operator_name,
        row.operator_username,
        row.top_material_name,
        row.top_account_name,
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    const columns = compactOperatorRanking
      ? [
          { key: "rank", label: "序号", sortable: false },
          { key: "operator_name", label: entityLabel, sortable: true },
          { key: "stat_cost", label: "消耗", sortable: true },
        ]
      : [
          { key: "rank", label: "序号", sortable: false },
          { key: "operator_name", label: entityLabel, sortable: true },
          { key: "stat_cost", label: "消耗", sortable: true },
          { key: "total_pay_amount", label: "整体成交", sortable: true },
          { key: "settled_pay_amount", label: "净成交", sortable: true },
          { key: "roi", label: "ROI", sortable: true },
          { key: "settled_roi", label: "净ROI", sortable: true },
          { key: "order_count", label: "整体订单", sortable: true },
          { key: "settled_order_count", label: "净订单", sortable: true },
          { key: "pay_order_cost", label: "订单成本", sortable: true },
          { key: "settled_amount_rate", label: "结算率", sortable: true },
          { key: "refund_rate_1h", label: "1h退款率", sortable: true },
          { key: "material_count", label: "素材数", sortable: true },
          { key: "advertiser_count", label: "账户数", sortable: true },
          { key: "keyword_count", label: "关键词数", sortable: true },
        ];
    const activeSort = columns.some((column) => column.key === state.employeeSort.key)
      ? state.employeeSort
      : { key: "stat_cost", dir: "desc" };
    if (activeSort.key !== state.employeeSort.key || activeSort.dir !== state.employeeSort.dir) {
      state.employeeSort = activeSort;
      saveSort("employee-sort", state.employeeSort);
    }
    const sorted = sortRows(visibleRows, activeSort);

    employeeTable.innerHTML = `
      ${makeHeader(columns, activeSort, "employee-sort")}
      <tbody>
        ${sorted.map((row, index) => {
          const entityName = breakdownEntityName(row);
          const subline = compactOperatorRanking
            ? []
            : [
                row.top_material_name ? `代表素材 ${row.top_material_name}` : "",
              ].filter(Boolean);
          const refundRateText = row.refund_rate_1h_available ? formatPercent(row.refund_rate_1h) : "-";
          return `
            <tr data-employee-name="${escapeHtml(entityName)}" class="${state.selectedEmployeeName === entityName ? "active-row" : ""}">
              <td class="mono rank-index-cell">${formatNumber(index + 1)}</td>
              <td>
                <div class="cell-primary">${escapeHtml(entityName)}</div>
                ${subline.length ? `<div class="cell-subline">${subline.map((item) => `<span class="cell-subitem">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
              </td>
              <td class="mono">${formatMoney(row.stat_cost)}</td>
              ${compactOperatorRanking ? "" : `
              <td class="mono">${formatMoney(row.total_pay_amount)}</td>
              <td class="mono">${formatMoney(row.settled_pay_amount)}</td>
              <td class="mono">${formatRate(row.roi)}</td>
              <td class="mono">${formatRate(row.settled_roi)}</td>
              <td class="mono">${formatNumber(row.order_count)}</td>
              <td class="mono">${formatNumber(row.settled_order_count)}</td>
              <td class="mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</td>
              <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</td>
              <td class="mono">${refundRateText}</td>
              <td class="mono">${formatNumber(row.material_count)}</td>
              <td class="mono">${formatNumber(row.advertiser_count)}</td>
              <td class="mono">${formatNumber(row.keyword_count)}</td>
              `}
            </tr>
          `;
        }).join("")}
      </tbody>
    `;

    employeeTable.querySelectorAll("th[data-key]").forEach((header) => {
      header.addEventListener("click", () => {
        const key = header.dataset.key;
        const column = columns.find((item) => item.key === key);
        if (!column || !column.sortable) return;
        state.employeeSort = toggleSort(activeSort, key);
        saveSort("employee-sort", state.employeeSort);
        renderEmployeeTable(enrichedRows);
      });
    });

    renderEmployeeInteractions(enrichedRows);
    return;
  }
  if (operatorMode) {
    const query = employeeSearch.value.trim().toLowerCase();
    const visibleRows = rows.filter((row) => {
      const haystack = [
        row.operator_name,
        row.operator_username,
        row.top_material_name,
        row.top_account_name,
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    });
    const columns = [
      { key: "rank", label: "序号", sortable: false },
      { key: "operator_name", label: entityLabel, sortable: true },
      { key: "stat_cost", label: "消耗", sortable: true },
      { key: "pay_amount", label: "支付", sortable: true },
      { key: "order_count", label: "订单", sortable: true },
      { key: "roi", label: "ROI", sortable: true },
      { key: "advertiser_count", label: "账户数", sortable: true },
      { key: "keyword_count", label: "关键词数", sortable: true },
      { key: "material_count", label: "素材数", sortable: true },
    ];
    const activeSort = columns.some((column) => column.key === state.employeeSort.key)
      ? state.employeeSort
      : { key: "stat_cost", dir: "desc" };
    if (activeSort.key !== state.employeeSort.key || activeSort.dir !== state.employeeSort.dir) {
      state.employeeSort = activeSort;
      saveSort("employee-sort", state.employeeSort);
    }
    const sorted = sortRows(visibleRows, activeSort);

    employeeTable.innerHTML = `
      ${makeHeader(columns, activeSort, "employee-sort")}
      <tbody>
        ${sorted.map((row, index) => {
          const entityName = breakdownEntityName(row);
          const materialCount = Number(row.material_count ?? row.plan_count ?? 0);
          const subline = [
            row.top_material_name ? `代表素材 ${row.top_material_name}` : "",
          ].filter(Boolean);
          return `
            <tr data-employee-name="${escapeHtml(entityName)}" class="${state.selectedEmployeeName === entityName ? "active-row" : ""}">
              <td class="mono rank-index-cell">${formatNumber(index + 1)}</td>
              <td>
                <div class="cell-primary">${escapeHtml(entityName)}</div>
                ${subline.length ? `<div class="cell-subline">${subline.map((item) => `<span class="cell-subitem">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
              </td>
              <td class="mono">${formatMoney(row.stat_cost)}</td>
              <td class="mono">${formatMoney(row.pay_amount)}</td>
              <td class="mono">${formatNumber(row.order_count)}</td>
              <td class="mono">${formatRate(row.roi)}</td>
              <td class="mono">${formatNumber(row.advertiser_count)}</td>
              <td class="mono">${formatNumber(row.keyword_count)}</td>
              <td class="mono">${formatNumber(materialCount)}</td>
            </tr>
          `;
        }).join("")}
      </tbody>
    `;

    employeeTable.querySelectorAll("th[data-key]").forEach((header) => {
      header.addEventListener("click", () => {
        const key = header.dataset.key;
        const column = columns.find((item) => item.key === key);
        if (!column || !column.sortable) return;
        state.employeeSort = toggleSort(activeSort, key);
        saveSort("employee-sort", state.employeeSort);
        renderEmployeeTable(rows);
      });
    });

    renderEmployeeInteractions(rows);
    return;
  }
  const query = employeeSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = operatorMode
      ? [row.operator_name, row.operator_username, row.top_plan_name, row.top_account_name].join(" ").toLowerCase()
      : [row.employee_name, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = operatorMode
    ? [
        { key: "rank", label: "序号", sortable: false },
        { key: "operator_name", label: entityLabel, sortable: true },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "pay_amount", label: "支付", sortable: true },
        { key: "order_count", label: "订单", sortable: true },
        { key: "roi", label: "ROI", sortable: true },
        { key: "advertiser_count", label: "账户数", sortable: true },
        { key: "keyword_count", label: "关键词数", sortable: true },
        { key: "plan_count", label: "计划数", sortable: true },
      ]
    : [
        { key: "rank", label: "序号", sortable: false },
        { key: "employee_name", label: entityLabel, sortable: true },
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
      ${sorted.map((row, index) => {
        const entityName = breakdownEntityName(row);
        const subline = operatorMode
          ? [row.operator_username ? `账号 ${row.operator_username}` : "", row.top_account_name ? `代表账户 ${row.top_account_name}` : ""].filter(Boolean)
          : [row.top_account_name ? `代表账户 ${row.top_account_name}` : "", row.top_plan_name ? `代表计划 ${row.top_plan_name}` : ""].filter(Boolean);
        return `
          <tr data-employee-name="${escapeHtml(entityName)}" class="${state.selectedEmployeeName === entityName ? "active-row" : ""}">
            <td class="mono rank-index-cell">${formatNumber(index + 1)}</td>
            <td>
              <div class="cell-primary">${escapeHtml(entityName)}</div>
              ${subline.length ? `<div class="cell-subline">${subline.map((item) => `<span class="cell-subitem">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
            </td>
            <td class="mono">${formatMoney(row.stat_cost)}</td>
            <td class="mono">${formatMoney(row.pay_amount)}</td>
            <td class="mono">${formatNumber(row.order_count)}</td>
            <td class="mono">${formatRate(row.roi)}</td>
            <td class="mono">${formatNumber(row.advertiser_count)}</td>
            <td class="mono">${formatNumber(operatorMode ? row.keyword_count : row.product_count)}</td>
            <td class="mono">${formatNumber(row.plan_count)}</td>
          </tr>
        `;
      }).join("")}
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
  if (!productTable || productRankPanel?.classList.contains("hidden")) return;
  const query = productSearch?.value.trim().toLowerCase() || "";
  const visibleRows = rows.filter((row) => {
    const haystack = [row.product_name, row.product_id, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "product_name", label: "商品", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "advertiser_count", label: "账户数", sortable: true },
    { key: "employee_count", label: "命中人数", sortable: true },
    { key: "plan_count", label: "计划数", sortable: true },
  ];
  const sorted = sortRows(visibleRows, state.productSort);

  productTable.innerHTML = `
    ${makeHeader(columns, state.productSort, "product-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-product-key="${escapeHtml(row.product_key)}" class="${state.selectedProductKey === row.product_key ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.product_name)}</div>
            <div class="cell-subline">
              ${row.top_plan_name ? `<span class="cell-subitem">代表计划 ${escapeHtml(row.top_plan_name)}</span>` : ""}
              ${row.top_account_name ? `<span class="cell-subitem">代表账户 ${escapeHtml(row.top_account_name)}</span>` : ""}
            </div>
          </td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">
            ${Number(row.advertiser_count || 0) > 0
              ? `<button type="button" class="relation-trigger mono" data-action="open-product-account-detail" data-product-key="${escapeHtml(row.product_key)}">${formatNumber(row.advertiser_count)}</button>`
              : formatNumber(row.advertiser_count)}
          </td>
          <td class="mono">${formatNumber(row.employee_count)}</td>
          <td class="mono">
            ${Number(row.plan_count || 0) > 0
              ? `<button type="button" class="relation-trigger mono" data-action="open-product-plan-detail" data-product-key="${escapeHtml(row.product_key)}">${formatNumber(row.plan_count)}</button>`
              : formatNumber(row.plan_count)}
          </td>
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

  productTable.querySelectorAll('[data-action="open-product-account-detail"], [data-action="open-product-plan-detail"]').forEach((button) => {
    const productKey = String(button.dataset.productKey || "");
    const row = sorted.find((item) => String(item.product_key || "") === productKey);
    if (!row) return;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openProductRelationDetail(row, button.dataset.action === "open-product-account-detail" ? "account" : "plan");
    });
  });

  renderProductInteractions(rows);
}

function clearMaterialDetail() {
  if (!materialDetail) return;
  materialDetailStage?.classList.remove("hidden");
  renderDetailEmptyState(
    materialDetail,
    "素材详情",
    "选中素材后查看补充信息",
    "这里会展示素材预览入口、核心效果指标和归属关系。",
  );
}

function renderMaterialDetail(materialKey) {
  if (!materialDetail) return;
  const rows = materialRangePayload(sectionFilter("material"))?.items || [];
  const sourceRow = rows.find((item) => item.material_key === materialKey);
  const row = sourceRow ? enrichMaterialRow(sourceRow) : null;
  if (!row) return;
  materialDetailStage?.classList.remove("hidden");
  materialDetail.className = "detail-panel";
  const summaryText = materialSupportsSettledMetrics(row)
    ? `当前素材消耗 ${formatMoney(row.stat_cost)}，整体成交 ${formatMaterialTotalPayAmount(row)}，净成交 ${formatMaterialSettledPayAmount(row)}，净成交 ROI ${formatMaterialSettledRoi(row)}。`
    : `当前素材消耗 ${formatMoney(row.stat_cost)}，整体成交 ${formatMaterialTotalPayAmount(row)}，支付 ROI ${formatRate(row.roi)}。该素材类型暂不支持净成交口径。`;
  materialDetail.innerHTML = `
    <div class="detail-shell-head">
      <div class="detail-shell-copy">
        <span class="detail-eyebrow">素材详情</span>
        <h4 class="detail-shell-title">${escapeHtml(row.material_name || "未命名素材")}</h4>
        <div class="detail-meta-row">
          ${detailMetaPill(escapeHtml(row.material_type || "OTHER"))}
          ${detailMetaPill(row.is_original ? "首发素材" : "非首发素材")}
          ${detailMetaPill(`覆盖账户 ${formatNumber(row.advertiser_count)}`)}
          ${detailMetaPill(`覆盖计划 ${formatNumber(row.plan_count)}`)}
        </div>
      </div>
      <div class="detail-actions">
        ${canPreviewMaterial(row)
          ? `<button type="button" class="button ghost compact" data-action="open-material-preview" data-material-key="${escapeHtml(row.material_key)}">查看预览</button>`
          : ""}
      </div>
    </div>
    <div class="detail-highlight-grid">
      ${detailHighlightCard("消耗", formatMoney(row.stat_cost), "mono")}
      ${detailHighlightCard("整体成交", formatMaterialTotalPayAmount(row), "mono")}
      ${detailHighlightCard("净成交", formatMaterialSettledPayAmount(row), "mono")}
      ${detailHighlightCard("支付 ROI", formatRate(row.roi), "mono")}
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">效果拆分</div>
      <div class="detail-metric-grid">
        ${detailMetricCard("净成交 ROI", formatMaterialSettledRoi(row), "mono")}
        ${detailMetricCard("支付金额", formatMoney(row.pay_amount), "mono")}
        ${detailMetricCard("成交订单数", formatNumber(row.order_count), "mono")}
        ${detailMetricCard("净成交订单数", materialSupportsSettledMetrics(row) ? formatNumber(row.settled_order_count) : "-", "mono")}
        ${detailMetricCard("净成交结算率", formatMaterialSettledAmountRate(row), "mono")}
        ${detailMetricCard("素材标记", row.is_original ? "首发素材" : "常规素材", "compact")}
      </div>
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">归属与识别</div>
      <div class="detail-metric-grid">
        ${detailMetricCard("素材 ID", escapeHtml(row.material_id || "-"), "compact mono")}
        ${detailMetricCard("视频 ID", escapeHtml(row.video_id || "-"), "compact mono")}
        ${detailMetricCard("代表账户", escapeHtml(row.top_account_name || "-"), "compact")}
        ${detailMetricCard("代表计划", escapeHtml(row.top_plan_name || "-"), "compact")}
        ${detailMetricCard("账户覆盖数", formatNumber(row.advertiser_count), "mono")}
        ${detailMetricCard("计划覆盖数", formatNumber(row.plan_count), "mono")}
      </div>
    </div>
    ${detailNoteCard("当前判断", escapeHtml(summaryText))}
  `;
  materialDetail.querySelector('[data-action="open-material-preview"]')?.addEventListener("click", () => {
    openMaterialPreview(row.material_key);
  });
}

function setSelectedMaterial(materialKey) {
  if (!materialDetail) return;
  state.selectedMaterialKey = materialKey;
  if (!materialKey) {
    clearMaterialDetail();
    return;
  }
  renderMaterialDetail(materialKey);
}

function syncSelectedMaterial(rows) {
  if (!materialDetail) return;
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

function materialPagerPages(totalPages, currentPage) {
  const pages = new Set([1, totalPages, currentPage - 1, currentPage, currentPage + 1]);
  return [...pages].filter((page) => page >= 1 && page <= totalPages).sort((left, right) => left - right);
}

function renderMaterialPager(totalRows, currentPage, totalPages, startIndex, endIndex) {
  if (!materialTablePager) return;
  if (totalRows <= MATERIAL_PAGE_SIZE) {
    materialTablePager.innerHTML = "";
    materialTablePager.classList.add("hidden");
    return;
  }
  const pages = materialPagerPages(totalPages, currentPage);
  materialTablePager.classList.remove("hidden");
  materialTablePager.innerHTML = `
    <div class="table-pager-summary">显示 ${formatNumber(startIndex)}-${formatNumber(endIndex)} / ${formatNumber(totalRows)}，按页渲染以减少卡顿。</div>
    <div class="table-pager-actions">
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage - 1}"
        ${currentPage <= 1 ? "disabled" : ""}
      >上一页</button>
      ${pages.map((page, index) => `
        ${index > 0 && page - pages[index - 1] > 1 ? '<span class="table-pager-ellipsis">...</span>' : ""}
        <button
          type="button"
          class="button ghost compact table-page-button ${page === currentPage ? "is-active" : ""}"
          data-page="${page}"
          ${page === currentPage ? 'aria-current="page"' : ""}
        >${formatNumber(page)}</button>
      `).join("")}
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage + 1}"
        ${currentPage >= totalPages ? "disabled" : ""}
      >下一页</button>
    </div>
  `;
  materialTablePager.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page || 0);
      if (!nextPage || nextPage === state.materialPage) return;
      state.materialPage = nextPage;
      renderMaterialTable(materialRowsForCurrentFilter());
    });
  });
}

function renderMaterialInteractions(rows) {
  if (materialDetail) {
    materialTable.querySelectorAll("tbody tr").forEach((rowEl) => {
      rowEl.addEventListener("click", () => {
        setSelectedMaterial(String(rowEl.dataset.materialKey || ""));
        renderMaterialTable(rows);
      });
    });
  }
  materialTable.querySelectorAll('[data-action="open-material-preview"]').forEach((button) => {
    const materialKey = String(button.dataset.materialKey || "");
    const row = rows.find((item) => item.material_key === materialKey);
    if (!row) return;
    const replacement = materialPreviewTriggerMarkup(row);
    if (replacement.startsWith("<span")) {
      button.outerHTML = replacement;
      return;
    }
    if (String(row.cover_url || "").trim()) {
      button.outerHTML = replacement;
    }
  });
  materialTable.querySelectorAll('[data-action="open-material-preview"]').forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const materialKey = String(button.dataset.materialKey || "");
      if (!materialKey) return;
      openMaterialPreview(materialKey);
    });
  });
  materialTable.querySelectorAll(".material-preview-thumb").forEach((thumb) => {
    thumb.addEventListener("error", () => {
      const trigger = thumb.closest(".material-preview-trigger");
      if (!trigger) return;
      downgradeMaterialPreviewTrigger(trigger);
    }, { once: true });
  });
}

function renderMaterialTable(rows) {
  const operatorMode = isOperator();
  const enrichedRows = rows.map((row) => enrichMaterialRow(row));
  if (
    operatorMode
    && !["material_name", "create_time", "overall_ctr", "stat_cost", "top_anchor_name"].includes(String(state.materialSort.key || ""))
  ) {
    state.materialSort = { key: "create_time", dir: "desc" };
    saveSort("material-sort", state.materialSort);
  }
  const query = materialSearch.value.trim().toLowerCase();
  const visibleRows = enrichedRows.filter((row) => {
    const haystack = [
      row.material_name,
      row.material_id,
      row.video_id,
      row.product_info_text,
      row.top_anchor_name,
      ...(operatorMode ? [] : [row.top_plan_name, row.top_account_name]),
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = operatorMode
    ? [
        { key: "material_name", label: "素材", sortable: true },
        { key: "product_info_text", label: "商品信息", sortable: false },
        { key: "preview", label: "预览", sortable: false },
        { key: "create_time", label: "创建时间", sortable: true },
        { key: "overall_ctr", label: "整体点击率", sortable: true },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "top_anchor_name", label: "达人", sortable: true },
      ]
    : [
        { key: "material_name", label: "素材", sortable: true },
        { key: "product_info_text", label: "商品信息", sortable: false },
        { key: "preview", label: "预览", sortable: false },
        { key: "create_time", label: "创建时间", sortable: true },
        { key: "overall_ctr", label: "整体点击率", sortable: true },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "total_pay_amount", label: "整体成交", sortable: true },
        { key: "settled_pay_amount", label: "净成交", sortable: true },
        { key: "roi", label: "支付ROI", sortable: true },
        { key: "pay_amount", label: "支付金额", sortable: true },
        { key: "order_count", label: "订单", sortable: true },
        { key: "top_account_name", label: "归属账户", sortable: true },
        { key: "top_plan_name", label: "归属计划", sortable: true },
        { key: "top_anchor_name", label: "达人", sortable: true },
        { key: "plan_count", label: "计划数", sortable: true },
        { key: "advertiser_count", label: "账户数", sortable: true },
      ];
  const sorted = sortRows(visibleRows, state.materialSort);
  const totalRows = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / MATERIAL_PAGE_SIZE));
  const currentPage = Math.min(Math.max(Number(state.materialPage) || 1, 1), totalPages);
  const pageStart = totalRows ? (currentPage - 1) * MATERIAL_PAGE_SIZE : 0;
  const pageRows = sorted.slice(pageStart, pageStart + MATERIAL_PAGE_SIZE);
  state.materialPage = currentPage;
  const supportsMaterialDetail = Boolean(materialDetail);
  materialTable.innerHTML = `
    ${makeHeader(columns, state.materialSort, "material-sort")}
    <tbody>
      ${pageRows.map((row) => `
        <tr data-material-key="${escapeHtml(row.material_key)}" class="${supportsMaterialDetail && state.selectedMaterialKey === row.material_key ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.material_name || "未命名素材")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem" title="素材 ID：${escapeHtml(row.material_id || "-")}">MID ${escapeHtml(truncateMiddle(row.material_id || "-", 8, 6))}</span>
              <span class="cell-subitem" title="视频 ID：${escapeHtml(row.video_id || "-")}">VID ${escapeHtml(truncateMiddle(row.video_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td>
            <div class="cell-secondary compact">${escapeHtml(row.product_info_text || "--")}</div>
          </td>
          <td>
            <button
              type="button"
              class="button ghost compact"
              data-action="open-material-preview"
              data-material-key="${escapeHtml(row.material_key)}"
              ${canPreviewMaterial(row) ? "" : "disabled"}
            >${canPreviewMaterial(row) ? "预览" : "暂无"}</button>
          </td>
          <td class="mono">${escapeHtml(formatDateTime(row.create_time || ""))}</td>
          <td class="mono">${formatPercent(row.overall_ctr)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          ${operatorMode
            ? `
          <td>${escapeHtml(row.top_anchor_name || "--")}</td>
          `
            : `
          <td class="mono">${formatMaterialTotalPayAmount(row)}</td>
          <td class="mono">${formatMaterialSettledPayAmount(row)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td>${escapeHtml(row.top_account_name || "--")}</td>
          <td>${escapeHtml(row.top_plan_name || "--")}</td>
          <td>${escapeHtml(row.top_anchor_name || "--")}</td>
          <td class="mono">
            ${Number(row.plan_count || 0) > 0
              ? `<button type="button" class="relation-trigger mono" data-action="open-material-plan-detail" data-material-key="${escapeHtml(row.material_key)}">${formatNumber(row.plan_count)}</button>`
              : formatNumber(row.plan_count)}
          </td>
          <td class="mono">
            ${Number(row.advertiser_count || 0) > 0
              ? `<button type="button" class="relation-trigger mono" data-action="open-material-account-detail" data-material-key="${escapeHtml(row.material_key)}">${formatNumber(row.advertiser_count)}</button>`
              : formatNumber(row.advertiser_count)}
          </td>
          `}
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
      renderMaterialTable(enrichedRows);
    });
  });
  materialTable.querySelectorAll('[data-action="open-material-plan-detail"], [data-action="open-material-account-detail"]').forEach((button) => {
    const materialKey = String(button.dataset.materialKey || "");
    const row = pageRows.find((item) => String(item.material_key || "") === materialKey);
    if (!row) return;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openMaterialRelationDetail(row, button.dataset.action === "open-material-account-detail" ? "account" : "plan");
    });
  });
  renderMaterialPager(
    totalRows,
    currentPage,
    totalPages,
    totalRows ? pageStart + 1 : 0,
    pageStart + pageRows.length,
  );
  renderMaterialInteractions(enrichedRows);
}

function renderTeamMaterialPager(totalRows, currentPage, totalPages, startIndex, endIndex) {
  if (!teamMaterialTablePager) return;
  if (totalRows <= MATERIAL_PAGE_SIZE) {
    teamMaterialTablePager.innerHTML = "";
    teamMaterialTablePager.classList.add("hidden");
    return;
  }
  const pages = materialPagerPages(totalPages, currentPage);
  teamMaterialTablePager.classList.remove("hidden");
  teamMaterialTablePager.innerHTML = `
    <div class="table-pager-summary">显示 ${formatNumber(startIndex)}-${formatNumber(endIndex)} / ${formatNumber(totalRows)}，按页渲染以减少卡顿。</div>
    <div class="table-pager-actions">
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage - 1}"
        ${currentPage <= 1 ? "disabled" : ""}
      >上一页</button>
      ${pages.map((page, index) => `
        ${index > 0 && page - pages[index - 1] > 1 ? '<span class="table-pager-ellipsis">...</span>' : ""}
        <button
          type="button"
          class="button ghost compact table-page-button ${page === currentPage ? "is-active" : ""}"
          data-page="${page}"
          ${page === currentPage ? 'aria-current="page"' : ""}
        >${formatNumber(page)}</button>
      `).join("")}
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage + 1}"
        ${currentPage >= totalPages ? "disabled" : ""}
      >下一页</button>
    </div>
  `;
  teamMaterialTablePager.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page || 0);
      if (!nextPage || nextPage === state.teamMaterialPage) return;
      state.teamMaterialPage = nextPage;
      renderTeamMaterialTable(teamMaterialRowsForCurrentFilter());
    });
  });
}

function renderTeamMaterialTable(rows) {
  if (!teamMaterialTable) return;
  const operatorMode = isOperator();
  const enrichedRows = rows.map((row) => enrichMaterialRow(row));
  if (
    ![
      "material_name",
      "create_time",
      "overall_ctr",
      "stat_cost",
      ...(operatorMode ? ["top_anchor_name"] : ["top_account_name", "top_plan_name", "top_anchor_name"]),
    ].includes(String(state.teamMaterialSort.key || ""))
  ) {
    state.teamMaterialSort = { key: "create_time", dir: "desc" };
    saveSort("team-material-sort", state.teamMaterialSort);
  }
  const query = teamMaterialSearch?.value.trim().toLowerCase() || "";
  const visibleRows = enrichedRows.filter((row) => {
    const haystack = [
      row.material_name,
      row.material_id,
      row.video_id,
      row.product_info_text,
      row.top_anchor_name,
      ...(operatorMode ? [] : [row.top_account_name, row.top_plan_name]),
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = operatorMode
    ? [
        { key: "material_name", label: "素材", sortable: true },
        { key: "product_info_text", label: "商品信息", sortable: false },
        { key: "preview", label: "预览", sortable: false },
        { key: "create_time", label: "创建时间", sortable: true },
        { key: "overall_ctr", label: "整体点击率", sortable: true },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "top_anchor_name", label: "达人", sortable: true },
      ]
    : [
        { key: "material_name", label: "素材", sortable: true },
        { key: "product_info_text", label: "商品信息", sortable: false },
        { key: "preview", label: "预览", sortable: false },
        { key: "create_time", label: "创建时间", sortable: true },
        { key: "overall_ctr", label: "整体点击率", sortable: true },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "top_account_name", label: "归属账户", sortable: true },
        { key: "top_plan_name", label: "归属计划", sortable: true },
        { key: "top_anchor_name", label: "达人", sortable: true },
      ];
  const sorted = sortRows(visibleRows, state.teamMaterialSort);
  const totalRows = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / MATERIAL_PAGE_SIZE));
  const currentPage = Math.min(Math.max(Number(state.teamMaterialPage) || 1, 1), totalPages);
  const pageStart = totalRows ? (currentPage - 1) * MATERIAL_PAGE_SIZE : 0;
  const pageRows = sorted.slice(pageStart, pageStart + MATERIAL_PAGE_SIZE);
  state.teamMaterialPage = currentPage;
  teamMaterialTable.innerHTML = `
    ${makeHeader(columns, state.teamMaterialSort, "team-material-sort")}
    <tbody>
      ${pageRows.map((row) => `
        <tr>
          <td>
            <div class="cell-primary">${escapeHtml(row.material_name || "未命名素材")}</div>
            <div class="cell-subline cell-subline-stack mono">
              <span class="cell-subitem" title="素材 ID：${escapeHtml(row.material_id || "-")}">MID ${escapeHtml(truncateMiddle(row.material_id || "-", 8, 6))}</span>
              <span class="cell-subitem" title="视频 ID：${escapeHtml(row.video_id || "-")}">VID ${escapeHtml(truncateMiddle(row.video_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td>
            <div class="cell-secondary compact">${escapeHtml(row.product_info_text || "--")}</div>
          </td>
          <td>
            ${canPreviewMaterial(row)
              ? `<button
                  type="button"
                  class="button ghost compact"
                  data-action="open-material-preview"
                  data-material-key="${escapeHtml(row.material_key)}"
                >查看预览</button>`
              : '<span class="material-preview-placeholder">暂无</span>'}
          </td>
          <td class="mono">${escapeHtml(formatDateTime(row.create_time || ""))}</td>
          <td class="mono">${formatPercent(row.overall_ctr)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          ${operatorMode
            ? ""
            : `
          <td>${escapeHtml(row.top_account_name || "--")}</td>
          <td>${escapeHtml(row.top_plan_name || "--")}</td>
          `}
          <td>${escapeHtml(row.top_anchor_name || "--")}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  teamMaterialTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.teamMaterialSort = toggleSort(state.teamMaterialSort, key);
      saveSort("team-material-sort", state.teamMaterialSort);
      renderTeamMaterialTable(enrichedRows);
    });
  });
  renderTeamMaterialInteractions(pageRows);
  renderTeamMaterialPager(
    totalRows,
    currentPage,
    totalPages,
    totalRows ? pageStart + 1 : 0,
    pageStart + pageRows.length,
  );
}

function renderTeamMaterialInteractions(rows) {
  if (!teamMaterialTable) return;
  teamMaterialTable.querySelectorAll('[data-action="open-material-preview"]').forEach((button) => {
    const materialKey = String(button.dataset.materialKey || "");
    const row = rows.find((item) => item.material_key === materialKey);
    if (!row) return;
    const replacement = materialPreviewTriggerMarkup(row);
    if (replacement.startsWith("<span")) {
      button.outerHTML = replacement;
      return;
    }
    if (String(row.cover_url || "").trim()) {
      button.outerHTML = replacement;
    }
  });
  teamMaterialTable.querySelectorAll('[data-action="open-material-preview"]').forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const materialKey = String(button.dataset.materialKey || "");
      if (!materialKey) return;
      openMaterialPreview(materialKey);
    });
  });
  teamMaterialTable.querySelectorAll(".material-preview-thumb").forEach((thumb) => {
    thumb.addEventListener("error", () => {
      const trigger = thumb.closest(".material-preview-trigger");
      if (!trigger) return;
      downgradeMaterialPreviewTrigger(trigger);
    }, { once: true });
  });
}

function fillCommentAccountFilter(accounts) {
  if (!commentAccountFilter) return;
  const current = String(commentAccountFilter.value || "");
  const options = ['<option value="">全部账户</option>']
    .concat((accounts || []).map((item) => (
      `<option value="${escapeHtml(item.advertiser_id)}">${escapeHtml(item.advertiser_name || item.advertiser_id)}</option>`
    )));
  commentAccountFilter.innerHTML = options.join("");
  if ([...commentAccountFilter.options].some((option) => option.value === current)) {
    commentAccountFilter.value = current;
  } else {
    commentAccountFilter.value = "";
  }
}

function renderCommentPager(totalRows, currentPage, totalPages, startIndex, endIndex) {
  if (!commentTablePager) return;
  if (totalRows <= COMMENT_PAGE_SIZE) {
    commentTablePager.innerHTML = "";
    commentTablePager.classList.add("hidden");
    return;
  }
  const pages = materialPagerPages(totalPages, currentPage);
  commentTablePager.classList.remove("hidden");
  commentTablePager.innerHTML = `
    <div class="table-pager-summary">鏄剧ず ${formatNumber(startIndex)}-${formatNumber(endIndex)} / ${formatNumber(totalRows)} 鏉¤瘎璁恒€?/div>
    <div class="table-pager-actions">
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage - 1}"
        ${currentPage <= 1 ? "disabled" : ""}
      >涓婁竴椤?/button>
      ${pages.map((page, index) => `
        ${index > 0 && page - pages[index - 1] > 1 ? '<span class="table-pager-ellipsis">...</span>' : ""}
        <button
          type="button"
          class="button ghost compact table-page-button ${page === currentPage ? "is-active" : ""}"
          data-page="${page}"
          ${page === currentPage ? 'aria-current="page"' : ""}
        >${formatNumber(page)}</button>
      `).join("")}
      <button
        type="button"
        class="button ghost compact table-page-button"
        data-page="${currentPage + 1}"
        ${currentPage >= totalPages ? "disabled" : ""}
      >涓嬩竴椤?/button>
    </div>
  `;
  commentTablePager.querySelectorAll("button[data-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextPage = Number(button.dataset.page || 0);
      if (!nextPage || nextPage === state.commentPage) return;
      state.commentPage = nextPage;
      renderCommentTable(commentRowsForCurrentFilter());
    });
  });
}

function closeCommentReplyModal() {
  state.commentReplyTarget = null;
  if (commentReplyInput) commentReplyInput.value = "";
  setInlineFeedback(commentReplyStatus, "", "neutral");
  if (!commentReplyModal) return;
  commentReplyModal.classList.add("hidden");
  commentReplyModal.setAttribute("aria-hidden", "true");
}

function closeRelationDetailModal() {
  if (!relationDetailModal) return;
  relationDetailModal.classList.add("hidden");
  relationDetailModal.setAttribute("aria-hidden", "true");
  if (relationDetailBody) relationDetailBody.innerHTML = "";
}

function relationMetricValue(value, formatter = (item) => item) {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  return formatter(value);
}

function relationMetricCardMarkup(label, value, className = "") {
  return `
    <div class="relation-card-metric">
      <span>${escapeHtml(label)}</span>
      <strong class="${className}">${escapeHtml(String(value))}</strong>
    </div>
  `;
}

function relationPlanCardMarkup(item) {
  const planId = Number(item?.ad_id || 0);
  const planName = String(item?.ad_name || "").trim() || (planId ? `计划 ${planId}` : "未命名计划");
  const advertiserName = String(item?.advertiser_name || "").trim();
  const payAmount = relationMetricValue(item?.pay_amount, formatMoney);
  const orderCount = relationMetricValue(item?.order_count, formatNumber);
  const roi = relationMetricValue(item?.roi, formatRate);
  return `
    <article class="relation-card">
      <div class="relation-card-head">
        <div>
          <div class="cell-primary">${escapeHtml(planName)}</div>
          <div class="cell-subline mono">
            <span class="cell-subitem">PID ${escapeHtml(String(planId || "-"))}</span>
            ${advertiserName ? `<span class="cell-subitem">${escapeHtml(advertiserName)}</span>` : ""}
          </div>
        </div>
        ${item?.stat_cost !== null && item?.stat_cost !== undefined ? `<span class="pill">消耗 ${formatMoney(item.stat_cost)}</span>` : ""}
      </div>
      <div class="relation-card-metrics">
        ${relationMetricCardMarkup("支付", payAmount, "mono")}
        ${relationMetricCardMarkup("订单", orderCount, "mono")}
        ${relationMetricCardMarkup("ROI", roi, "mono")}
      </div>
    </article>
  `;
}

function relationAccountCardMarkup(item) {
  const advertiserId = Number(item?.advertiser_id || 0);
  const advertiserName = String(item?.advertiser_name || "").trim() || (advertiserId ? `账户 ${advertiserId}` : "未命名账户");
  const topPlanName = String(item?.top_plan_name || "").trim();
  const planCount = relationMetricValue(item?.plan_count, formatNumber);
  const statCost = relationMetricValue(item?.stat_cost, formatMoney);
  const payAmount = relationMetricValue(item?.pay_amount, formatMoney);
  const orderCount = relationMetricValue(item?.order_count, formatNumber);
  return `
    <article class="relation-card">
      <div class="relation-card-head">
        <div>
          <div class="cell-primary">${escapeHtml(advertiserName)}</div>
          <div class="cell-subline mono">
            <span class="cell-subitem">AID ${escapeHtml(String(advertiserId || "-"))}</span>
            ${topPlanName ? `<span class="cell-subitem">代表计划 ${escapeHtml(topPlanName)}</span>` : ""}
          </div>
        </div>
        ${item?.plan_count !== null && item?.plan_count !== undefined ? `<span class="pill">计划 ${formatNumber(item.plan_count)}</span>` : ""}
      </div>
      <div class="relation-card-metrics">
        ${relationMetricCardMarkup("消耗", statCost, "mono")}
        ${relationMetricCardMarkup("支付", payAmount, "mono")}
        ${relationMetricCardMarkup("订单", orderCount, "mono")}
      </div>
    </article>
  `;
}

function openRelationDetailModal({ title, meta, kind, items, emptyText }) {
  if (!relationDetailModal || !relationDetailBody) return;
  if (relationDetailTitle) {
    relationDetailTitle.textContent = title || "关联明细";
  }
  if (relationDetailMeta) {
    relationDetailMeta.textContent = meta || "按当前筛选结果展示关联明细。";
  }
  if (!items.length) {
    relationDetailBody.innerHTML = `<div class="relation-empty">${escapeHtml(emptyText || "当前范围内没有关联明细。")}</div>`;
  } else {
    relationDetailBody.innerHTML = `<div class="relation-list">${items.map((item) => (
      kind === "account" ? relationAccountCardMarkup(item) : relationPlanCardMarkup(item)
    )).join("")}</div>`;
  }
  relationDetailModal.classList.remove("hidden");
  relationDetailModal.setAttribute("aria-hidden", "false");
}

function openAccountPlanRelationDetail(row) {
  const payload = rangePayload(sectionFilter("account"));
  const advertiserId = Number(row?.advertiser_id || 0);
  const plans = buildPlanRelationItems((payload?.plans || []).filter((item) => Number(item?.advertiser_id || 0) === advertiserId));
  openRelationDetailModal({
    title: `${String(row?.advertiser_name || "").trim() || "账户"} 关联计划`,
    meta: `${formatDateWindowMeta(payload)} · AID ${advertiserId || "-"}`,
    kind: "plan",
    items: plans,
    emptyText: "当前筛选范围内没有查询到这个账户的关联计划。",
  });
}

function openProductRelationDetail(row, kind) {
  const payload = rangePayload(sectionFilter("breakdown"));
  const productKey = String(row?.product_key || productKeyForItem(row));
  const plans = (payload?.plans || []).filter((item) => productKeyForItem(item) === productKey);
  const label = String(row?.product_name || row?.product_id || "当前商品").trim() || "当前商品";
  if (kind === "account") {
    openRelationDetailModal({
      title: `${label} 覆盖账户`,
      meta: `${formatDateWindowMeta(payload)} · 由当前商品命中的计划汇总`,
      kind: "account",
      items: buildAccountRelationItemsFromPlans(plans),
      emptyText: "当前筛选范围内没有查询到这个商品覆盖的账户。",
    });
    return;
  }
  openRelationDetailModal({
    title: `${label} 关联计划`,
    meta: `${formatDateWindowMeta(payload)} · 由当前商品命中的计划汇总`,
    kind: "plan",
    items: buildPlanRelationItems(plans),
    emptyText: "当前筛选范围内没有查询到这个商品关联的计划。",
  });
}

function openMaterialRelationDetail(row, kind) {
  const payload = materialRangePayload(sectionFilter("material"));
  const label = String(row?.material_name || row?.material_id || "当前素材").trim() || "当前素材";
  if (kind === "account") {
    openRelationDetailModal({
      title: `${label} 覆盖账户`,
      meta: `${formatDateWindowMeta(payload)} · 基于当前素材汇总关系`,
      kind: "account",
      items: resolveAccountRelationItemsByIds(row?.advertiser_ids || []),
      emptyText: "当前素材没有可展示的关联账户。",
    });
    return;
  }
  openRelationDetailModal({
    title: `${label} 关联计划`,
    meta: `${formatDateWindowMeta(payload)} · 基于当前素材汇总关系`,
    kind: "plan",
    items: resolvePlanRelationItemsByIds(row?.plan_ids || []),
    emptyText: "当前素材没有可展示的关联计划。",
  });
}

function openCommentReplyModal(row) {
  if (!row || !commentReplyModal) return;
  state.commentReplyTarget = {
    advertiser_id: Number(row.advertiser_id || 0),
    comment_id: String(row.comment_id || ""),
  };
  if (commentReplyTitle) {
    commentReplyTitle.textContent = "回复评论";
  }
  if (commentReplyMeta) {
    const commentText = String(row.text || "").trim();
    const previewText = commentText.length > 48 ? `${commentText.slice(0, 48)}...` : commentText;
    commentReplyMeta.textContent = `${row.advertiser_name || "-"} · ${row.create_time || "-"} · ${previewText || "无评论内容"}`;
  }
  if (commentReplyInput) {
    commentReplyInput.value = "";
    commentReplyInput.focus();
  }
  setInlineFeedback(commentReplyStatus, "回复将直接发送到巨量评论管理。", "neutral");
  commentReplyModal.classList.remove("hidden");
  commentReplyModal.setAttribute("aria-hidden", "false");
}

async function submitCommentReply() {
  const target = state.commentReplyTarget;
  if (!target) return;
  const replyText = String(commentReplyInput?.value || "").trim();
  if (!replyText) {
    setInlineFeedback(commentReplyStatus, "请输入回复内容。", "error");
    commentReplyInput?.focus();
    return;
  }
  if (commentReplySubmit) commentReplySubmit.disabled = true;
  setInlineFeedback(commentReplyStatus, "正在发布回复…", "neutral");
  try {
    const response = await fetch("/api/comments/reply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        advertiser_id: target.advertiser_id,
        comment_id: target.comment_id,
        reply_text: replyText,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "回复评论失败");
    }
    closeCommentReplyModal();
    await refreshCommentSection(true);
  } catch (error) {
    setInlineFeedback(commentReplyStatus, error.message || "回复评论失败。", "error");
  } finally {
    if (commentReplySubmit) commentReplySubmit.disabled = false;
  }
}

async function hideComment(row) {
  if (!row || String(row.hide_status || "").trim().toUpperCase() === "HIDE") return;
  const confirmed = window.confirm("确认隐藏这条评论吗？");
  if (!confirmed) return;
  const response = await fetch("/api/comments/hide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      advertiser_id: Number(row.advertiser_id || 0),
      comment_id: String(row.comment_id || ""),
    }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "隐藏评论失败");
  }
  await refreshCommentSection(true);
}


function renderCommentTable(rows) {
  if (!commentTable) return;
  commentTable.classList.add("comment-table");
  const query = String(commentSearch?.value || "").trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = [
      row.text,
      row.comment_user_name,
      row.comment_user_id,
      row.item_title,
      row.promotion_display_name,
      row.material_display_name,
      row.advertiser_name,
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = [
    { key: "text", label: "评论内容", sortable: true },
    { key: "actions", label: "操作", sortable: false },
    { key: "reply_status_text", label: "回复状态", sortable: true },
    { key: "hide_status_text", label: "隐藏状态", sortable: true },
    { key: "level_type_text", label: "评论层级", sortable: true },
    { key: "comment_user_name", label: "评论用户", sortable: true },
    { key: "material_display_name", label: "关联视频素材", sortable: true },
    { key: "reply_count", label: "相关回复数", sortable: true },
    { key: "like_count", label: "点赞数", sortable: true },
    { key: "item_title", label: "视频标题", sortable: true },
    { key: "video_owner_aweme_id", label: "视频所属抖音号", sortable: true },
    { key: "comment_type_text", label: "评论类型", sortable: true },
    { key: "promotion_display_name", label: "评论来源计划", sortable: true },
    { key: "create_time", label: "评论时间", sortable: true },
  ];
  const columnWidths = [
    "240px",
    "112px",
    "84px",
    "84px",
    "84px",
    "160px",
    "240px",
    "76px",
    "76px",
    "300px",
    "112px",
    "96px",
    "160px",
    "150px",
  ];
  const sortedRows = sortRows(visibleRows, state.commentSort);
  const totalRows = sortedRows.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / COMMENT_PAGE_SIZE));
  const currentPage = Math.min(Math.max(Number(state.commentPage) || 1, 1), totalPages);
  const pageStart = totalRows ? (currentPage - 1) * COMMENT_PAGE_SIZE : 0;
  const pageRows = sortedRows.slice(pageStart, pageStart + COMMENT_PAGE_SIZE);
  state.commentPage = currentPage;
  commentTable.innerHTML = `
    <colgroup>
      ${columnWidths.map((width) => `<col style="width: ${width};">`).join("")}
    </colgroup>
    ${makeHeader(columns, state.commentSort, "comment-sort")}
    <tbody>
      ${pageRows.map((row) => `
        <tr data-comment-id="${escapeHtml(row.comment_id)}" data-advertiser-id="${escapeHtml(row.advertiser_id)}">
          <td>
            <div class="cell-primary comment-cell-copy">${escapeHtml(row.text || "-")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">CID ${escapeHtml(truncateMiddle(row.comment_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td>
            <div class="comment-action-buttons">
              <button
                type="button"
                class="button ghost compact"
                data-action="reply-comment"
                data-comment-id="${escapeHtml(row.comment_id)}"
                data-advertiser-id="${escapeHtml(row.advertiser_id)}"
              >回复评论</button>
              <button
                type="button"
                class="button ghost compact"
                data-action="hide-comment"
                data-comment-id="${escapeHtml(row.comment_id)}"
                data-advertiser-id="${escapeHtml(row.advertiser_id)}"
                ${String(row.hide_status || "").trim().toUpperCase() === "HIDE" ? "disabled" : ""}
              >${String(row.hide_status || "").trim().toUpperCase() === "HIDE" ? "已隐藏" : "隐藏评论"}</button>
            </div>
          </td>
          <td>${escapeHtml(row.reply_status_text || "-")}</td>
          <td>${escapeHtml(row.hide_status_text || "-")}</td>
          <td>${escapeHtml(row.level_type_text || "-")}</td>
          <td>
            <div class="cell-primary">${escapeHtml(row.comment_user_name || "未知用户")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">${escapeHtml(row.comment_user_id || "-")}</span>
            </div>
          </td>
          <td>
            <div class="cell-primary">${escapeHtml(row.material_display_name || "-")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">MID ${escapeHtml(truncateMiddle(row.material_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td class="mono">${formatNumber(row.reply_count || 0)}</td>
          <td class="mono">${formatNumber(row.like_count || 0)}</td>
          <td>
            <div class="cell-primary">${escapeHtml(row.item_title || "-")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">VID ${escapeHtml(truncateMiddle(row.item_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td class="mono">${escapeHtml(row.video_owner_aweme_id || "-")}</td>
          <td>${escapeHtml(row.comment_type_text || "-")}</td>
          <td>
            <div class="cell-primary">${escapeHtml(row.promotion_display_name || "-")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">PID ${escapeHtml(truncateMiddle(row.promotion_id || "-", 8, 6))}</span>
            </div>
          </td>
          <td class="mono">${escapeHtml(row.create_time || "-")}</td>
        </tr>
      `).join("")}
    </tbody>
  `;
  commentTable.querySelectorAll("th[data-key]").forEach((header) => {
    header.addEventListener("click", () => {
      const key = header.dataset.key;
      const column = columns.find((item) => item.key === key);
      if (!column || !column.sortable) return;
      state.commentSort = toggleSort(state.commentSort, key);
      saveSort("comment-sort", state.commentSort);
      renderCommentTable(rows);
    });
  });
  commentTable.querySelectorAll('[data-action="reply-comment"]').forEach((button) => {
    button.addEventListener("click", () => {
      const commentId = String(button.dataset.commentId || "");
      const advertiserId = Number(button.dataset.advertiserId || 0);
      const row = visibleRows.find(
        (item) => String(item.comment_id || "") === commentId && Number(item.advertiser_id || 0) === advertiserId,
      );
      if (!row) return;
      openCommentReplyModal(row);
    });
  });
  commentTable.querySelectorAll('[data-action="hide-comment"]').forEach((button) => {
    button.addEventListener("click", async () => {
      const commentId = String(button.dataset.commentId || "");
      const advertiserId = Number(button.dataset.advertiserId || 0);
      const row = visibleRows.find(
        (item) => String(item.comment_id || "") === commentId && Number(item.advertiser_id || 0) === advertiserId,
      );
      if (!row) return;
      try {
        await hideComment(row);
      } catch (error) {
        window.alert(error.message || "隐藏评论失败");
      }
    });
  });
  renderCommentPager(
    totalRows,
    currentPage,
    totalPages,
    totalRows ? pageStart + 1 : 0,
    pageStart + pageRows.length,
  );
}

async function fetchMaterialRankings(force = false) {
  const filter = sectionFilter("material");
  const cacheKey = performanceFilterKey(filter);
  const cachedPayload = state.materialPayloads[cacheKey];
  if (!force && cachedPayload) {
    const expectedSnapshot = latestMaterialSnapshotToken();
    const cachedSnapshot = String(cachedPayload.snapshot_time || "").trim();
    const cachedAt = Number(state.materialPayloadFetchedAt[cacheKey] || 0);
    const freshBySnapshot = Boolean(expectedSnapshot) && cachedSnapshot === expectedSnapshot;
    const freshByAge = !expectedSnapshot && cachedAt > 0 && Date.now() - cachedAt < MATERIAL_CACHE_TTL_MS;
    if (freshBySnapshot || freshByAge) {
      return cachedPayload;
    }
  }
  const params = appendDisplayScopeParam(new URLSearchParams());
  params.set("range", filter.mode);
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  const response = await fetch(`/api/material-rankings?${params.toString()}`).catch(() => null);
  if (!response || !response.ok) {
    const errorPayload = response ? await response.json().catch(() => ({})) : {};
    if (cachedPayload) {
      return cachedPayload;
    }
    throw new Error(errorPayload.detail || "material rankings fetch failed");
  }
  const payload = await response.json();
  state.materialPayloads[cacheKey] = payload;
  state.materialPayloadFetchedAt[cacheKey] = Date.now();
  return payload;
}

async function fetchTeamMaterialRankings(force = false) {
  const filter = sectionFilter("teamMaterial");
  const cacheKey = performanceFilterKey(filter);
  const cachedPayload = state.teamMaterialPayloads[cacheKey];
  if (!force && cachedPayload) {
    const expectedSnapshot = latestMaterialSnapshotToken();
    const cachedSnapshot = String(cachedPayload.snapshot_time || "").trim();
    const cachedAt = Number(state.teamMaterialPayloadFetchedAt[cacheKey] || 0);
    const freshBySnapshot = Boolean(expectedSnapshot) && cachedSnapshot === expectedSnapshot;
    const freshByAge = !expectedSnapshot && cachedAt > 0 && Date.now() - cachedAt < MATERIAL_CACHE_TTL_MS;
    if (freshBySnapshot || freshByAge) {
      return cachedPayload;
    }
  }
  const params = appendDisplayScopeParam(new URLSearchParams());
  params.set("range", filter.mode);
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  const response = await fetch(`/api/team-material-rankings?${params.toString()}`).catch(() => null);
  if (!response || !response.ok) {
    const errorPayload = response ? await response.json().catch(() => ({})) : {};
    if (cachedPayload) {
      return cachedPayload;
    }
    throw new Error(errorPayload.detail || "team material rankings fetch failed");
  }
  const payload = await response.json();
  state.teamMaterialPayloads[cacheKey] = payload;
  state.teamMaterialPayloadFetchedAt[cacheKey] = Date.now();
  return payload;
}

async function fetchComments(force = false) {
  const filter = sectionFilter("comment");
  const advertiserId = commentRequestAdvertiserId();
  const cacheKey = commentCacheKey(filter, advertiserId);
  const cachedPayload = state.commentPayloads[cacheKey];
  const cachedAt = Number(state.commentPayloadFetchedAt[cacheKey] || 0);
  if (!force && cachedPayload && cachedAt > 0 && Date.now() - cachedAt < COMMENT_CACHE_TTL_MS) {
    return cachedPayload;
  }
  const params = new URLSearchParams();
  params.set("range", filter.mode);
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  if (advertiserId > 0) {
    params.set("advertiser_id", String(advertiserId));
  }
  if (force) {
    params.set("force", "1");
  }
  const response = await fetch(`/api/comments?${params.toString()}`).catch(() => null);
  if (!response || !response.ok) {
    const errorPayload = response ? await response.json().catch(() => ({})) : {};
    if (cachedPayload) {
      return cachedPayload;
    }
    throw new Error(errorPayload.detail || "comments fetch failed");
  }
  const payload = await response.json();
  state.commentPayloads[cacheKey] = payload;
  state.commentPayloadFetchedAt[cacheKey] = Date.now();
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
  if (!planAssetSummary) return;
  renderDetailEmptyState(
    planAssetSummary,
    "素材与商品",
    "选中计划后查看资产摘要",
    "这里会展示该计划下的商品、素材类型分布和代表素材。",
  );
}

function planAssetCacheKey(adId, snapshotTime) {
  return `${requestDisplayScope()}:${snapshotTime || "latest"}:${adId}`;
}

async function fetchPlanAssets(adId) {
  const snapshotTime = state.payload?.latest?.snapshot_time || "";
  const cacheKey = planAssetCacheKey(adId, snapshotTime);
  if (state.planAssetCache[cacheKey]) {
    return state.planAssetCache[cacheKey];
  }
  const params = appendDisplayScopeParam(new URLSearchParams());
  if (snapshotTime) {
    params.set("snapshot_time", snapshotTime);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`/api/plans/${encodeURIComponent(adId)}/assets${query}`);
  if (!response.ok) {
    throw new Error("assets fetch failed");
  }
  const payload = await response.json();
  state.planAssetCache[cacheKey] = payload;
  return payload;
}

function renderPlanAssetSummaryPayload(payload) {
  if (!planAssetSummary) return;
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
  const materialTypeCount = Object.keys(typeCount).length;

  planAssetSummary.className = "detail-panel";
  planAssetSummary.innerHTML = `
    <div class="detail-shell-head">
      <div class="detail-shell-copy">
        <span class="detail-eyebrow">商品与素材摘要</span>
        <h4 class="detail-shell-title">计划资产补充信息</h4>
        <div class="detail-meta-row">
          ${detailMetaPill(`明细快照 ${escapeHtml(payload?.snapshot_time || "-")}`)}
          ${detailMetaPill(`素材类型 ${formatNumber(materialTypeCount)}`)}
        </div>
      </div>
    </div>
    <div class="detail-highlight-grid">
      ${detailHighlightCard("商品条数", formatNumber(products.length), "mono")}
      ${detailHighlightCard("素材条数", formatNumber(materials.length), "mono")}
      ${detailHighlightCard("首发视频", formatNumber(payload?.originalVideoCount || 0), "mono")}
      ${detailHighlightCard("素材类型", formatNumber(materialTypeCount), "mono")}
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">素材类型分布</div>
      <div class="asset-tag-row">${typeTags || '<span class="pill">暂无素材</span>'}</div>
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">代表商品</div>
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
    <div class="detail-grid-section">
      <div class="detail-section-title">代表素材</div>
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
  if (!planAssetSummary) return;
  clearPlanAssetSummary();
  try {
    const payload = await fetchPlanAssets(adId);
    renderPlanAssetSummaryPayload(payload);
  } catch {
    renderDetailEmptyState(
      planAssetSummary,
      "素材与商品",
      "计划资产摘要加载失败",
      "请稍后重试，或刷新页面后重新选中该计划。",
    );
  }
}

async function renderPlanDetail(adId) {
  if (!planDetail || !planAssetSummary) return;
  const planFilter = sectionFilter("plan");
  const rows = rangePayload(planFilter)?.plans || [];
  const sourceRow = rows.find((item) => item.ad_id === adId);
  if (!sourceRow) return;
  const row = enrichPlanRow(sourceRow);
  const roiGap = Number(row.roi || 0) - Number(row.roi_goal || 0);
  const currentRangeLabel = rangeLabel(planFilter);
  planDetailStage?.classList.remove("hidden");
  planDetail.className = "detail-panel";
  const rangeSummary = `${currentRangeLabel}内整体支付 ROI ${formatRate(row.roi)}，整体成交 ${formatMoney(row.total_pay_amount)}，净成交 ${formatMoney(row.settled_pay_amount)}，1 小时内退款率 ${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}`;
  planDetail.innerHTML = `
    <div class="detail-shell-head">
      <div class="detail-shell-copy">
        <span class="detail-eyebrow">计划效果明细</span>
        <h4 class="detail-shell-title">${escapeHtml(row.ad_name)}</h4>
        <div class="detail-meta-row">
          ${detailMetaPill(escapeHtml(row.advertiser_name || "-"))}
          ${detailMetaPill(escapeHtml(row.product_name || "未关联商品"))}
          ${renderMarketingGoalBadge(row)}
          ${renderPlanStatusBadge(row)}
        </div>
      </div>
    </div>
    <div class="detail-highlight-grid">
      ${detailHighlightCard("消耗", formatMoney(row.stat_cost), "mono")}
      ${detailHighlightCard("整体成交金额", formatMoney(row.total_pay_amount), "mono")}
      ${detailHighlightCard("净成交金额", formatMoney(row.settled_pay_amount), "mono")}
      ${detailHighlightCard("整体支付 ROI", formatRate(row.roi), "mono")}
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">效果拆分</div>
      <div class="detail-metric-grid">
        ${detailMetricCard("净成交 ROI", formatRate(row.settled_roi), "mono")}
        ${detailMetricCard("支付金额", formatMoney(row.pay_amount), "mono")}
        ${detailMetricCard("整体成交订单数", formatNumber(row.order_count), "mono")}
        ${detailMetricCard("净成交订单数", formatNumber(row.settled_order_count), "mono")}
        ${detailMetricCard("整体成交订单成本", Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-", "mono")}
        ${detailMetricCard("净成交金额结算率", Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-", "mono")}
        ${detailMetricCard("1 小时内退款率", Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-", "mono")}
        ${detailMetricCard("目标 ROI", formatRate(row.roi_goal), "mono")}
        ${detailMetricCard("ROI 差值", `${roiGap >= 0 ? "+" : ""}${formatRate(roiGap)}`, `mono ${roiGap >= 0 ? "positive" : "negative"}`)}
      </div>
    </div>
    <div class="detail-grid-section">
      <div class="detail-section-title">计划信息</div>
      <div class="detail-metric-grid">
        ${detailMetricCard("计划 ID", formatNumber(row.ad_id), "compact mono")}
        ${detailMetricCard("账户 ID", formatNumber(row.advertiser_id), "compact mono")}
        ${detailMetricCard("商品 ID", escapeHtml(row.product_id || "-"), "compact mono")}
        ${detailMetricCard("主播", escapeHtml(row.anchor_name || "-"), "compact")}
        ${detailMetricCard("归属账户", escapeHtml(row.advertiser_name || "-"), "compact")}
        ${detailMetricCard("关联商品", escapeHtml(row.product_name || "-"), "compact")}
      </div>
    </div>
    ${detailNoteCard(`${escapeHtml(currentRangeLabel)}判断`, escapeHtml(rangeSummary))}
  `;
  await renderPlanAssets(adId);
}

function clearPlanDetail() {
  if (!planDetail || !planAssetSummary) return;
  planDetailStage?.classList.remove("hidden");
  renderDetailEmptyState(
    planDetail,
    "计划效果明细",
    "选中计划后查看补充信息",
    "这里会展示计划效果拆分、状态标签和资产摘要。",
  );
  clearPlanAssetSummary();
}

function setSelectedPlan(adId) {
  if (!planDetail || !planAssetSummary) return;
  state.selectedPlanId = adId;
  if (!adId) {
    clearPlanDetail();
    return;
  }
  renderPlanDetail(adId);
}

function renderPlanInteractions(plans) {
  if (!planDetail || !planAssetSummary) return;
  planTable.querySelectorAll("tbody tr").forEach((rowEl) => {
    rowEl.addEventListener("click", () => {
      setSelectedPlan(Number(rowEl.dataset.planId));
      renderPlanTable(plans);
    });
  });
}

function syncSelectedPlan(plans) {
  if (!planDetail || !planAssetSummary) return;
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

function deprecatedRenderPlanTable(plans) {
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
  const columns = [
    { key: "plan_source_text", label: "投放类型", sortable: true },
    { key: "ad_name", label: "计划", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "total_pay_amount", label: "整体成交", sortable: true },
    { key: "settled_pay_amount", label: "净成交", sortable: true },
    { key: "roi", label: "支付ROI", sortable: true },
    { key: "settled_roi", label: "净ROI", sortable: true },
    { key: "order_count", label: "整体订单", sortable: true },
    { key: "settled_order_count", label: "净订单", sortable: true },
    { key: "pay_order_cost", label: "订单成本", sortable: true },
    { key: "settled_amount_rate", label: "结算率", sortable: true },
    { key: "refund_rate_1h", label: "1h退款率", sortable: true },
    { key: "product_name", label: "商品 / 主播", sortable: true },
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "status_text", label: "投放状态", sortable: true },
  ];
  const enrichedRows = plans.map((row) => enrichPlanRow(row));
  const rows = enrichedRows.filter((row) => {
    const haystack = [
      row.ad_name,
      row.product_name,
      row.advertiser_name,
      row.anchor_name,
      row.ad_id,
      row.product_id,
      row.plan_source_text,
      row.marketing_goal_text,
      row.status_text,
    ].join(" ").toLowerCase();
    const matchQuery = haystack.includes(query);
    const matchAccount = !accountFilter || row.advertiser_name === accountFilter;
    return matchQuery && matchAccount;
  });
  const sortedRows = sortRows(rows, state.planSort);
  const supportsPlanDetail = Boolean(planDetail && planAssetSummary);

  planTable.innerHTML = `
    ${makeHeader(columns, state.planSort, "plan-sort")}
    <tbody>
      ${sortedRows.map((row) => `
        <tr data-plan-id="${row.ad_id}" class="${supportsPlanDetail && state.selectedPlanId === row.ad_id ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.ad_name)}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">PID ${escapeHtml(String(row.ad_id || "-"))}</span>
            </div>
          </td>
          <td>${renderPlanSourceBadge(row)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.total_pay_amount)}</td>
          <td class="mono">${formatMoney(row.settled_pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatRate(row.settled_roi)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatNumber(row.settled_order_count)}</td>
          <td class="mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}</td>
          <td>
            <div class="cell-primary">${escapeHtml(row.product_name || "-")}</div>
            <div class="cell-subline">
              ${row.product_id ? `<span class="cell-subitem mono" title="商品 ID：${escapeHtml(row.product_id)}">GID ${escapeHtml(truncateMiddle(row.product_id, 7, 5))}</span>` : ""}
              ${row.anchor_name ? `<span class="cell-subitem">主播 ${escapeHtml(row.anchor_name)}</span>` : ""}
            </div>
          </td>
          <td>${escapeHtml(row.advertiser_name)}</td>
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
  const columns = [
    { key: "ad_name", label: "计划", sortable: true },
    { key: "plan_source_text", label: "投放类型", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "total_pay_amount", label: "整体成交", sortable: true },
    { key: "settled_pay_amount", label: "净成交", sortable: true },
    { key: "roi", label: "支付ROI", sortable: true },
    { key: "settled_roi", label: "净ROI", sortable: true },
    { key: "order_count", label: "整体订单", sortable: true },
    { key: "settled_order_count", label: "净订单", sortable: true },
    { key: "pay_order_cost", label: "订单成本", sortable: true },
    { key: "settled_amount_rate", label: "结算率", sortable: true },
    { key: "refund_rate_1h", label: "1h退款率", sortable: true },
    { key: "product_name", label: "商品 / 主播", sortable: true },
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "status_text", label: "投放状态", sortable: true },
  ];
  const enrichedRows = plans.map((row) => enrichPlanRow(row));
  const rows = enrichedRows.filter((row) => {
    const haystack = [
      row.ad_name,
      row.product_name,
      row.advertiser_name,
      row.anchor_name,
      row.ad_id,
      row.product_id,
      row.plan_source_text,
      row.marketing_goal_text,
      row.status_text,
    ].join(" ").toLowerCase();
    const matchQuery = haystack.includes(query);
    const matchAccount = !accountFilter || row.advertiser_name === accountFilter;
    return matchQuery && matchAccount;
  });
  const sortedRows = sortRows(rows, state.planSort);
  const supportsPlanDetail = Boolean(planDetail && planAssetSummary);

  planTable.innerHTML = `
    ${makeHeader(columns, state.planSort, "plan-sort")}
    <tbody>
      ${sortedRows.map((row) => `
        <tr data-plan-id="${row.ad_id}" class="${supportsPlanDetail && state.selectedPlanId === row.ad_id ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.ad_name)}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">PID ${escapeHtml(String(row.ad_id || "-"))}</span>
            </div>
          </td>
          <td>${renderPlanSourceBadge(row)}</td>
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          <td class="mono">${formatMoney(row.total_pay_amount)}</td>
          <td class="mono">${formatMoney(row.settled_pay_amount)}</td>
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatRate(row.settled_roi)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td class="mono">${formatNumber(row.settled_order_count)}</td>
          <td class="mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</td>
          <td class="mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}</td>
          <td>
            <div class="cell-primary">${escapeHtml(row.product_name || "-")}</div>
            <div class="cell-subline">
              ${row.product_id ? `<span class="cell-subitem mono" title="商品 ID：${escapeHtml(row.product_id)}">GID ${escapeHtml(truncateMiddle(row.product_id, 7, 5))}</span>` : ""}
              ${row.anchor_name ? `<span class="cell-subitem">主播 ${escapeHtml(row.anchor_name)}</span>` : ""}
            </div>
          </td>
          <td>${escapeHtml(row.advertiser_name)}</td>
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
  const filteredRules = filteredAlertRules(rules);
  if (ruleListMeta) {
    const filterLabel = String(ruleStatusFilter?.value || "all");
    const statusText = filterLabel === "enabled" ? "仅看启用" : filterLabel === "disabled" ? "仅看关闭" : "全部状态";
    const query = String(ruleSearchInput?.value || "").trim();
    ruleListMeta.textContent = query
      ? `${statusText} · 命中 ${formatNumber(filteredRules.length)} / ${formatNumber(rules.length)} 条规则`
      : `${statusText} · 当前共 ${formatNumber(filteredRules.length)} 条规则`;
    ruleListMeta.dataset.tone = filteredRules.length ? "neutral" : "warn";
  }
  ruleTable.innerHTML = `
    <thead>
      <tr>
        <th>对象</th>
        <th>条件</th>
        <th>冷却</th>
        <th>状态</th>
        <th>备注</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      ${filteredRules.length ? filteredRules.map((rule) => `
        <tr class="${Number(rule.id) === Number(state.editingRuleId || 0) ? "is-editing" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(entityLabel(rule.entity_type))}</div>
            <div class="cell-subline">
              <span class="cell-subitem">${escapeHtml(targetDisplayLabel(rule.entity_type, rule.target_id))}</span>
            </div>
          </td>
          <td>
            <div class="cell-primary">${escapeHtml(metricLabel(rule.metric))}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem">${escapeHtml(operatorLabel(rule.operator))} ${escapeHtml(rule.threshold)}</span>
              ${["account", "plan"].includes(rule.entity_type) ? `<span class="cell-subitem">最低消耗 ${formatMoney(rule.min_spend)}</span>` : ""}
            </div>
          </td>
          <td class="mono">${formatNumber(rule.cooldown_minutes)} 分钟</td>
          <td><span class="pill">${rule.enabled ? "启用" : "关闭"}</span></td>
          <td>${escapeHtml(rule.note || "--")}</td>
          <td>
            <button class="button ghost compact edit-rule" data-id="${rule.id}">编辑</button>
            <button class="button ghost compact toggle-rule" data-id="${rule.id}">${rule.enabled ? "停用" : "启用"}</button>
            <button class="button ghost compact delete-rule" data-id="${rule.id}">删除</button>
          </td>
        </tr>
      `).join("") : `<tr><td colspan="6" class="empty-cell">${rules.length ? "当前筛选条件下没有命中规则。" : "还没有预警规则，先从账户余额、共享钱包、消耗或爆单规则开始。"}</td></tr>`}
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
      renderRuleTable(state.alertRules || []);
    });
  });

  ruleTable.querySelectorAll(".toggle-rule").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = Number(button.dataset.id);
      const rule = rules.find((item) => Number(item.id) === id);
      if (!rule) return;
      button.disabled = true;
      const response = await fetch(`/api/alert-rules/${id}`, {
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
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        window.alert(errorPayload.detail || "切换规则状态失败");
        button.disabled = false;
        return;
      }
      await fetchDashboard();
    });
  });

  ruleTable.querySelectorAll(".delete-rule").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = Number(button.dataset.id);
      const rule = rules.find((item) => Number(item.id) === id);
      if (!rule) return;
      if (!window.confirm(`确认删除${entityLabel(rule.entity_type)}规则“${metricLabel(rule.metric)}”吗？`)) return;
      button.disabled = true;
      const response = await fetch(`/api/alert-rules/${id}`, { method: "DELETE" });
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        window.alert(errorPayload.detail || "删除规则失败");
        button.disabled = false;
        return;
      }
      if (Number(state.editingRuleId || 0) === id) {
        resetRuleFormState();
      }
      await fetchDashboard();
    });
  });
}

function isAdmin() {
  return state.session?.role === "admin";
}

function isSupervisor() {
  return state.session?.role === "supervisor";
}

function isOperator() {
  return state.session?.role === "operator";
}

function roleLabel(role) {
  if (role === "admin") return "管理员";
  if (role === "supervisor") return "主管";
  if (role === "operator") return "运营";
  return role || "--";
}

function confirmAccountMutation(payload, keywordSeeds = []) {
  const editing = Boolean(state.selectedUserId);
  const title = editing ? "\u4fdd\u5b58\u8d26\u53f7\u53d8\u66f4" : "\u65b0\u5efa\u8d26\u53f7";
  const lines = [
    `${title}\u540e\u5c06\u7acb\u5373\u751f\u6548\u3002`,
    "",
    `\u540d\u79f0\uff1a${payload.display_name || payload.username || "--"}`,
    `\u767b\u5f55\u540d\uff1a${payload.username || "--"}`,
    `\u89d2\u8272\uff1a${roleLabel(payload.role)}`,
    `\u72b6\u6001\uff1a${payload.enabled ? "\u542f\u7528" : "\u505c\u7528"}`,
  ];
  if (payload.role === "supervisor") {
    lines.push(`\u7d20\u6750\u4e0a\u4f20\uff1a${payload.upload_materials_enabled ? "\u5f00\u542f" : "\u5173\u95ed"}`);
  }
  if (payload.role === "operator") {
    lines.push(`\u9884\u8bbe\u5173\u952e\u8bcd\uff1a${formatNumber(keywordSeeds.length)} \u6761`);
  }
  lines.push("");
  lines.push(editing ? "\u786e\u8ba4\u4fdd\u5b58\u5417\uff1f" : "\u786e\u8ba4\u65b0\u5efa\u5417\uff1f");
  return window.confirm(lines.join("\n"));
}

function roleTone(role) {
  if (role === "admin") return "admin";
  if (role === "supervisor") return "supervisor";
  if (role === "operator") return "operator";
  return "neutral";
}

function userScopeSummary(user) {
  if (!user) return "--";
  if (user.role === "admin") return "全部账户";
  if (user.role === "supervisor") return `${formatNumber(user.scope_count || 0)} 个账户`;
  if (user.role === "operator") return "按关键词";
  return "--";
}

function userAvatarText(user) {
  const source = String(user?.display_name || user?.username || "?").trim();
  return escapeHtml(source.slice(0, 1).toUpperCase() || "?");
}

function userCapabilitySummary(user) {
  if (!user) return "--";
  if (user.role === "admin") return "全量访问，默认允许上传素材";
  if (user.role === "supervisor") {
    return user.upload_materials_enabled ? "管理勾选账户并允许上传素材" : "管理勾选账户，上传权限关闭";
  }
  if (user.role === "operator") {
    return `按关键词归属素材，当前 ${formatNumber(user.keyword_count || 0)} 条规则`;
  }
  return "--";
}

function uploadPermissionSummary(user) {
  if (!user) return "--";
  if (user.role === "admin") return "默认允许";
  if (user.role === "supervisor") return user.upload_materials_enabled ? "已开启" : "已关闭";
  return "不适用";
}

function renderAccessOverview() {
  if (!accessOverview) return;
  const users = Array.isArray(state.users) ? state.users : [];
  const adminCount = users.filter((item) => item.role === "admin").length;
  const supervisorCount = users.filter((item) => item.role === "supervisor").length;
  const operatorCount = users.filter((item) => item.role === "operator").length;
  const enabledCount = users.filter((item) => Boolean(item.enabled)).length;
  const uploadEnabledCount = users.filter((item) => item.role === "admin" || (item.role === "supervisor" && item.upload_materials_enabled)).length;
  accessOverview.innerHTML = [
    {
      label: "已配置账号",
      value: formatNumber(users.length),
      detail: users.length ? `启用 ${formatNumber(enabledCount)} 个` : "等待创建账号",
      tone: users.length ? "" : "muted",
    },
    {
      label: "角色分布",
      value: `${formatNumber(adminCount)} / ${formatNumber(supervisorCount)} / ${formatNumber(operatorCount)}`,
      detail: "管理员 / 主管 / 运营",
      tone: "",
    },
    {
      label: "上传能力",
      value: formatNumber(uploadEnabledCount),
      detail: "管理员与已开上传的主管",
      tone: uploadEnabledCount ? "accent" : "muted",
    },
  ].map((item) => `
    <article class="access-overview-card ${item.tone ? `is-${item.tone}` : ""}">
      <span class="access-overview-label">${item.label}</span>
      <strong class="access-overview-value">${item.value}</strong>
      <span class="access-overview-detail">${item.detail}</span>
    </article>
  `).join("");
}

function syncUserRoleFields() {
  if (!userForm) return;
  const role = String(userForm.querySelector('select[name="role"]')?.value || "operator");
  const uploadInput = userForm.querySelector('input[name="upload_materials_enabled"]');
  const keywordSeedInput = userForm.querySelector('textarea[name="keyword_seed"]');
  if (uploadPermissionField) {
    uploadPermissionField.classList.toggle("hidden", role !== "supervisor");
  }
  if (operatorKeywordSeedField) {
    operatorKeywordSeedField.classList.toggle("hidden", role !== "operator");
  }
  if (keywordSeedInput) {
    keywordSeedInput.disabled = role !== "operator";
    if (role !== "operator") {
      keywordSeedInput.value = "";
    }
  }
  if (!uploadInput) return;
  if (role === "admin") {
    uploadInput.checked = true;
    uploadInput.disabled = true;
    return;
  }
  if (role === "supervisor") {
    uploadInput.disabled = false;
    return;
  }
  uploadInput.checked = false;
  uploadInput.disabled = true;
}

function selectedUserKeywords() {
  if (!state.selectedUserId) return [];
  return state.userKeywords[state.selectedUserId] || [];
}

function currentMaterialRows() {
  return (materialRangePayload(sectionFilter("material"))?.items || []).map((row) => enrichMaterialRow(row));
}

function currentTeamMaterialRows() {
  return (teamMaterialRangePayload(sectionFilter("teamMaterial"))?.items || []).map((row) => enrichMaterialRow(row));
}

function selectedMaterialRow(materialKey) {
  const key = String(materialKey || "").trim();
  if (!key) return null;
  return currentMaterialRows().find((item) => item.material_key === key)
    || currentTeamMaterialRows().find((item) => item.material_key === key)
    || null;
}

function canPreviewMaterial(row) {
  if (!row) return false;
  return Boolean(
    String(row.video_url || "").trim()
    || String(row.cover_url || "").trim()
    || materialAwemeLink(row)
  );
}

function materialPreviewTriggerMarkup(row) {
  if (!canPreviewMaterial(row)) {
    return '<span class="material-preview-placeholder">暂无</span>';
  }
  const materialKey = escapeHtml(row.material_key);
  const materialName = escapeHtml(row.material_name || "素材预览");
  const coverUrl = String(row.cover_url || "").trim();
  if (coverUrl) {
    return `
      <button
        type="button"
        class="material-preview-trigger"
        data-action="open-material-preview"
        data-material-key="${materialKey}"
        title="预览 ${materialName}"
      >
        <img class="material-preview-thumb" src="${escapeHtml(coverUrl)}" alt="${materialName}" loading="lazy" />
        <span class="material-preview-badge">预览</span>
      </button>
    `;
  }
  return `
    <button
      type="button"
      class="button ghost compact"
      data-action="open-material-preview"
      data-material-key="${materialKey}"
    >打开预览</button>
  `;
}

function downgradeMaterialPreviewTrigger(button) {
  if (!button || button.classList.contains("is-fallback")) return;
  button.classList.add("is-fallback");
  button.querySelector(".material-preview-thumb")?.remove();
  const badge = button.querySelector(".material-preview-badge");
  if (badge) {
    badge.textContent = "打开预览";
  }
}

function materialAwemeLink(row) {
  const awemeId = String(row?.aweme_item_id || "").trim();
  return awemeId ? `https://www.douyin.com/video/${encodeURIComponent(awemeId)}` : "";
}

function materialPreviewCurveCacheKey(row, filter) {
  const normalized = normalizeRangeFilter(filter);
  return [
    requestDisplayScope(),
    String(row?.material_key || "").trim(),
    normalized.mode,
    normalized.start || "",
    normalized.end || "",
  ].join(":");
}

function materialPreviewCurveRequest(row) {
  const filter = sectionFilter("material");
  const params = appendDisplayScopeParam(new URLSearchParams());
  params.set("material_key", String(row?.material_key || "").trim());
  params.set("range", filter.mode);
  if (filter.mode === "custom") {
    params.set("start_date", filter.start);
    params.set("end_date", filter.end);
  }
  return {
    cacheKey: materialPreviewCurveCacheKey(row, filter),
    url: `/api/material-preview-curve?${params.toString()}`,
  };
}

function materialPreviewCurveLoadingMarkup() {
  return `
    <div class="preview-curve-loading">
      <div class="preview-curve-loading-copy">
        <strong>互动峰形加载中</strong>
        <span>正在拉取视频按秒点击/流失分布</span>
      </div>
      <div class="preview-curve-loading-bar"></div>
    </div>
  `;
}

function materialPreviewCurveEmptyMarkup(title, detail = "") {
  return `
    <div class="preview-curve-empty">
      <strong>${escapeHtml(title || "暂无峰形数据")}</strong>
      ${detail ? `<span>${escapeHtml(detail)}</span>` : ""}
    </div>
  `;
}

function previewCurvePoints(series, width, height, maxSecond, maxValue) {
  const innerWidth = width - 16;
  const innerHeight = height - 24;
  return series.map((item) => {
    const second = Number(item.second || 0);
    const value = Number(item.value || 0);
    const x = 8 + (maxSecond > 0 ? second / maxSecond : 0) * innerWidth;
    const y = 8 + innerHeight - (maxValue > 0 ? value / maxValue : 0) * innerHeight;
    return { x, y, second, value };
  });
}

function previewCurveLinePath(points) {
  if (!points.length) return "";
  if (points.length === 1) {
    const point = points[0];
    return `M ${point.x} ${point.y} L ${point.x + 0.01} ${point.y}`;
  }
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

function previewCurveAreaPath(points, baseline) {
  if (!points.length) return "";
  const linePath = previewCurveLinePath(points);
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath} L ${last.x.toFixed(2)} ${baseline.toFixed(2)} L ${first.x.toFixed(2)} ${baseline.toFixed(2)} Z`;
}

function previewCurveAxisMarks(maxSecond) {
  const marks = [0, 0.33, 0.66, 1];
  return marks.map((ratio) => `${Math.round(maxSecond * ratio)}s`);
}

function renderMaterialPreviewCurvePanel(payload) {
  if (!payload?.supported) {
    return materialPreviewCurveEmptyMarkup("仅视频素材支持峰形图", payload?.message || "当前素材没有可查询的按秒互动分布。");
  }
  const series = Array.isArray(payload?.series) ? payload.series : [];
  if (!series.length) {
    return materialPreviewCurveEmptyMarkup("暂无峰形数据", payload?.message || payload?.notice || "接口暂未返回可用的秒级分布。");
  }

  const chartWidth = 640;
  const chartHeight = 156;
  const loseSeries = series.map((item) => ({ second: Number(item.second || 0), value: Number(item.user_lose_cnt || 0) }));
  const clickSeries = series.map((item) => ({ second: Number(item.second || 0), value: Number(item.click_cnt || 0) }));
  const maxSecond = Math.max(...series.map((item) => Number(item.second || 0)), 1);
  const maxValue = Math.max(
    ...series.map((item) => Math.max(Number(item.user_lose_cnt || 0), Number(item.click_cnt || 0))),
    1,
  );
  const baseline = chartHeight - 16;
  const losePoints = previewCurvePoints(loseSeries, chartWidth, chartHeight, maxSecond, maxValue);
  const clickPoints = previewCurvePoints(clickSeries, chartWidth, chartHeight, maxSecond, maxValue);
  const loseLine = previewCurveLinePath(losePoints);
  const clickLine = previewCurveLinePath(clickPoints);
  const loseArea = previewCurveAreaPath(losePoints, baseline);
  const clickArea = previewCurveAreaPath(clickPoints, baseline);
  const peak = payload?.peak || {};
  const peakSecond = Number(peak.second || 0);
  const peakX = 8 + (maxSecond > 0 ? peakSecond / maxSecond : 0) * (chartWidth - 16);
  const peakY = 8 + (chartHeight - 24) - (maxValue > 0 ? Number(peak.user_lose_cnt || 0) / maxValue : 0) * (chartHeight - 24);
  const gradientId = `preview-curve-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const rangeText = payload?.query_start_date && payload?.query_end_date
    ? (payload.query_start_date === payload.query_end_date
      ? payload.query_end_date
      : `${payload.query_start_date} 至 ${payload.query_end_date}`)
    : "最近可查询范围";
  const note = [payload?.notice, payload?.message].filter(Boolean).join(" ");

  return `
    <div class="preview-curve-head">
      <div class="preview-curve-title">
        <strong>视频互动峰形</strong>
        <span>按秒分布 · ${escapeHtml(rangeText)}</span>
      </div>
      <span class="preview-curve-badge">T+1</span>
    </div>
    <div class="preview-curve-summary">
      <span class="preview-curve-chip lose">流失 ${formatNumber(payload?.totals?.user_lose_cnt || 0)}</span>
      <span class="preview-curve-chip click">点击 ${formatNumber(payload?.totals?.click_cnt || 0)}</span>
      <span class="preview-curve-chip peak">峰值 ${formatNumber(peakSecond)}s</span>
    </div>
    <div class="preview-curve-stage">
      <svg class="preview-curve-svg" viewBox="0 0 ${chartWidth} ${chartHeight}" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="${gradientId}-lose" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="rgba(255, 133, 92, 0.88)"></stop>
            <stop offset="100%" stop-color="rgba(255, 133, 92, 0.08)"></stop>
          </linearGradient>
          <linearGradient id="${gradientId}-click" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="rgba(88, 214, 184, 0.82)"></stop>
            <stop offset="100%" stop-color="rgba(88, 214, 184, 0.08)"></stop>
          </linearGradient>
        </defs>
        <path d="M 8 24 H ${chartWidth - 8}" class="preview-curve-grid"></path>
        <path d="M 8 ${(chartHeight - 24) / 2} H ${chartWidth - 8}" class="preview-curve-grid faint"></path>
        <path d="M 8 ${baseline} H ${chartWidth - 8}" class="preview-curve-grid"></path>
        <path d="${loseArea}" fill="url(#${gradientId}-lose)" class="preview-curve-area lose"></path>
        <path d="${clickArea}" fill="url(#${gradientId}-click)" class="preview-curve-area click"></path>
        <path d="${loseLine}" class="preview-curve-line lose"></path>
        <path d="${clickLine}" class="preview-curve-line click"></path>
        <circle cx="${peakX.toFixed(2)}" cy="${peakY.toFixed(2)}" r="4" class="preview-curve-peak"></circle>
      </svg>
      <div class="preview-curve-axis">
        ${previewCurveAxisMarks(maxSecond).map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
      </div>
    </div>
    ${note ? `<div class="preview-curve-note">${escapeHtml(note)}</div>` : ""}
  `;
}

async function fetchMaterialPreviewCurve(row, force = false) {
  const request = materialPreviewCurveRequest(row);
  if (!force && state.materialPreviewCurveCache[request.cacheKey]) {
    return state.materialPreviewCurveCache[request.cacheKey];
  }
  const response = await fetch(request.url).catch(() => null);
  if (!response || !response.ok) {
    const errorPayload = response ? await response.json().catch(() => ({})) : {};
    throw new Error(errorPayload.detail || "峰形数据请求失败");
  }
  const payload = await response.json();
  state.materialPreviewCurveCache[request.cacheKey] = payload;
  return payload;
}

async function loadMaterialPreviewCurve(row) {
  if (!materialPreviewBody) return;
  const materialKey = String(row?.material_key || "").trim();
  const panel = materialPreviewBody.querySelector('[data-role="preview-curve-panel"]');
  if (!panel || !materialKey) return;
  if (materialTypeKey(row) !== "VIDEO") {
    panel.innerHTML = materialPreviewCurveEmptyMarkup("仅视频素材支持峰形图", "该接口只提供视频素材的按秒点击和流失分布。");
    return;
  }
  const requestToken = ++state.materialPreviewRequestToken;
  materialPreviewBody.dataset.materialKey = materialKey;
  panel.innerHTML = materialPreviewCurveLoadingMarkup();
  try {
    const payload = await fetchMaterialPreviewCurve(row);
    if (!materialPreviewBody || materialPreviewBody.dataset.materialKey !== materialKey) return;
    if (state.materialPreviewRequestToken !== requestToken) return;
    panel.innerHTML = renderMaterialPreviewCurvePanel(payload);
  } catch (error) {
    if (!materialPreviewBody || materialPreviewBody.dataset.materialKey !== materialKey) return;
    if (state.materialPreviewRequestToken !== requestToken) return;
    panel.innerHTML = materialPreviewCurveEmptyMarkup("峰形图加载失败", error?.message || "未能获取预览曲线。");
  }
}

function closeMaterialPreview() {
  if (!materialPreviewModal) return;
  state.materialPreviewRequestToken += 1;
  materialPreviewModal.classList.add("hidden");
  materialPreviewModal.setAttribute("aria-hidden", "true");
  if (materialPreviewBody) {
    delete materialPreviewBody.dataset.materialKey;
    materialPreviewBody.innerHTML = "";
  }
}

function openMaterialPreviewFromRow(row) {
  if (!row || !materialPreviewModal || !materialPreviewBody) return;
  const operatorMode = isOperator();
  row = enrichMaterialRow(row);
  const directVideoUrl = String(row.video_url || "").trim();
  const coverUrl = String(row.cover_url || "").trim();
  const awemeLink = materialAwemeLink(row);
  if (materialPreviewTitle) {
    materialPreviewTitle.textContent = row.material_name || "素材预览";
  }
  if (materialPreviewMeta) {
    materialPreviewMeta.textContent = [
      ...(operatorMode ? [] : [row.top_account_name || "", row.top_plan_name || ""]),
      row.top_anchor_name || "",
    ].filter(Boolean).join(" / ") || "素材预览";
  }
  const previewBlock = directVideoUrl
    ? `<video class="preview-video" src="${escapeHtml(directVideoUrl)}" ${coverUrl ? `poster="${escapeHtml(coverUrl)}"` : ""} controls playsinline preload="metadata"></video>`
    : coverUrl
      ? `<img class="preview-cover" src="${escapeHtml(coverUrl)}" alt="${escapeHtml(row.material_name || "素材封面")}" />`
      : '<div class="preview-empty">当前素材没有可直接预览的地址。</div>';
  const extraActions = [
    awemeLink ? `<a class="button ghost compact" href="${escapeHtml(awemeLink)}" target="_blank" rel="noreferrer">打开抖音作品</a>` : "",
    directVideoUrl ? `<a class="button ghost compact" href="${escapeHtml(directVideoUrl)}" target="_blank" rel="noreferrer">打开原始视频</a>` : "",
  ].filter(Boolean).join("");
  const detailStatsMarkup = operatorMode
    ? `
      <div class="preview-stat"><span>达人</span><strong>${escapeHtml(row.top_anchor_name || "--")}</strong></div>
      <div class="preview-stat"><span>消耗</span><strong class="mono">${formatMoney(row.stat_cost)}</strong></div>
      <div class="preview-stat"><span>整体点击率</span><strong class="mono">${formatPercent(row.overall_ctr)}</strong></div>
    `
    : `
      <div class="preview-stat"><span>归属账户</span><strong>${escapeHtml(row.top_account_name || "--")}</strong></div>
      <div class="preview-stat"><span>归属计划</span><strong>${escapeHtml(row.top_plan_name || "--")}</strong></div>
      <div class="preview-stat"><span>达人</span><strong>${escapeHtml(row.top_anchor_name || "--")}</strong></div>
      <div class="preview-stat"><span>消耗</span><strong class="mono">${formatMoney(row.stat_cost)}</strong></div>
      <div class="preview-stat"><span>整体成交</span><strong class="mono">${formatMaterialTotalPayAmount(row)}</strong></div>
      <div class="preview-stat"><span>净成交</span><strong class="mono">${formatMaterialSettledPayAmount(row)}</strong></div>
      <div class="preview-stat"><span>支付金额</span><strong class="mono">${formatMoney(row.pay_amount)}</strong></div>
      <div class="preview-stat"><span>订单</span><strong class="mono">${formatNumber(row.order_count)}</strong></div>
      <div class="preview-stat"><span>支付ROI</span><strong class="mono">${formatRate(row.roi)}</strong></div>
      <div class="preview-stat"><span>覆盖计划</span><strong class="mono">${formatNumber(row.plan_count)}</strong></div>
      <div class="preview-stat"><span>素材 ID</span><strong class="mono">${escapeHtml(row.material_id || "--")}</strong></div>
      <div class="preview-stat"><span>视频 ID</span><strong class="mono">${escapeHtml(row.video_id || "--")}</strong></div>
    `;
  materialPreviewBody.innerHTML = `
    <div class="preview-media-shell">
      <div class="preview-media-stage">${previewBlock}</div>
      <div class="preview-curve-panel" data-role="preview-curve-panel">${materialPreviewCurveLoadingMarkup()}</div>
    </div>
    <div class="preview-detail-grid">
      ${detailStatsMarkup}
    </div>
    ${extraActions ? `<div class="preview-actions">${extraActions}</div>` : ""}
  `;
  const previewMediaShell = materialPreviewBody.querySelector(".preview-media-shell");
  const previewCurvePanel = materialPreviewBody.querySelector('[data-role="preview-curve-panel"]');
  const previewVideo = materialPreviewBody.querySelector(".preview-video");
  const previewCover = materialPreviewBody.querySelector(".preview-cover");
  previewVideo?.addEventListener("error", () => {
    if (!previewMediaShell) return;
    previewMediaShell.innerHTML = coverUrl
      ? `
        <div class="preview-media-stage">
          <img class="preview-cover" src="${escapeHtml(coverUrl)}" alt="${escapeHtml(row.material_name || "素材封面")}" />
          <div class="preview-empty">当前视频地址无法直接播放，已降级为封面预览。</div>
        </div>
      `
      : '<div class="preview-media-stage"><div class="preview-empty">当前视频地址无法直接播放，请尝试下方入口。</div></div>';
    if (previewCurvePanel) {
      previewMediaShell.appendChild(previewCurvePanel);
    }
    const fallbackCover = previewMediaShell.querySelector(".preview-cover");
    fallbackCover?.addEventListener("error", () => {
      previewMediaShell.innerHTML = '<div class="preview-media-stage"><div class="preview-empty">当前素材没有可站外访问的预览地址，请尝试打开抖音作品。</div></div>';
      if (previewCurvePanel) {
        previewMediaShell.appendChild(previewCurvePanel);
      }
    }, { once: true });
  }, { once: true });
  previewCover?.addEventListener("error", () => {
    if (!previewMediaShell) return;
    previewMediaShell.innerHTML = '<div class="preview-media-stage"><div class="preview-empty">当前素材没有可站外访问的预览地址，请尝试打开抖音作品。</div></div>';
    if (previewCurvePanel) {
      previewMediaShell.appendChild(previewCurvePanel);
    }
  }, { once: true });
  materialPreviewModal.classList.remove("hidden");
  materialPreviewModal.setAttribute("aria-hidden", "false");
  void loadMaterialPreviewCurve(row);
}

function openMaterialPreview(materialKey) {
  const row = selectedMaterialRow(materialKey);
  if (!row) return;
  openMaterialPreviewFromRow(row);
}

function selectedUserMatchedMaterials() {
  if (!state.selectedUserId) return [];
  return state.userMatchedMaterials[state.selectedUserId] || [];
}

async function fetchUserKeywords(userId, force = false) {
  if (!userId || !isAdmin()) return [];
  if (!force && state.userKeywords[userId]) return state.userKeywords[userId];
  const response = await fetch(`/api/users/${userId}/keywords`);
  const payload = await response.json();
  state.userKeywords[userId] = payload.items || [];
  return state.userKeywords[userId];
}

async function fetchUserMatchedMaterials(userId, force = false) {
  if (!userId || !isAdmin()) return [];
  if (!force && state.userMatchedMaterials[userId]) return state.userMatchedMaterials[userId];
  const response = await fetch(`/api/users/${userId}/matched-materials?range=month`);
  const payload = await response.json();
  state.userMatchedMaterials[userId] = payload.items || [];
  return state.userMatchedMaterials[userId];
}

function renderUserKeywordTable() {
  if (!operatorKeywordTable) return;
  if (!isAdmin()) {
    operatorKeywordTable.innerHTML = '<tbody><tr><td class="empty-cell">只有管理员可以配置运营关键词。</td></tr></tbody>';
    return;
  }
  const user = selectedUserRecord();
  if (!user) {
    operatorKeywordTable.innerHTML = '<tbody><tr><td colspan="3" class="empty-cell">先选择一个运营账号，再维护关键词。</td></tr></tbody>';
    return;
  }
  if (user.role !== "operator") {
    operatorKeywordTable.innerHTML = '<tbody><tr><td colspan="3" class="empty-cell">只有运营账号需要配置关键词。</td></tr></tbody>';
    return;
  }
  const items = selectedUserKeywords();
  operatorKeywordTable.innerHTML = `
    <thead>
      <tr>
        <th>关键词</th>
        <th>状态</th>
        <th class="align-right">操作</th>
      </tr>
    </thead>
    <tbody>
      ${items.length ? items.map((item) => `
        <tr data-user-keyword-id="${item.id}">
          <td>${escapeHtml(item.keyword || "--")}</td>
          <td><span class="pill ${item.enabled ? "active" : ""}">${item.enabled ? "启用" : "停用"}</span></td>
          <td class="align-right">
            <button type="button" class="button ghost danger compact" data-action="delete-user-keyword" data-keyword-id="${item.id}">删除</button>
          </td>
        </tr>
      `).join("") : '<tr><td colspan="3" class="empty-cell">还没有关键词。添加后，该账号只看命中结果。</td></tr>'}
    </tbody>
  `;
}

function renderUserMatchedMaterialTable() {
  if (!operatorMaterialTable) return;
  if (!isAdmin()) {
    operatorMaterialTable.innerHTML = '<tbody><tr><td class="empty-cell">只有管理员可以查看运营账号的命中素材。</td></tr></tbody>';
    return;
  }
  const user = selectedUserRecord();
  if (!user) {
    operatorMaterialTable.innerHTML = '<tbody><tr><td colspan="4" class="empty-cell">先选择一个运营账号，再查看命中素材列表。</td></tr></tbody>';
    return;
  }
  if (user.role !== "operator") {
    operatorMaterialTable.innerHTML = '<tbody><tr><td colspan="4" class="empty-cell">只有运营账号才会显示命中素材列表。</td></tr></tbody>';
    return;
  }
  const query = String(operatorMaterialSearch?.value || "").trim().toLowerCase();
  const items = selectedUserMatchedMaterials().filter((item) => {
    if (!query) return true;
    const haystack = [item.material_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  operatorMaterialTable.innerHTML = `
    <thead>
      <tr>
        <th>素材</th>
        <th>预览</th>
        <th>消耗</th>
        <th>账户</th>
        <th>计划</th>
      </tr>
    </thead>
    <tbody>
      ${items.length ? items.map((item) => `
        <tr>
          <td>
            <div class="table-primary">${escapeHtml(item.material_name || "--")}</div>
            <div class="table-sub mono">${escapeHtml(item.material_id || "--")}</div>
          </td>
          <td>
            <button
              type="button"
              class="button ghost compact"
              data-action="preview-user-material"
              data-material-key="${escapeHtml(item.material_key || "")}"
            >预览</button>
          </td>
          <td class="mono">${formatMoney(item.stat_cost)}</td>
          <td>${escapeHtml(item.top_account_name || "--")}</td>
          <td>${escapeHtml(item.top_plan_name || "--")}</td>
        </tr>
      `).join("") : '<tr><td colspan="5" class="empty-cell">当前关键词还没有命中素材。</td></tr>'}
    </tbody>
  `;
  operatorMaterialTable.querySelectorAll('[data-action="preview-user-material"]').forEach((button, index) => {
    button.addEventListener("click", () => {
      const row = items[index];
      if (!row) return;
      openMaterialPreviewFromRow(row);
    });
  });
}

function setOperatorMaterialVisibility(visible) {
  if (operatorMaterialContent) {
    operatorMaterialContent.classList.toggle("hidden", !visible);
  }
  if (toggleOperatorMaterialsButton) {
    toggleOperatorMaterialsButton.textContent = visible ? "收起列表" : "显示列表";
  }
}

function syncAccessRolePanels() {
  const user = selectedUserRecord();
  const role = String(user?.role || userForm?.querySelector('select[name="role"]')?.value || "");
  const isOperator = role === "operator";
  const isSupervisor = role === "supervisor";
  operatorKeywordSection?.classList.toggle("hidden", !isOperator);
  operatorMaterialSection?.classList.toggle("hidden", !isOperator);
  if (!isOperator) {
    setOperatorMaterialVisibility(false);
  }
  if (scopeAccountList?.closest(".ownership-card")) {
    scopeAccountList.closest(".ownership-card").classList.toggle("hidden", isOperator);
  }
  if (!isAdmin()) return;
  if (!user) {
    setInlineFeedback(scopeEditorMeta, "先选账号，再配范围。", "neutral");
    setInlineFeedback(operatorKeywordStatus, "新建运营时可直接填关键词，也可后续追加。", "neutral");
    setInlineFeedback(operatorMaterialStatus, "先选运营，再看近30天命中素材。", "neutral");
    renderUserKeywordTable();
    renderUserMatchedMaterialTable();
    return;
  }
  if (isSupervisor) {
    setInlineFeedback(scopeEditorMeta, "主管只看勾选账户；需要时再开上传。", "neutral");
  } else if (isOperator) {
    setInlineFeedback(scopeEditorMeta, "运营不配置账户范围，只看关键词命中结果。", "neutral");
    setInlineFeedback(operatorKeywordStatus, "新建运营时可直接填关键词，也可后续追加。", "neutral");
    setInlineFeedback(operatorMaterialStatus, "展示近30天内按素材名称关键词命中的素材，默认收起。", "neutral");
  } else {
    setInlineFeedback(scopeEditorMeta, "管理员默认全量可见。", "neutral");
    setInlineFeedback(operatorKeywordStatus, "当前角色不使用运营关键词。", "neutral");
    setInlineFeedback(operatorMaterialStatus, "当前角色不显示运营命中素材。", "neutral");
  }
  renderUserKeywordTable();
  renderUserMatchedMaterialTable();
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
  const supervisor = isSupervisor();
  const operator = isOperator();
  const customerCenterShell = customerCenterChip?.closest(".customer-center-shell");
  if (document.body) {
    document.body.classList.toggle("role-admin", admin);
    document.body.classList.toggle("role-supervisor", supervisor);
    document.body.classList.toggle("role-operator", operator);
  }
  if (operator) {
    state.oceanEnginePopoverOpen = false;
  }
  if (customerCenterShell) {
    customerCenterShell.classList.toggle("hidden", operator);
  }
  const accessTab = viewTabs?.querySelector('[data-view="access"]');
  const signalsTab = viewTabs?.querySelector('[data-view="signals"]');
  const overviewTab = viewTabs?.querySelector('[data-view="overview"]');
  const accountTab = viewTabs?.querySelector('[data-view="accounts"]');
  const planTab = viewTabs?.querySelector('[data-view="plans"]');
  const breakdownTab = viewTabs?.querySelector('[data-view="breakdown"]');
  const materialsTab = viewTabs?.querySelector('[data-view="materials"]');
  const teamMaterialsTab = viewTabs?.querySelector('[data-view="team-materials"]');
  const commentsTab = viewTabs?.querySelector('[data-view="comments"]');
  const uploadsTab = viewTabs?.querySelector('[data-view="uploads"]');
  const tabOrder = admin
    ? ["overview", "accounts", "plans", "materials", "comments", "breakdown", "uploads", "access", "signals"]
    : supervisor
      ? (canUseUploadModule()
        ? ["overview", "accounts", "plans", "materials", "comments", "breakdown", "uploads"]
        : ["overview", "accounts", "plans", "materials", "comments", "breakdown"])
      : ["breakdown", "materials", "team-materials"];
  if (overviewTab) {
    overviewTab.classList.toggle("hidden", operator);
    overviewTab.textContent = "总览";
  }
  if (accessTab) {
    accessTab.classList.toggle("hidden", !admin);
    accessTab.textContent = "账号权限";
  }
  if (signalsTab) {
    signalsTab.classList.toggle("hidden", !admin);
    signalsTab.textContent = "预警";
  }
  if (accountTab) {
    accountTab.classList.toggle("hidden", operator);
  }
  if (planTab) {
    planTab.classList.toggle("hidden", operator);
  }
  if (breakdownTab) {
    breakdownTab.textContent = operator ? "团队排名" : "运营排名";
  }
  if (materialsTab) {
    materialsTab.textContent = operator ? "我的素材" : "素材";
  }
  if (teamMaterialsTab) {
    teamMaterialsTab.classList.toggle("hidden", !operator);
    teamMaterialsTab.textContent = "团队素材";
  }
  if (commentsTab) {
    commentsTab.classList.toggle("hidden", operator);
    commentsTab.textContent = "评论";
  }
  if (uploadsTab) {
    uploadsTab.classList.toggle("hidden", !canUseUploadModule());
    uploadsTab.textContent = "批量上传";
  }
  if (syncButton) {
    syncButton.classList.toggle("hidden", !admin);
  }
  if (syncExtendedButton) {
    syncExtendedButton.classList.toggle("hidden", !admin);
  }
  if (productRankPanel) {
    productRankPanel.classList.add("hidden");
  }
  if (overviewBoardGrid) {
    overviewBoardGrid.classList.toggle("hidden", !admin);
  }
  if (overviewSystemRail) {
    overviewSystemRail.classList.toggle("hidden", !admin);
  }
  if (overviewAlertTitle) {
    overviewAlertTitle.textContent = operator ? "今日重点" : "重点";
  }
  if (breakdownTitle) {
    breakdownTitle.textContent = operator ? "团队排名" : "运营排名";
  }
  if (teamPanelTitle) {
    teamPanelTitle.textContent = operator ? "团队排名" : "运营账号";
  }
  if (materialsPanelTitle) {
    materialsPanelTitle.textContent = operator ? "我的素材" : "素材排行";
  }
  if (teamMaterialsPanelTitle) {
    teamMaterialsPanelTitle.textContent = "团队素材";
  }
  if (commentsPanelTitle) {
    commentsPanelTitle.textContent = "评论";
  }
  if (materialSearch) {
    materialSearch.placeholder = operator ? "搜索素材名称" : "搜索素材";
  }
  if (teamMaterialSearch) {
    teamMaterialSearch.placeholder = operator ? "搜索素材 / 达人" : "搜索素材 / 归属账户 / 计划 / 达人";
  }
  if (heroCopy) {
    heroCopy.textContent = admin
      ? "账户、计划、素材、运营。"
      : supervisor
        ? "范围内账户、计划、素材。"
        : "我的素材、团队素材、团队排名。";
  }
  const allowedViews = admin
    ? new Set(["overview", "accounts", "breakdown", "plans", "materials", "comments", "uploads", "access", "signals"])
    : supervisor
      ? new Set(canUseUploadModule() ? ["overview", "accounts", "breakdown", "plans", "materials", "comments", "uploads"] : ["overview", "accounts", "breakdown", "plans", "materials", "comments"])
      : new Set(["breakdown", "materials", "team-materials"]);
  if (viewTabs) {
    tabOrder.forEach((view) => {
      const tab = viewTabs.querySelector(`[data-view="${view}"]`);
      if (tab) viewTabs.appendChild(tab);
    });
  }
  if (!allowedViews.has(state.activeView)) {
    const fallback = Array.from(allowedViews)[0] || "overview";
    setActiveView(fallback);
  }
  userFormReset && (userFormReset.disabled = !admin);
}

function selectedUserRecord() {
  return state.users.find((item) => Number(item.id) === Number(state.selectedUserId)) || null;
}


function resetScopeSearch() {
  if (scopeSearchInput) scopeSearchInput.value = "";
}

function focusScopeControl() {
  if (scopeSearchInput && !scopeSearchInput.disabled && !scopeControls?.classList.contains("hidden")) {
    scopeSearchInput.focus();
    return;
  }
  scopeAccountList?.querySelector('input[type="checkbox"]')?.focus();
}

function selectedScopeIdSet() {
  return new Set(
    (state.selectedUserScopeIds || [])
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item) && item > 0),
  );
}

function filteredScopeAccounts() {
  const query = String(scopeSearchInput?.value || "").trim().toLowerCase();
  if (!query) return state.catalogAccounts;
  return state.catalogAccounts.filter((item) => {
    const name = String(item.advertiser_name || "").toLowerCase();
    const advertiserId = String(item.advertiser_id || "");
    return name.includes(query) || advertiserId.includes(query);
  });
}

function setScopeControlsState({
  active = false,
  selectedCount = 0,
  visibleCount = 0,
  totalCount = 0,
  query = "",
} = {}) {
  scopeControls?.classList.toggle("hidden", !active);
  if (scopeSearchInput) {
    scopeSearchInput.disabled = !active;
    if (!active) scopeSearchInput.value = "";
  }
  if (scopeSelectVisibleButton) scopeSelectVisibleButton.disabled = !active || visibleCount === 0;
  if (scopeClearSelectedButton) scopeClearSelectedButton.disabled = !active || selectedCount === 0;
  if (!scopeSelectionSummary) return;
  if (!active) {
    scopeSelectionSummary.textContent = "";
    return;
  }
  const baseText = `已选 ${formatNumber(selectedCount)} / ${formatNumber(totalCount)} 个账户`;
  scopeSelectionSummary.textContent = query
    ? `${baseText} · 当前筛到 ${formatNumber(visibleCount)} 个`
    : baseText;
}

function resetUserFormState() {
  state.selectedUserId = null;
  state.selectedUserScopeIds = [];
  state.userKeywords = {};
  state.userMatchedMaterials = {};
  if (userForm) userForm.reset();
  const roleInput = userForm?.querySelector('select[name="role"]');
  if (roleInput) roleInput.value = "operator";
  const enabledInput = userForm?.querySelector('input[name="enabled"]');
  if (enabledInput) enabledInput.checked = true;
  const uploadInput = userForm?.querySelector('input[name="upload_materials_enabled"]');
  if (uploadInput) uploadInput.checked = false;
  const keywordSeedInput = userForm?.querySelector('textarea[name="keyword_seed"]');
  if (keywordSeedInput) keywordSeedInput.value = "";
  resetScopeSearch();
  syncUserRoleFields();
  setInlineFeedback(
    userEditorStatus,
    isAdmin() ? "新建账号时可同时填写关键词。" : "只有管理员可以配置账号。",
    "neutral",
  );
  setInlineFeedback(
    scopeEditorMeta,
    isAdmin() ? "管理员默认全量；主管需要勾选范围。" : "当前账号无权修改范围。",
    "neutral",
  );
  setInlineFeedback(operatorKeywordStatus, "新建运营时可直接填关键词，也可后续追加。", "neutral");
  setInlineFeedback(operatorMaterialStatus, "先选运营，再看近30天命中素材。", "neutral");
  setOperatorMaterialVisibility(false);
  renderScopeChecklist();
  renderUserKeywordTable();
  renderUserMatchedMaterialTable();
  syncAccessRolePanels();
  renderAccessOverview();
  if (isAdmin()) focusFirstInput(userForm, 'input[name="username"]');
}

function fillUserForm(user) {
  if (!userForm) return;
  userForm.querySelector('input[name="username"]').value = user?.username || "";
  userForm.querySelector('input[name="display_name"]').value = user?.display_name || "";
  userForm.querySelector('select[name="role"]').value = user?.role || "operator";
  userForm.querySelector('input[name="password"]').value = "";
  const keywordSeedInput = userForm.querySelector('textarea[name="keyword_seed"]');
  if (keywordSeedInput) keywordSeedInput.value = "";
  userForm.querySelector('input[name="enabled"]').checked = Boolean(user?.enabled);
  userForm.querySelector('input[name="upload_materials_enabled"]').checked = Boolean(user?.upload_materials_enabled);
  syncUserRoleFields();
  setInlineFeedback(
    userEditorStatus,
    user ? `当前编辑：${user.username} · ${roleLabel(user.role)}` : "新建账号时可同时填写关键词。",
    "neutral",
  );
  syncAccessRolePanels();
  renderAccessOverview();
}

function renderUserTable() {
  if (!userTable) return;
  if (!isAdmin()) {
    userTable.innerHTML = '<tbody><tr><td class="empty-cell">当前账号为只读角色，不能配置后台账号。</td></tr></tbody>';
    renderAccessOverview();
    return;
  }
  userTable.innerHTML = `
    <thead>
      <tr>
        <th>成员</th>
        <th>角色与能力</th>
        <th>可见范围</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      ${state.users.length ? state.users.map((item) => `
        <tr data-user-id="${item.id}" class="${Number(state.selectedUserId) === Number(item.id) ? "active-row" : ""}">
          <td>
            <div class="access-user-cell">
              <span class="access-user-avatar role-${escapeHtml(roleTone(item.role))}">${userAvatarText(item)}</span>
              <div class="access-user-copy">
                <strong class="access-user-name">${escapeHtml(item.display_name || item.username)}</strong>
                <span class="access-user-subline mono">@${escapeHtml(item.username)}</span>
              </div>
            </div>
          </td>
          <td>
            <div class="access-user-tags">
              <span class="pill role-${escapeHtml(roleTone(item.role))}">${escapeHtml(roleLabel(item.role))}</span>
              ${item.role === "admin"
                ? '<span class="pill active">默认可上传</span>'
                : item.role === "supervisor"
                  ? `<span class="pill ${item.upload_materials_enabled ? "active" : ""}">${item.upload_materials_enabled ? "可上传" : "仅查看"}</span>`
                  : '<span class="pill">关键词归属</span>'}
            </div>
            <div class="access-user-note">${escapeHtml(userCapabilitySummary(item))}</div>
          </td>
          <td>
            <div class="access-user-note strong">${escapeHtml(userScopeSummary(item))}</div>
            <div class="access-user-subline">${item.role === "operator" ? `关键词 ${formatNumber(item.keyword_count || 0)} 条` : item.role === "supervisor" ? `账户 ${formatNumber(item.scope_count || 0)} 个` : "默认覆盖全部账户"}</div>
          </td>
          <td>
            <span class="pill ${item.enabled ? "active" : ""}">${item.enabled ? "启用" : "停用"}</span>
            <div class="access-user-subline">${escapeHtml(String(item.updated_at || item.created_at || "--").slice(0, 16).replace("T", " "))}</div>
          </td>
        </tr>
      `).join("") : '<tr><td colspan="4" class="empty-cell">还没有后台账号。</td></tr>'}
    </tbody>
  `;
  userTable.querySelectorAll("tbody tr[data-user-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      await selectUserManager(Number(row.dataset.userId));
    });
  });
  renderAccessOverview();
}

function renderScopeChecklist() {
  if (!scopeAccountList) return;
  const user = selectedUserRecord();
  if (!isAdmin()) {
    setScopeControlsState();
    scopeAccountList.innerHTML = '<div class="empty-cell">只有管理员可以配置账户范围。</div>';
    return;
  }
  if (!user) {
    setScopeControlsState();
    scopeAccountList.innerHTML = '<div class="empty-cell">先选择后台账号，再配置账户范围。</div>';
    return;
  }
  if (user.role === "admin") {
    setScopeControlsState();
    scopeAccountList.innerHTML = '<div class="empty-cell">管理员默认可查看全部账户，不需要单独勾选。</div>';
    return;
  }
  if (user.role === "operator") {
    setScopeControlsState();
    scopeAccountList.innerHTML = '<div class="empty-cell">运营账号按关键词看数据，这里不配置范围。</div>';
    return;
  }
  if (!state.catalogAccounts.length) {
    setScopeControlsState();
    scopeAccountList.innerHTML = '<div class="empty-cell">还没有可分配的账户数据。</div>';
    return;
  }
  const query = String(scopeSearchInput?.value || "").trim();
  const selected = selectedScopeIdSet();
  const visibleAccounts = filteredScopeAccounts();
  setScopeControlsState({
    active: true,
    selectedCount: selected.size,
    visibleCount: visibleAccounts.length,
    totalCount: state.catalogAccounts.length,
    query,
  });
  if (!visibleAccounts.length) {
    scopeAccountList.innerHTML = `<div class="empty-cell scope-empty">${query ? "没有匹配的账户，换个关键词试试。" : "还没有可分配的账户数据。"}</div>`;
    return;
  }
  scopeAccountList.innerHTML = visibleAccounts.map((item) => {
    const advertiserId = Number(item.advertiser_id);
    const checked = selected.has(advertiserId);
    return `
      <label class="scope-check ${checked ? "is-selected" : ""}">
        <input type="checkbox" value="${advertiserId}" ${checked ? "checked" : ""} />
        <span class="scope-check-body">
          <span class="scope-check-name">${escapeHtml(item.advertiser_name || String(item.advertiser_id))}</span>
          <span class="scope-check-meta">
            <span class="scope-check-id mono">ID ${formatNumber(advertiserId)}</span>
            <span class="scope-check-state">${checked ? "已选" : "未选"}</span>
          </span>
        </span>
      </label>
    `;
  }).join("");
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
  const params = appendDisplayScopeParam(new URLSearchParams());
  const response = await fetch(`/api/catalog/accounts?${params.toString()}`);
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
  resetScopeSearch();
  const user = selectedUserRecord();
  fillUserForm(user);
  renderUserTable();
  setOperatorMaterialVisibility(false);
  if (user?.role === "supervisor") {
    state.selectedUserScopeIds = await fetchUserScopes(userId, true);
  } else {
    state.selectedUserScopeIds = [];
  }
  if (user?.role === "operator") {
    await fetchUserKeywords(userId, true);
    state.userMatchedMaterials[userId] = [];
  }
  renderScopeChecklist();
  renderUserKeywordTable();
  renderUserMatchedMaterialTable();
  if (isAdmin() && user?.role === "supervisor") {
    focusScopeControl();
  } else if (isAdmin() && user?.role === "operator") {
    focusFirstInput(operatorKeywordForm, 'input[name="keyword"]');
  }
  syncAccessRolePanels();
}

async function ensureAccessData(force = false) {
  await Promise.all([fetchUsers(force), fetchCatalogAccounts(force)]);
  renderUserTable();
  if (state.selectedUserId) {
    fillUserForm(selectedUserRecord());
    const user = selectedUserRecord();
    if (user?.role === "supervisor" && isAdmin()) {
      state.selectedUserScopeIds = await fetchUserScopes(state.selectedUserId, force);
    } else {
      state.selectedUserScopeIds = [];
    }
    if (user?.role === "operator" && isAdmin()) {
      await fetchUserKeywords(state.selectedUserId, force);
      if (!state.userMatchedMaterials[state.selectedUserId]) {
        state.userMatchedMaterials[state.selectedUserId] = [];
      }
    }
  } else {
    resetUserFormState();
  }
  renderScopeChecklist();
  renderUserKeywordTable();
  renderUserMatchedMaterialTable();
  setOperatorMaterialVisibility(false);
  syncAccessRolePanels();
}

async function fetchPerformance(filter, force = false) {
  const normalized = normalizeRangeFilter(filter);
  const cacheKey = performanceFilterKey(normalized);
  if (!force && state.rangePayloads[cacheKey]) {
    return state.rangePayloads[cacheKey];
  }
  const params = appendDisplayScopeParam(new URLSearchParams());
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
  if (breakdownTitle) {
    breakdownTitle.textContent = isOperator() ? "团队排名" : "运营排名";
  }
  if (teamPanelTitle) {
    teamPanelTitle.textContent = isOperator() ? "团队排名" : "运营账号排名";
  }
  if (employeeSearch) {
    employeeSearch.placeholder = breakdownSearchPlaceholder(breakdownPayload);
  }

  renderAccountTable(accountPayload?.accounts || []);
  fillPlanAccountFilter((planPayload?.accounts || []).map((row) => row.advertiser_name));
  renderPlanTable(planPayload?.plans || []);
  renderEmployeeTable(breakdownRows(breakdownPayload));
  renderProductTable(breakdownPayload?.products || []);
  syncSelectedPlan(planPayload?.plans || []);
  syncSelectedEmployee(breakdownRows(breakdownPayload));
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
  syncSectionRangeControls("material");
  const payload = await fetchMaterialRankings(force);
  renderMaterialTable(payload?.items || []);
  syncSelectedMaterial(payload?.items || []);
  const meta = payload?.meta || {};
  const rangeText = formatDateWindowMeta(payload);
  const materialCount = Array.isArray(payload?.items) ? payload.items.length : Number(meta.material_row_count || 0);
  const syncText = payload?.snapshot_time
    ? `${rangeText} · 汇总 ${formatNumber(payload?.snapshot_count || 0)} 个日快照 · 最近明细同步 ${payload.snapshot_time} · 素材 ${formatNumber(materialCount)} 条 · 错误 ${formatNumber(meta.error_count || 0)}`
    : `${rangeText} · 当前时间范围内暂无素材快照`;
  materialSyncMeta.textContent = syncText;
}

async function refreshTeamMaterialSection(force = false) {
  syncSectionRangeControls("teamMaterial");
  const payload = await fetchTeamMaterialRankings(force);
  renderTeamMaterialTable(payload?.items || []);
  const meta = payload?.meta || {};
  const rangeText = formatDateWindowMeta(payload);
  const materialCount = Array.isArray(payload?.items) ? payload.items.length : Number(meta.material_row_count || 0);
  const syncText = payload?.snapshot_time
    ? `${rangeText} · 汇总 ${formatNumber(payload?.snapshot_count || 0)} 个日快照 · 最近明细同步 ${payload.snapshot_time} · 素材 ${formatNumber(materialCount)} 条 · 错误 ${formatNumber(meta.error_count || 0)}`
    : `${rangeText} · 当前时间范围内暂无团队素材`;
  if (teamMaterialSyncMeta) {
    teamMaterialSyncMeta.textContent = syncText;
  }
}

async function refreshCommentSection(force = false) {
  syncSectionRangeControls("comment");
  const payload = await fetchComments(force);
  fillCommentAccountFilter(payload?.accounts || []);
  renderCommentTable(payload?.items || []);
  const meta = payload?.meta || {};
  const rangeText = formatDateWindowMeta(payload);
  const commentCount = Array.isArray(payload?.items) ? payload.items.length : Number(meta.comment_count || 0);
  const accountCount = Array.isArray(payload?.accounts) ? payload.accounts.length : Number(meta.account_count || 0);
  const visibleCount = Number(meta.visible_count || 0);
  const visibleSuffix = visibleCount > 0 && visibleCount !== commentCount ? ` · 可见 ${formatNumber(visibleCount)} 条` : "";
  commentSyncMeta.textContent = `${rangeText} · 评论 ${formatNumber(commentCount)} 条 · 账户 ${formatNumber(accountCount)} 个 · 错误 ${formatNumber(meta.error_count || 0)}${visibleSuffix}`;
}

async function applyQuickRange(sectionKey, mode) {
  const current = sectionFilter(sectionKey);
  if (current.mode === mode) return;
  setRangeEditorOpen(sectionKey, false);
  setSectionFilter(sectionKey, { mode });
  try {
    if (sectionKey === "material") {
      state.materialPage = 1;
      await refreshMaterialSection(false);
      return;
    }
    if (sectionKey === "teamMaterial") {
      state.teamMaterialPage = 1;
      await refreshTeamMaterialSection(false);
      return;
    }
    if (sectionKey === "comment") {
      state.commentPage = 1;
      await refreshCommentSection(false);
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
  setRangeEditorOpen(sectionKey, true);
  setSectionFilter(sectionKey, { mode: "custom", start, end });
  try {
    if (sectionKey === "material") {
      state.materialPage = 1;
      await refreshMaterialSection(false);
      return;
    }
    if (sectionKey === "teamMaterial") {
      state.teamMaterialPage = 1;
      await refreshTeamMaterialSection(false);
      return;
    }
    if (sectionKey === "comment") {
      state.commentPage = 1;
      await refreshCommentSection(false);
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
  const toggle = config.startEl?.closest(".custom-date-inline")?.querySelector('[data-role="custom-range-toggle"]');
  toggle?.addEventListener("click", () => {
    const current = sectionFilter(sectionKey);
    const nextOpen = !(current.mode === "custom" || state.rangeEditorOpen[sectionKey]);
    setRangeEditorOpen(sectionKey, nextOpen);
    syncSectionRangeControls(sectionKey);
    if (nextOpen) {
      config.startEl?.focus();
    }
  });
  [config.startEl, config.endEl].forEach((input) => {
    input?.addEventListener("focus", () => {
      setRangeEditorOpen(sectionKey, true);
      syncSectionRangeControls(sectionKey);
    });
    input?.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      await applyCustomRange(sectionKey);
    });
  });
}

function bindInputs() {
  const debouncedMaterialSearch = debounce(() => {
    state.materialPage = 1;
    renderMaterialTable(materialRowsForCurrentFilter());
  }, MATERIAL_SEARCH_DEBOUNCE_MS);
  const debouncedTeamMaterialSearch = debounce(() => {
    state.teamMaterialPage = 1;
    renderTeamMaterialTable(teamMaterialRowsForCurrentFilter());
  }, MATERIAL_SEARCH_DEBOUNCE_MS);
  const debouncedCommentSearch = debounce(() => {
    state.commentPage = 1;
    renderCommentTable(commentRowsForCurrentFilter());
  }, COMMENT_SEARCH_DEBOUNCE_MS);
  materialPreviewModal?.addEventListener("click", (event) => {
    const trigger = event.target.closest('[data-action="close-preview"]');
    if (trigger) {
      closeMaterialPreview();
    }
  });
  commentReplyModal?.addEventListener("click", (event) => {
    const trigger = event.target.closest('[data-action="close-comment-reply"]');
    if (trigger) {
      closeCommentReplyModal();
    }
  });
  relationDetailModal?.addEventListener("click", (event) => {
    const trigger = event.target.closest('[data-action="close-relation-detail"]');
    if (trigger) {
      closeRelationDetailModal();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && materialPreviewModal && !materialPreviewModal.classList.contains("hidden")) {
      closeMaterialPreview();
    }
    if (event.key === "Escape" && commentReplyModal && !commentReplyModal.classList.contains("hidden")) {
      closeCommentReplyModal();
    }
    if (event.key === "Escape" && relationDetailModal && !relationDetailModal.classList.contains("hidden")) {
      closeRelationDetailModal();
    }
    if (event.key === "Escape" && state.oceanEnginePopoverOpen) {
      setOceanEnginePopoverOpen(false);
    }
  });
  customerCenterChip?.addEventListener("click", (event) => {
    if (!isAdmin()) return;
    event.stopPropagation();
    const nextOpen = !state.oceanEnginePopoverOpen;
    setOceanEnginePopoverOpen(nextOpen);
    if (nextOpen) {
      window.setTimeout(() => {
        const allScopeButton = oceanEngineBoundAccounts?.querySelector('[data-action="switch-display-scope-all"]:not(:disabled)');
        if (allScopeButton) {
          allScopeButton.focus();
          return;
        }
        const firstSavedCcButton = oceanEngineBoundAccounts?.querySelector('[data-action="switch-bound-customer-center"]:not(:disabled)');
        if (firstSavedCcButton) {
          firstSavedCcButton.focus();
          return;
        }
        oceanEngineConfigForm?.querySelector('input[name="customer_center_id"]')?.focus();
      }, 0);
    }
  });
  oceanEngineBoundAccounts?.addEventListener("click", async (event) => {
    const allScopeButton = event.target.closest('[data-action="switch-display-scope-all"]');
    if (allScopeButton && isAdmin()) {
      await switchOceanEngineDisplayScope(DISPLAY_SCOPE_ALL);
      return;
    }
    const button = event.target.closest('[data-action="switch-bound-customer-center"]');
    if (!button || !isAdmin()) return;
    const targetCc = String(button.dataset.customerCenterId || "").trim();
    if (!targetCc) return;
    await switchOceanEngineCustomerCenter(targetCc, "已授权 token");
  });
  oceanEngineConfigCard?.addEventListener("click", (event) => {
    event.stopPropagation();
  });
  document.addEventListener("click", () => {
    if (!state.oceanEnginePopoverOpen) return;
    setOceanEnginePopoverOpen(false);
  });
  if (viewTabs) {
    viewTabs.querySelectorAll(".view-tab").forEach((button) => {
      button.addEventListener("click", async () => {
        if (state.oceanEnginePopoverOpen) {
          setOceanEnginePopoverOpen(false);
        }
        const view = button.dataset.view || "overview";
        setActiveView(view);
        if (view === "materials") {
          await refreshMaterialSection(false);
        }
        if (view === "team-materials") {
          await refreshTeamMaterialSection(false);
        }
        if (view === "comments") {
          await refreshCommentSection(false);
        }
        if (view === "uploads") {
          await fetchUploadTargets(true);
          await fetchUploadJobs();
        }
        if (view === "access") {
          await ensureAccessData(true);
        }
      });
    });
  }

  accountSearch?.addEventListener("input", () => renderAccountTable(rangePayload(sectionFilter("account"))?.accounts || []));
  planSearch?.addEventListener("input", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));
  employeeSearch?.addEventListener("input", () => renderEmployeeTable(breakdownRows(rangePayload(sectionFilter("breakdown")))));
  productSearch?.addEventListener("input", () => renderProductTable(rangePayload(sectionFilter("breakdown"))?.products || []));
  materialSearch?.addEventListener("input", debouncedMaterialSearch);
  teamMaterialSearch?.addEventListener("input", debouncedTeamMaterialSearch);
  commentSearch?.addEventListener("input", debouncedCommentSearch);
  operatorMaterialSearch?.addEventListener("input", () => renderUserMatchedMaterialTable());
  toggleOperatorMaterialsButton?.addEventListener("click", async () => {
    const nextVisible = operatorMaterialContent?.classList.contains("hidden");
    setOperatorMaterialVisibility(Boolean(nextVisible));
    if (nextVisible && state.selectedUserId && isAdmin()) {
      await fetchUserMatchedMaterials(state.selectedUserId, true);
      renderUserMatchedMaterialTable();
    }
  });
  planAccountFilter?.addEventListener("change", () => renderPlanTable(rangePayload(sectionFilter("plan"))?.plans || []));
  commentAccountFilter?.addEventListener("change", async () => {
    state.commentPage = 1;
    await refreshCommentSection(false);
  });
  commentRefreshButton?.addEventListener("click", async () => {
    state.commentPage = 1;
    await refreshCommentSection(true);
  });
  commentReplySubmit?.addEventListener("click", async () => {
    await submitCommentReply();
  });
  commentReplyInput?.addEventListener("keydown", async (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      await submitCommentReply();
    }
  });
  uploadSearchForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await fetchUploadTargets(true);
  });
  uploadSelectAll?.addEventListener("change", () => {
    const items = state.uploadTargets?.plans || [];
    state.uploadSelectedPlanIds = uploadSelectAll.checked ? items.map((item) => Number(item.ad_id)) : [];
    renderUploadTargetTable();
  });
  uploadTargetTable?.addEventListener("change", (event) => {
    const input = event.target.closest(".upload-target-checkbox");
    if (!input) return;
    const planId = Number(input.dataset.planId || 0);
    if (!planId) return;
    if (input.checked) {
      if (!state.uploadSelectedPlanIds.includes(planId)) state.uploadSelectedPlanIds.push(planId);
    } else {
      state.uploadSelectedPlanIds = state.uploadSelectedPlanIds.filter((item) => item !== planId);
    }
    const total = (state.uploadTargets?.plans || []).length;
    if (uploadSelectAll) {
      uploadSelectAll.checked = total > 0 && state.uploadSelectedPlanIds.length === total;
    }
    renderUploadTargetSummary();
  });
  uploadJobTable?.addEventListener("click", async (event) => {
    const retryButton = event.target.closest('[data-action="retry-upload-job"]');
    const deleteButton = event.target.closest('[data-action="delete-upload-job"]');
    const button = retryButton || deleteButton;
    if (!button) return;
    const jobId = Number(button.dataset.jobId || 0);
    if (!jobId) return;
    if (retryButton) {
      await retryUploadJob(jobId);
      return;
    }
    await deleteUploadJob(jobId);
  });
  uploadFileInput?.addEventListener("change", () => {
    state.uploadFiles = Array.from(uploadFileInput.files || []);
    renderUploadFileSummary();
  });
  uploadJobForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.uploadSelectedPlanIds.length) {
      window.alert("请先勾选目标计划");
      return;
    }
    if (!state.uploadFiles.length) {
      window.alert("请先选择视频文件");
      return;
    }
    const form = new FormData();
    form.set("scope", String(uploadScopeSelect?.value || "plan"));
    form.set("query_text", String(uploadKeywordInput?.value || "").trim());
    form.set("target_plan_ids", JSON.stringify(state.uploadSelectedPlanIds));
    state.uploadFiles.forEach((file) => form.append("files", file));
    uploadJobSubmit.disabled = true;
    setInlineFeedback(uploadJobStatus, "正在创建上传任务…", "neutral");
    try {
      const response = await fetch("/api/upload/jobs", { method: "POST", body: form });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        window.alert(payload.detail || "创建上传任务失败");
        setInlineFeedback(uploadJobStatus, "创建上传任务失败。", "error");
        return;
      }
      state.uploadFiles = [];
      if (uploadFileInput) uploadFileInput.value = "";
      renderUploadFileSummary();
      setInlineFeedback(uploadJobStatus, `已创建任务 #${payload.id}，当前为准备状态。`, "success");
      await fetchUploadJobs();
    } finally {
      uploadJobSubmit.disabled = false;
    }
  });

  bindRangeFilterControls("account");
  bindRangeFilterControls("plan");
  bindRangeFilterControls("breakdown");
  bindRangeFilterControls("material");
  bindRangeFilterControls("teamMaterial");
  bindRangeFilterControls("comment");

  oceanEngineConfigForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(oceanEngineConfigForm);
    const targetCc = String(form.get("customer_center_id") || "").trim();
    await switchOceanEngineCustomerCenter(targetCc, "手动输入");
  });


  ruleForm?.querySelector('select[name="entity_type"]')?.addEventListener("change", () => {
    if (ruleTargetInput) ruleTargetInput.value = "";
    if (ruleTargetSearchInput) ruleTargetSearchInput.value = "";
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
      if (ruleTargetSearchInput) ruleTargetSearchInput.value = "";
      if (ruleFormHint) {
        ruleFormHint.textContent = `已套用 ${button.textContent.trim()} 模板，可继续补充具体对象和阈值。`;
        ruleFormHint.dataset.tone = "neutral";
      }
    });
  });

  notificationForm?.addEventListener("submit", async (event) => {
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
    const submitButton = document.querySelector('button[form="notificationForm"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "保存中...";
    }
    try {
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
      if (notificationStatus) {
        notificationStatus.dataset.tone = "success";
      }
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "保存通知";
      }
    }
  });

  ruleForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    syncRuleTargetSelectionFromSearch();
    const form = new FormData(ruleForm);
    const targetSearchValue = String(ruleTargetSearchInput?.value || "").trim();
    const targetIdValue = String(form.get("target_id") || "").trim();
    if (targetSearchValue && !targetIdValue) {
      window.alert("请从下拉候选项中选择一个具体对象，或清空后按全部对象生效。");
      ruleTargetSearchInput?.focus();
      return;
    }
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
    if (ruleFormSubmitButton) {
      ruleFormSubmitButton.disabled = true;
      ruleFormSubmitButton.textContent = ruleId ? "保存中..." : "创建中...";
    }
    try {
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
        ruleFormHint.textContent = `已保存${savedLabel}规则。可继续新增，或到下方调整状态。`;
        ruleFormHint.dataset.tone = "success";
      }
    } finally {
      if (ruleFormSubmitButton) {
        ruleFormSubmitButton.disabled = false;
        ruleFormSubmitButton.textContent = state.editingRuleId ? "保存规则" : "新增规则";
      }
    }
  });

  ruleTargetSearchInput?.addEventListener("input", () => {
    syncRuleTargetSelectionFromSearch();
  });

  ruleTargetSearchInput?.addEventListener("change", () => {
    syncRuleTargetSelectionFromSearch();
  });

  ruleForm?.addEventListener("input", () => {
    renderRulePreview();
  });

  ruleForm?.addEventListener("change", () => {
    renderRulePreview();
  });

  notificationForm?.addEventListener("input", () => {
    syncNotificationFormFields();
  });

  notificationForm?.addEventListener("change", () => {
    syncNotificationFormFields();
  });

  ruleStatusFilter?.addEventListener("change", () => {
    renderRuleTable(state.alertRules || []);
  });

  ruleSearchInput?.addEventListener("input", () => {
    renderRuleTable(state.alertRules || []);
  });

  syncButton?.addEventListener("click", async () => {
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
        const response = await fetch("/api/sync/extended?force_refresh=1", { method: "POST" });
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
    const keywordSeeds = parseKeywordSeedInput(form.get("keyword_seed"));
    const payload = {
      username: String(form.get("username") || "").trim(),
      display_name: String(form.get("display_name") || "").trim(),
      role: String(form.get("role") || "operator"),
      password: String(form.get("password") || ""),
      enabled: form.get("enabled") === "on",
      upload_materials_enabled: form.get("upload_materials_enabled") === "on",
    };
    if (!confirmAccountMutation(payload, keywordSeeds)) {
      setInlineFeedback(userEditorStatus, "已取消提交账号变更。", "neutral");
      return;
    }
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
      let addedKeywordCount = 0;
      if (item.role === "operator" && keywordSeeds.length) {
        const existingKeywords = new Set(
          (state.userKeywords[item.id] || []).map((entry) => String(entry.keyword || "").trim().toLowerCase()),
        );
        for (const keyword of keywordSeeds) {
          if (existingKeywords.has(keyword.toLowerCase())) continue;
          const keywordResponse = await fetch(`/api/users/${item.id}/keywords`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keyword, enabled: true }),
          });
          if (keywordResponse.ok) {
            addedKeywordCount += 1;
            existingKeywords.add(keyword.toLowerCase());
          }
        }
        await fetchUserKeywords(item.id, true);
      }
      const keywordSuffix = addedKeywordCount ? `，并新增 ${addedKeywordCount} 个关键词` : "";
      setInlineFeedback(userEditorStatus, `已保存账号 ${item.username || payload.username}${keywordSuffix}。`, "success");
      if (item.role === "supervisor") {
        setInlineFeedback(scopeEditorMeta, "继续勾选该主管可见账户。", "success");
        focusScopeControl();
      } else if (item.role === "operator") {
        if (addedKeywordCount) {
          setInlineFeedback(operatorKeywordStatus, "关键词已保存，可继续追加。", "success");
        } else {
          setInlineFeedback(operatorKeywordStatus, "可继续追加关键词。", "success");
          focusFirstInput(operatorKeywordForm, 'input[name="keyword"]');
        }
      }
    } else {
      await ensureAccessData(true);
    }
  });

  userFormReset?.addEventListener("click", () => {
    resetUserFormState();
    renderUserTable();
  });

  userForm?.querySelector('select[name="role"]')?.addEventListener("change", () => {
    syncUserRoleFields();
    syncAccessRolePanels();
    renderScopeChecklist();
  });

  scopeSearchInput?.addEventListener("input", () => {
    renderScopeChecklist();
  });

  scopeAccountList?.addEventListener("change", (event) => {
    const user = selectedUserRecord();
    if (!isAdmin() || !user || user.role !== "supervisor") return;
    const checkbox = event.target.closest('input[type="checkbox"]');
    if (!checkbox) return;
    const advertiserId = Number(checkbox.value);
    if (!Number.isFinite(advertiserId)) return;
    const selected = selectedScopeIdSet();
    if (checkbox.checked) {
      selected.add(advertiserId);
    } else {
      selected.delete(advertiserId);
    }
    state.selectedUserScopeIds = [...selected].sort((left, right) => left - right);
    const card = checkbox.closest(".scope-check");
    card?.classList.toggle("is-selected", checkbox.checked);
    const stateBadge = card?.querySelector(".scope-check-state");
    if (stateBadge) stateBadge.textContent = checkbox.checked ? "已选" : "未选";
    setScopeControlsState({
      active: true,
      selectedCount: selected.size,
      visibleCount: filteredScopeAccounts().length,
      totalCount: state.catalogAccounts.length,
      query: String(scopeSearchInput?.value || "").trim(),
    });
  });

  scopeSelectVisibleButton?.addEventListener("click", () => {
    const user = selectedUserRecord();
    if (!isAdmin() || !user || user.role !== "supervisor") return;
    const visibleAccounts = filteredScopeAccounts();
    if (!visibleAccounts.length) return;
    const selected = selectedScopeIdSet();
    visibleAccounts.forEach((item) => {
      const advertiserId = Number(item.advertiser_id);
      if (Number.isFinite(advertiserId)) selected.add(advertiserId);
    });
    state.selectedUserScopeIds = [...selected].sort((left, right) => left - right);
    renderScopeChecklist();
  });

  scopeClearSelectedButton?.addEventListener("click", () => {
    const user = selectedUserRecord();
    if (!isAdmin() || !user || user.role !== "supervisor") return;
    if (!state.selectedUserScopeIds.length) return;
    state.selectedUserScopeIds = [];
    renderScopeChecklist();
  });

  operatorKeywordForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!isAdmin() || !state.selectedUserId) {
      window.alert("请先选择一个运营账号");
      return;
    }
    const user = selectedUserRecord();
    if (!user || user.role !== "operator") {
      window.alert("只有运营账号可以配置关键词");
      return;
    }
    const form = new FormData(operatorKeywordForm);
    const payload = {
      keyword: String(form.get("keyword") || "").trim(),
      enabled: form.get("enabled") === "on",
    };
    if (!payload.keyword) {
      window.alert("请输入关键词");
      return;
    }
    const response = await fetch(`/api/users/${state.selectedUserId}/keywords`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "新增运营关键词失败");
      return;
    }
    operatorKeywordForm.reset();
    operatorKeywordForm.querySelector('input[name="enabled"]').checked = true;
    await fetchUserKeywords(state.selectedUserId, true);
    await fetchUserMatchedMaterials(state.selectedUserId, true);
    renderUserKeywordTable();
    renderUserMatchedMaterialTable();
    setInlineFeedback(operatorKeywordStatus, `已添加关键词“${payload.keyword}”。`, "success");
    focusFirstInput(operatorKeywordForm, 'input[name="keyword"]');
    await fetchDashboard();
  });

  operatorKeywordTable?.addEventListener("click", async (event) => {
    const button = event.target.closest('[data-action="delete-user-keyword"]');
    if (!button || !isAdmin()) return;
    const keywordId = Number(button.dataset.keywordId || 0);
    if (!keywordId) return;
    const response = await fetch(`/api/user-keywords/${keywordId}`, { method: "DELETE" });
    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      window.alert(errorPayload.detail || "删除运营关键词失败");
      return;
    }
    if (state.selectedUserId) {
      await fetchUserKeywords(state.selectedUserId, true);
      await fetchUserMatchedMaterials(state.selectedUserId, true);
    }
    renderUserKeywordTable();
    renderUserMatchedMaterialTable();
    setInlineFeedback(operatorKeywordStatus, "已删除关键词。", "success");
    await fetchDashboard();
  });

  saveUserScopesButton?.addEventListener("click", async () => {
    if (!isAdmin() || !state.selectedUserId) return;
    const user = selectedUserRecord();
    if (!user || user.role === "admin") {
      window.alert("管理员默认拥有全部权限，无需设置账户范围。");
      return;
    }
    if (user.role !== "supervisor") return;
    const advertiserIds = [...selectedScopeIdSet()].sort((left, right) => left - right);
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
  const params = appendDisplayScopeParam(new URLSearchParams());
  const response = await fetch(`/api/dashboard?${params.toString()}`);
  const payload = await response.json();
  state.payload = payload;
  state.session = payload.session || null;
  state.oceanEngineConfig = payload.oceanEngineConfig || null;
  if (!payload.latest) {
    applyRoleViewPolicy();
    renderOceanEngineConfig(payload.oceanEngineConfig || { customer_center_id: payload.customerCenterId || "" });
    return;
  }
  await render(payload);
}

async function render(payload) {
  const latest = payload.latest;
  state.alertRules = payload.alertRules || [];
  applyRoleViewPolicy();
  renderOceanEngineConfig(payload.oceanEngineConfig || { customer_center_id: payload.customerCenterId || "" });
  renderOverviewHero(latest);
  renderKpis(latest);
  renderSystemCards(latest, payload.extendedSync || latest?.extendedSync, payload.tokenInfo || {});
  renderAlerts(payload.alertEvents || []);
  renderSignalOverview(payload.notificationSettings || {}, state.alertRules);
  renderNotificationSettings(payload.notificationSettings || {});
  renderRuleTable(state.alertRules);
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
      await refreshMaterialSection(false);
    } catch (error) {
      console.error("refreshMaterialSection failed", error);
    }
  }
  if (state.activeView === "team-materials") {
    try {
      await refreshTeamMaterialSection(false);
    } catch (error) {
      console.error("refreshTeamMaterialSection failed", error);
    }
  }
  if (state.activeView === "comments") {
    try {
      await refreshCommentSection(false);
    } catch (error) {
      console.error("refreshCommentSection failed", error);
    }
  }
  if (state.activeView === "access") {
    try {
      await ensureAccessData(true);
    } catch (error) {
      console.error("ensureAccessData failed", error);
    }
  }
  if (state.activeView === "uploads" && canUseUploadModule()) {
    try {
      await fetchUploadTargets(true);
      await fetchUploadJobs();
    } catch (error) {
      console.error("upload section load failed", error);
    }
  }
  setActiveView(state.activeView);
}

bindInputs();
setActiveView(state.activeView);
fetchDashboard();
window.setInterval(fetchDashboard, 60 * 1000);
window.setInterval(() => {
  if (state.activeView === "uploads" && canUseUploadModule()) {
    fetchUploadJobs().catch(() => {});
  }
}, 5 * 1000);
