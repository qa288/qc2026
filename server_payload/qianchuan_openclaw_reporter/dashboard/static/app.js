const RANGE_LABELS = {
  day: "今日",
  yesterday: "昨日",
  week: "近7天",
  month: "近30天",
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
  users: [],
  catalogAccounts: [],
  userScopes: {},
  userKeywords: {},
  userMatchedMaterials: {},
  uploadTargets: null,
  uploadJobs: [],
  uploadSelectedPlanIds: [],
  uploadFiles: [],
  unassignedScope: "all",
  accountSort: loadSort("account-sort", { key: "stat_cost", dir: "desc" }),
  planSort: loadSort("plan-sort", { key: "order_count", dir: "desc" }),
  employeeSort: loadSort("employee-sort", { key: "stat_cost", dir: "desc" }),
  productSort: loadSort("product-sort", { key: "order_count", dir: "desc" }),
  materialSort: loadSort("material-sort", { key: "stat_cost", dir: "desc" }),
  activeView: loadPreference("active-view", "overview"),
  ruleTargetOptions: [],
  performanceFilters: {
    account: loadRangeFilter("account-range-filter", "day"),
    plan: loadRangeFilter("plan-range-filter", "day"),
    breakdown: loadRangeFilter("breakdown-range-filter", "day"),
    material: loadRangeFilter("material-range-filter", "day"),
  },
  rangeEditorOpen: {},
  selectedPlanId: null,
  selectedEmployeeName: null,
  selectedProductKey: null,
  selectedMaterialKey: null,
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
const planDetailStage = document.getElementById("planDetailStage");
const employeeDetail = document.getElementById("employeeDetail");
const productDetail = document.getElementById("productDetail");
const planAssetSummary = document.getElementById("planAssetSummary");
const materialTable = document.getElementById("materialTable");
const materialDetail = document.getElementById("materialDetail");
const materialDetailStage = document.getElementById("materialDetailStage");
const alertSummary = document.getElementById("alertSummary");
const accountSearch = document.getElementById("accountSearch");
const planSearch = document.getElementById("planSearch");
const employeeSearch = document.getElementById("employeeSearch");
const productSearch = document.getElementById("productSearch");
const breakdownTitle = document.getElementById("breakdownTitle");
const teamPanelTitle = document.getElementById("teamPanelTitle");
const productRankPanel = document.getElementById("productRankPanel");
const materialSearch = document.getElementById("materialSearch");
const planAccountFilter = document.getElementById("planAccountFilter");
const notificationForm = document.getElementById("notificationForm");
const notificationStatus = document.getElementById("notificationStatus");
const ruleForm = document.getElementById("ruleForm");
const ruleFormHint = document.getElementById("ruleFormHint");
const ruleFormSubmitButton = document.getElementById("ruleFormSubmitButton");
const ruleFormCancelButton = document.getElementById("ruleFormCancelButton");
const ruleTargetInput = document.getElementById("ruleTargetInput");
const ruleTargetSearchInput = document.getElementById("ruleTargetSearchInput");
const ruleTargetLabel = document.getElementById("ruleTargetLabel");
const ruleTargetOptions = document.getElementById("ruleTargetOptions");
const ruleTargetMeta = document.getElementById("ruleTargetMeta");
const ruleMinSpendField = document.getElementById("ruleMinSpendField");
const syncButton = document.getElementById("syncButton");
const syncExtendedButton = document.getElementById("syncExtendedButton");
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
const userTable = document.getElementById("userTable");
const userForm = document.getElementById("userForm");
const userFormReset = document.getElementById("userFormReset");
const userEditorStatus = document.getElementById("userEditorStatus");
const uploadPermissionField = document.getElementById("uploadPermissionField");
const operatorKeywordSeedField = document.getElementById("operatorKeywordSeedField");
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
}

function syncRuleTargetSelectionFromSearch() {
  if (!ruleTargetSearchInput || !ruleTargetInput) return;
  const text = String(ruleTargetSearchInput.value || "").trim();
  if (!text) {
    ruleTargetInput.value = "";
    if (ruleTargetMeta) {
      ruleTargetMeta.dataset.tone = "neutral";
    }
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
    return;
  }
  ruleTargetInput.value = "";
  if (ruleTargetMeta) {
    ruleTargetMeta.textContent = "请输入关键词后，从下拉候选项中选择一个具体对象；留空表示全部。";
    ruleTargetMeta.dataset.tone = "neutral";
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

function enrichPlanRow(row) {
  const statCost = Number(row?.stat_cost || 0);
  const totalPayAmount = Number(row?.total_pay_amount || 0);
  const settledPayAmount = Number(row?.settled_pay_amount || 0);
  const orderCount = Number(row?.order_count || 0);
  const settledOrderCount = Number(row?.settled_order_count || 0);
  const refundAmount1h = Number(row?.refund_amount_1h || 0);
  return {
    ...row,
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
  if (text.includes("/local/file/video/upload/ permission")) {
    return "当前应用还没有该广告主的视频上传权限，请先补齐应用授权或接口权限。";
  }
  return text;
}

function uploadJobStatusLabel(status) {
  const value = String(status || "").trim().toLowerCase();
  if (value === "ok") return "完成";
  if (value === "running") return "进行中";
  if (value === "partial") return "部分完成";
  if (value === "failed") return "失败";
  if (value === "prepared") return "待执行";
  return status || "--";
}

function uploadJobStatusClass(status) {
  const value = String(status || "").trim().toLowerCase();
  if (value === "ok") return "live";
  if (value === "running" || value === "prepared") return "paused";
  if (value === "partial" || value === "failed") return "system";
  return "neutral";
}

function renderUploadJobNote(item) {
  const base = normalizeUploadJobNote(item.note);
  const failedItems = Array.isArray(item.failed_items) ? item.failed_items : [];
  if (!failedItems.length) {
    return escapeHtml(base);
  }
  const failedNames = failedItems
    .map((row) => String(row.original_name || "").trim())
    .filter(Boolean)
    .slice(0, 5);
  const extraCount = Math.max(0, failedItems.length - failedNames.length);
  const summary = failedNames.length
    ? `失败文件：${failedNames.join("、")}${extraCount ? ` 等 ${formatNumber(failedItems.length)} 个` : ""}`
    : `失败文件：${formatNumber(failedItems.length)} 个`;
  return `
    <div class="cell-primary">${escapeHtml(base)}</div>
    <div class="cell-subline">
      <span class="cell-subitem">${escapeHtml(summary)}</span>
    </div>
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
    uploadJobTable.innerHTML = '<tbody><tr><td colspan="8" class="empty-cell">还没有上传任务。</td></tr></tbody>';
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
              <span class="cell-subitem">${item.failed_files ? "查看备注" : "--"}</span>
            </div>
          </td>
          <td>${escapeHtml(item.created_at || "--")}</td>
          <td>${renderUploadJobNote(item)}</td>
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
  const columns = [
    { key: "advertiser_name", label: "账户", sortable: true },
    { key: "stat_cost", label: "消耗", sortable: true },
    { key: "pay_amount", label: "支付", sortable: true },
    { key: "order_count", label: "订单", sortable: true },
    { key: "roi", label: "ROI", sortable: true },
    { key: "status_text", label: "状态", sortable: false },
  ];
  const enrichedRows = accounts.map((row) => ({
    ...row,
    status_text: !row.ok ? "查询失败" : String(row.error || "").startsWith("fallback:") ? "计划聚合" : "正常",
  }));
  const rows = enrichedRows.filter((row) => {
    const haystack = [
      row.advertiser_name,
      row.advertiser_id,
      row.status_text,
      row.error,
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const sorted = sortRows(rows, state.accountSort);

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
  const row = rows.find((item) => breakdownEntityName(item) === employeeName);
  if (!row) return;
  const operatorMode = breakdownUsesOperators(payload);
  const entityLabel = breakdownEntityLabel(payload);
  employeeDetail.className = "detail-panel";
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
  if (!productDetail) return;
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
  const query = employeeSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = operatorMode
      ? [row.operator_name, row.operator_username, row.top_plan_name, row.top_account_name].join(" ").toLowerCase()
      : [row.employee_name, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = operatorMode
    ? [
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
      ${sorted.map((row) => {
        const entityName = breakdownEntityName(row);
        const subline = operatorMode
          ? [row.operator_username ? `账号 ${row.operator_username}` : "", row.top_account_name ? `代表账户 ${row.top_account_name}` : ""].filter(Boolean)
          : [row.top_account_name ? `代表账户 ${row.top_account_name}` : "", row.top_plan_name ? `代表计划 ${row.top_plan_name}` : ""].filter(Boolean);
        return `
          <tr data-employee-name="${escapeHtml(entityName)}" class="${state.selectedEmployeeName === entityName ? "active-row" : ""}">
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
  const query = productSearch.value.trim().toLowerCase();
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
  if (!materialDetail) return;
  materialDetailStage?.classList.add("hidden");
  materialDetail.className = "detail-panel empty";
  materialDetail.textContent = "选中素材后查看补充信息。";
}

function renderMaterialDetail(materialKey) {
  if (!materialDetail) return;
  const rows = materialRangePayload(sectionFilter("material"))?.items || [];
  const row = rows.find((item) => item.material_key === materialKey);
  if (!row) return;
  materialDetailStage?.classList.remove("hidden");
  materialDetail.className = "detail-panel";
  materialDetail.innerHTML = `
    <div class="detail-block-head">
      <h4>${escapeHtml(row.material_name || "素材详情")}</h4>
      <span>补充信息</span>
    </div>
    <div class="detail-inline-actions">
      <button type="button" class="button ghost compact" data-action="open-material-preview" data-material-key="${escapeHtml(row.material_key)}">预览素材</button>
    </div>
    <div class="detail-stats">
      <div class="detail-stat"><span class="label">覆盖账户数</span><span class="value mono">${formatNumber(row.advertiser_count)}</span></div>
      <div class="detail-stat"><span class="label">覆盖计划数</span><span class="value mono">${formatNumber(row.plan_count)}</span></div>
      <div class="detail-stat"><span class="label">首发视频</span><span class="value compact">${row.is_original ? "是" : "否"}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">代表计划</span><span class="value compact">${escapeHtml(row.top_plan_name || "-")}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">代表账户</span><span class="value compact">${escapeHtml(row.top_account_name || "-")}</span></div>
    </div>
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
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const materialKey = String(button.dataset.materialKey || "");
      if (!materialKey) return;
      openMaterialPreview(materialKey);
    });
  });
}

function renderMaterialTable(rows) {
  const operatorMode = isOperator();
  if (
    operatorMode
    && !["material_name", "stat_cost", "top_account_name", "top_plan_name"].includes(String(state.materialSort.key || ""))
  ) {
    state.materialSort = { key: "stat_cost", dir: "desc" };
    saveSort("material-sort", state.materialSort);
  }
  const query = materialSearch.value.trim().toLowerCase();
  const visibleRows = rows.filter((row) => {
    const haystack = [row.material_name, row.material_id, row.video_id, row.top_plan_name, row.top_account_name].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  const columns = operatorMode
    ? [
        { key: "material_name", label: "素材", sortable: true },
        { key: "preview", label: "预览", sortable: false },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "top_account_name", label: "归属账户", sortable: true },
        { key: "top_plan_name", label: "归属计划", sortable: true },
      ]
    : [
        { key: "material_name", label: "素材", sortable: true },
        { key: "preview", label: "预览", sortable: false },
        { key: "stat_cost", label: "消耗", sortable: true },
        { key: "roi", label: "ROI", sortable: true },
        { key: "pay_amount", label: "支付", sortable: true },
        { key: "order_count", label: "订单", sortable: true },
        { key: "top_account_name", label: "归属账户", sortable: true },
        { key: "top_plan_name", label: "归属计划", sortable: true },
        { key: "plan_count", label: "计划数", sortable: true },
        { key: "advertiser_count", label: "账户数", sortable: true },
      ];
  const sorted = sortRows(visibleRows, state.materialSort);
  const supportsMaterialDetail = Boolean(materialDetail);
  materialTable.innerHTML = `
    ${makeHeader(columns, state.materialSort, "material-sort")}
    <tbody>
      ${sorted.map((row) => `
        <tr data-material-key="${escapeHtml(row.material_key)}" class="${supportsMaterialDetail && state.selectedMaterialKey === row.material_key ? "active-row" : ""}">
          <td>
            <div class="cell-primary">${escapeHtml(row.material_name || "未命名素材")}</div>
            <div class="cell-subline mono">
              <span class="cell-subitem" title="素材 ID：${escapeHtml(row.material_id || "-")}">MID ${escapeHtml(truncateMiddle(row.material_id || "-", 8, 6))}</span>
              <span class="cell-subitem" title="视频 ID：${escapeHtml(row.video_id || "-")}">VID ${escapeHtml(truncateMiddle(row.video_id || "-", 8, 6))}</span>
            </div>
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
          <td class="mono">${formatMoney(row.stat_cost)}</td>
          ${operatorMode
            ? `
          <td>${escapeHtml(row.top_account_name || "--")}</td>
          <td>${escapeHtml(row.top_plan_name || "--")}</td>
          `
            : `
          <td class="mono">${formatRate(row.roi)}</td>
          <td class="mono">${formatMoney(row.pay_amount)}</td>
          <td class="mono">${formatNumber(row.order_count)}</td>
          <td>${escapeHtml(row.top_account_name || "--")}</td>
          <td>${escapeHtml(row.top_plan_name || "--")}</td>
          <td class="mono">${formatNumber(row.plan_count)}</td>
          <td class="mono">${formatNumber(row.advertiser_count)}</td>
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
  if (!planAssetSummary) return;
  planAssetSummary.className = "detail-panel empty";
  planAssetSummary.textContent = "选中计划后查看商品和素材摘要。";
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
  if (!planAssetSummary) return;
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
  planDetail.innerHTML = `
    <div class="detail-block-head">
      <h4>${escapeHtml(row.ad_name)}</h4>
      <span>补充信息</span>
    </div>
    <div class="detail-stats detail-stats-plan">
      <div class="detail-stat"><span class="label">计划 ID</span><span class="value compact mono">${formatNumber(row.ad_id)}</span></div>
      <div class="detail-stat"><span class="label">账户</span><span class="value compact">${escapeHtml(row.advertiser_name)}</span></div>
      <div class="detail-stat"><span class="label">商品</span><span class="value compact">${escapeHtml(row.product_name || "-")}</span></div>
      <div class="detail-stat"><span class="label">主播</span><span class="value compact">${escapeHtml(row.anchor_name || "-")}</span></div>
      <div class="detail-stat"><span class="label">营销目标</span><span class="value">${renderMarketingGoalBadge(row)}</span></div>
      <div class="detail-stat"><span class="label">投放状态</span><span class="value">${renderPlanStatusBadge(row)}</span></div>
      <div class="detail-stat"><span class="label">商品 ID</span><span class="value compact mono">${escapeHtml(row.product_id || "-")}</span></div>
      <div class="detail-stat"><span class="label">账户 ID</span><span class="value compact mono">${formatNumber(row.advertiser_id)}</span></div>
      <div class="detail-stat"><span class="label">目标 ROI</span><span class="value mono">${formatRate(row.roi_goal)}</span></div>
      <div class="detail-stat"><span class="label">ROI 差值</span><span class="value mono ${roiGap >= 0 ? "positive" : "negative"}">${roiGap >= 0 ? "+" : ""}${formatRate(roiGap)}</span></div>
      <div class="detail-stat"><span class="label">支付金额</span><span class="value mono">${formatMoney(row.pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">整体成交金额</span><span class="value mono">${formatMoney(row.total_pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">净成交金额</span><span class="value mono">${formatMoney(row.settled_pay_amount)}</span></div>
      <div class="detail-stat"><span class="label">整体支付 ROI</span><span class="value mono">${formatRate(row.roi)}</span></div>
      <div class="detail-stat"><span class="label">净成交 ROI</span><span class="value mono">${formatRate(row.settled_roi)}</span></div>
      <div class="detail-stat"><span class="label">整体成交订单数</span><span class="value mono">${formatNumber(row.order_count)}</span></div>
      <div class="detail-stat"><span class="label">净成交订单数</span><span class="value mono">${formatNumber(row.settled_order_count)}</span></div>
      <div class="detail-stat"><span class="label">整体成交订单成本</span><span class="value mono">${Number(row.order_count || 0) > 0 ? formatMoney(row.pay_order_cost) : "-"}</span></div>
      <div class="detail-stat"><span class="label">净成交金额结算率</span><span class="value mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.settled_amount_rate) : "-"}</span></div>
      <div class="detail-stat"><span class="label">1 小时内退款率</span><span class="value mono">${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}</span></div>
      <div class="detail-stat detail-stat-wide"><span class="label">${escapeHtml(currentRangeLabel)}补充判断</span><span class="value compact">当前区间整体支付 ROI ${formatRate(row.roi)}，整体成交 ${formatMoney(row.total_pay_amount)}，净成交 ${formatMoney(row.settled_pay_amount)}，1 小时内退款率 ${Number(row.total_pay_amount || 0) > 0 ? formatPercent(row.refund_rate_1h) : "-"}。</span></div>
    </div>
  `;
  await renderPlanAssets(adId);
}

function clearPlanDetail() {
  if (!planDetail || !planAssetSummary) return;
  planDetailStage?.classList.add("hidden");
  planDetail.className = "detail-panel empty";
  planDetail.textContent = "选中计划后查看补充信息。";
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
      ${rules.length ? rules.map((rule) => `
        <tr>
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
      `).join("") : '<tr><td colspan="6" class="empty-cell">还没有预警规则，先从账户余额、共享钱包、消耗或爆单规则开始。</td></tr>'}
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

function userScopeSummary(user) {
  if (!user) return "--";
  if (user.role === "admin") return "全部账户";
  if (user.role === "supervisor") return `${formatNumber(user.scope_count || 0)} 个账户`;
  if (user.role === "operator") return "按关键词";
  return "--";
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
  return materialRangePayload(sectionFilter("material"))?.items || [];
}

function selectedMaterialRow(materialKey) {
  return currentMaterialRows().find((item) => item.material_key === materialKey) || null;
}

function canPreviewMaterial(row) {
  if (!row) return false;
  return Boolean(
    String(row.video_url || "").trim()
    || String(row.cover_url || "").trim()
    || materialAwemeLink(row)
  );
}

function materialAwemeLink(row) {
  const awemeId = String(row?.aweme_item_id || "").trim();
  return awemeId ? `https://www.douyin.com/video/${encodeURIComponent(awemeId)}` : "";
}

function closeMaterialPreview() {
  if (!materialPreviewModal) return;
  materialPreviewModal.classList.add("hidden");
  materialPreviewModal.setAttribute("aria-hidden", "true");
  if (materialPreviewBody) materialPreviewBody.innerHTML = "";
}

function openMaterialPreviewFromRow(row) {
  if (!row || !materialPreviewModal || !materialPreviewBody) return;
  const directVideoUrl = String(row.video_url || "").trim();
  const coverUrl = String(row.cover_url || "").trim();
  const awemeLink = materialAwemeLink(row);
  if (materialPreviewTitle) {
    materialPreviewTitle.textContent = row.material_name || "素材预览";
  }
  if (materialPreviewMeta) {
    materialPreviewMeta.textContent = [row.top_account_name || "", row.top_plan_name || ""].filter(Boolean).join(" / ") || "素材预览";
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
  materialPreviewBody.innerHTML = `
    <div class="preview-media-shell">${previewBlock}</div>
    <div class="preview-detail-grid">
      <div class="preview-stat"><span>归属账户</span><strong>${escapeHtml(row.top_account_name || "--")}</strong></div>
      <div class="preview-stat"><span>归属计划</span><strong>${escapeHtml(row.top_plan_name || "--")}</strong></div>
      <div class="preview-stat"><span>消耗</span><strong class="mono">${formatMoney(row.stat_cost)}</strong></div>
      <div class="preview-stat"><span>支付</span><strong class="mono">${formatMoney(row.pay_amount)}</strong></div>
      <div class="preview-stat"><span>订单</span><strong class="mono">${formatNumber(row.order_count)}</strong></div>
      <div class="preview-stat"><span>ROI</span><strong class="mono">${formatRate(row.roi)}</strong></div>
      <div class="preview-stat"><span>覆盖计划</span><strong class="mono">${formatNumber(row.plan_count)}</strong></div>
      <div class="preview-stat"><span>素材 ID</span><strong class="mono">${escapeHtml(row.material_id || "--")}</strong></div>
      <div class="preview-stat"><span>视频 ID</span><strong class="mono">${escapeHtml(row.video_id || "--")}</strong></div>
    </div>
    ${extraActions ? `<div class="preview-actions">${extraActions}</div>` : ""}
  `;
  const previewMediaShell = materialPreviewBody.querySelector(".preview-media-shell");
  const previewVideo = materialPreviewBody.querySelector(".preview-video");
  const previewCover = materialPreviewBody.querySelector(".preview-cover");
  previewVideo?.addEventListener("error", () => {
    if (!previewMediaShell) return;
    previewMediaShell.innerHTML = coverUrl
      ? `
        <img class="preview-cover" src="${escapeHtml(coverUrl)}" alt="${escapeHtml(row.material_name || "素材封面")}" />
        <div class="preview-empty">当前视频地址无法直接播放，已降级为封面预览。</div>
      `
      : '<div class="preview-empty">当前视频地址无法直接播放，请尝试下方入口。</div>';
    const fallbackCover = previewMediaShell.querySelector(".preview-cover");
    fallbackCover?.addEventListener("error", () => {
      previewMediaShell.innerHTML = '<div class="preview-empty">当前素材没有可站外访问的预览地址，请尝试打开抖音作品。</div>';
    }, { once: true });
  }, { once: true });
  previewCover?.addEventListener("error", () => {
    if (!previewMediaShell) return;
    previewMediaShell.innerHTML = '<div class="preview-empty">当前素材没有可站外访问的预览地址，请尝试打开抖音作品。</div>';
  }, { once: true });
  materialPreviewModal.classList.remove("hidden");
  materialPreviewModal.setAttribute("aria-hidden", "false");
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
  const response = await fetch(`/api/users/${userId}/matched-materials?range=day`);
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
    setInlineFeedback(operatorMaterialStatus, "先选运营，再看命中素材。", "neutral");
    renderUserKeywordTable();
    renderUserMatchedMaterialTable();
    return;
  }
  if (isSupervisor) {
    setInlineFeedback(scopeEditorMeta, "主管只看勾选账户；需要时再开上传。", "neutral");
  } else if (isOperator) {
    setInlineFeedback(scopeEditorMeta, "运营不配置账户范围，只看关键词命中结果。", "neutral");
    setInlineFeedback(operatorKeywordStatus, "新建运营时可直接填关键词，也可后续追加。", "neutral");
    setInlineFeedback(operatorMaterialStatus, "只按素材名称关键词命中，默认收起。", "neutral");
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
  const accessTab = viewTabs?.querySelector('[data-view="access"]');
  const signalsTab = viewTabs?.querySelector('[data-view="signals"]');
  const accountTab = viewTabs?.querySelector('[data-view="accounts"]');
  const planTab = viewTabs?.querySelector('[data-view="plans"]');
  const breakdownTab = viewTabs?.querySelector('[data-view="breakdown"]');
  const materialsTab = viewTabs?.querySelector('[data-view="materials"]');
  const uploadsTab = viewTabs?.querySelector('[data-view="uploads"]');
  const tabOrder = admin
    ? ["overview", "accounts", "plans", "materials", "breakdown", "uploads", "access", "signals"]
    : supervisor
      ? (canUseUploadModule()
        ? ["overview", "accounts", "plans", "materials", "breakdown", "uploads"]
        : ["overview", "accounts", "plans", "materials", "breakdown"])
      : ["overview", "materials", "breakdown"];
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
  if (materialSearch) {
    materialSearch.placeholder = operator ? "搜索素材名称" : "搜索素材";
  }
  if (heroCopy) {
    heroCopy.textContent = admin
      ? "账户、计划、素材、运营。"
      : supervisor
        ? "范围内账户、计划、素材。"
        : "我的素材、团队排名。";
  }
  const allowedViews = admin
    ? new Set(["overview", "accounts", "breakdown", "plans", "materials", "uploads", "access", "signals"])
    : supervisor
      ? new Set(canUseUploadModule() ? ["overview", "accounts", "breakdown", "plans", "materials", "uploads"] : ["overview", "accounts", "breakdown", "plans", "materials"])
      : new Set(["overview", "breakdown", "materials"]);
  if (viewTabs) {
    tabOrder.forEach((view) => {
      const tab = viewTabs.querySelector(`[data-view="${view}"]`);
      if (tab) viewTabs.appendChild(tab);
    });
  }
  if (!allowedViews.has(state.activeView)) {
    const fallback = allowedViews.has("overview") ? "overview" : Array.from(allowedViews)[0] || "overview";
    setActiveView(fallback);
  }
  userFormReset && (userFormReset.disabled = !admin);
}

function selectedUserRecord() {
  return state.users.find((item) => Number(item.id) === Number(state.selectedUserId)) || null;
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
  setInlineFeedback(operatorMaterialStatus, "先选运营，再看命中素材。", "neutral");
  setOperatorMaterialVisibility(false);
  renderScopeChecklist();
  renderUserKeywordTable();
  renderUserMatchedMaterialTable();
  syncAccessRolePanels();
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
        <th>数据范围</th>
        <th>关键词</th>
        <th>上传</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
      ${state.users.length ? state.users.map((item) => `
        <tr data-user-id="${item.id}" class="${Number(state.selectedUserId) === Number(item.id) ? "active-row" : ""}">
          <td>${escapeHtml(item.username)}</td>
          <td>${escapeHtml(item.display_name || "--")}</td>
          <td>${escapeHtml(roleLabel(item.role))}</td>
          <td>${escapeHtml(userScopeSummary(item))}</td>
          <td class="mono">${item.role === "operator" ? formatNumber(item.keyword_count || 0) : "--"}</td>
          <td>${item.role === "admin" ? '<span class="pill active">允许</span>' : item.role === "supervisor" ? `<span class="pill ${item.upload_materials_enabled ? "active" : ""}">${item.upload_materials_enabled ? "允许" : "关闭"}</span>` : "--"}</td>
          <td><span class="pill">${item.enabled ? "启用" : "停用"}</span></td>
        </tr>
      `).join("") : '<tr><td colspan="7" class="empty-cell">还没有后台账号。</td></tr>'}
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
  if (user.role === "operator") {
    scopeAccountList.innerHTML = '<div class="empty-cell">运营账号按关键词看数据，这里不配置范围。</div>';
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
    scopeAccountList.querySelector('input[type="checkbox"]')?.focus();
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

async function applyQuickRange(sectionKey, mode) {
  const current = sectionFilter(sectionKey);
  if (current.mode === mode) return;
  setRangeEditorOpen(sectionKey, false);
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
  setRangeEditorOpen(sectionKey, true);
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
  materialPreviewModal?.addEventListener("click", (event) => {
    const trigger = event.target.closest('[data-action="close-preview"]');
    if (trigger) {
      closeMaterialPreview();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && materialPreviewModal && !materialPreviewModal.classList.contains("hidden")) {
      closeMaterialPreview();
    }
  });
  if (viewTabs) {
    viewTabs.querySelectorAll(".view-tab").forEach((button) => {
      button.addEventListener("click", async () => {
        const view = button.dataset.view || "overview";
        setActiveView(view);
        if (view === "materials") {
          await refreshMaterialSection(true);
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
  materialSearch?.addEventListener("input", () => renderMaterialTable(materialRangePayload(sectionFilter("material"))?.items || []));
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
  });

  ruleTargetSearchInput?.addEventListener("input", () => {
    syncRuleTargetSelectionFromSearch();
  });

  ruleTargetSearchInput?.addEventListener("change", () => {
    syncRuleTargetSelectionFromSearch();
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
    const keywordSeeds = parseKeywordSeedInput(form.get("keyword_seed"));
    const payload = {
      username: String(form.get("username") || "").trim(),
      display_name: String(form.get("display_name") || "").trim(),
      role: String(form.get("role") || "operator"),
      password: String(form.get("password") || ""),
      enabled: form.get("enabled") === "on",
      upload_materials_enabled: form.get("upload_materials_enabled") === "on",
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
        scopeAccountList.querySelector('input[type="checkbox"]')?.focus();
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
