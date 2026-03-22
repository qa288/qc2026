const PUBLIC_RANGE_LABELS = {
  day: "今日",
  week: "近 7 天",
  month: "近 30 天",
  custom: "自定义时间段",
};

const publicState = {
  range: "day",
  start: "",
  end: "",
  sortKey: "stat_cost",
  sortDir: "desc",
};

const publicRangeSwitch = document.getElementById("publicRangeSwitch");
const publicDateStart = document.getElementById("publicDateStart");
const publicDateEnd = document.getElementById("publicDateEnd");
const publicDateApply = document.getElementById("publicDateApply");
const publicSortKey = document.getElementById("publicSortKey");
const publicSortDir = document.getElementById("publicSortDir");
const publicRangeMeta = document.getElementById("publicRangeMeta");
const publicEmployeeTable = document.getElementById("publicEmployeeTable");
const publicSummaryStrip = document.getElementById("publicSummaryStrip");

function publicFormatMoney(value) {
  return Number(value || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function publicFormatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function publicFormatRate(value) {
  return Number(value || 0).toFixed(2);
}

function publicDateValue(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function setPresetRange(mode) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  if (mode === "week") {
    start.setDate(start.getDate() - 6);
  } else if (mode === "month") {
    start.setDate(start.getDate() - 29);
  }
  publicState.range = mode;
  publicState.start = publicDateValue(start);
  publicState.end = publicDateValue(today);
  publicDateStart.value = publicState.start;
  publicDateEnd.value = publicState.end;
  syncRangeButtons();
}

function syncRangeButtons() {
  publicRangeSwitch.querySelectorAll(".range-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.range === publicState.range);
  });
  publicSortDir.textContent = publicState.sortDir === "desc" ? "降序" : "升序";
}

async function loadPublicRankings() {
  const params = new URLSearchParams({
    range: publicState.range,
    start_date: publicState.start,
    end_date: publicState.end,
    sort_key: publicState.sortKey,
    sort_dir: publicState.sortDir,
  });
  const response = await fetch(`/api/public/employee-rankings?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "加载失败" }));
    throw new Error(payload.detail || "加载失败");
  }
  return response.json();
}

function renderPublicTable(items) {
  const rows = items
    .map((item, index) => {
      return `
        <tr>
          <td>${index + 1}</td>
          <td>${item.employee_name || "未归属"}</td>
          <td>${publicFormatMoney(item.stat_cost)}</td>
          <td>${publicFormatMoney(item.pay_amount)}</td>
          <td>${publicFormatNumber(item.order_count)}</td>
          <td>${publicFormatRate(item.roi)}</td>
          <td>${publicFormatNumber(item.plan_count || 0)}</td>
          <td>${publicFormatNumber(item.advertiser_count || 0)}</td>
        </tr>
      `;
    })
    .join("");
  publicEmployeeTable.innerHTML = `
    <thead>
      <tr>
        <th>排名</th>
        <th>归属人</th>
        <th>消耗</th>
        <th>支付</th>
        <th>订单</th>
        <th>ROI</th>
        <th>计划数</th>
        <th>账户数</th>
      </tr>
    </thead>
    <tbody>${rows || '<tr><td colspan="8" class="empty-cell">当前时间范围内暂无数据</td></tr>'}</tbody>
  `;
}

function renderPublicSummary(items) {
  if (!publicSummaryStrip) return;
  const top = items[0] || null;
  const totalSpend = items.reduce((sum, item) => sum + Number(item.stat_cost || 0), 0);
  const totalPay = items.reduce((sum, item) => sum + Number(item.pay_amount || 0), 0);
  const totalOrders = items.reduce((sum, item) => sum + Number(item.order_count || 0), 0);
  publicSummaryStrip.innerHTML = `
    <article class="public-summary-card">
      <span>归属人数</span>
      <strong>${publicFormatNumber(items.length)}</strong>
      <small>当前时间范围内进入榜单的人数</small>
    </article>
    <article class="public-summary-card">
      <span>榜首归属人</span>
      <strong>${top?.employee_name || "--"}</strong>
      <small>${top ? `当前消耗 ${publicFormatMoney(top.stat_cost)}` : "等待数据"}</small>
    </article>
    <article class="public-summary-card">
      <span>总消耗</span>
      <strong>${publicFormatMoney(totalSpend)}</strong>
      <small>总支付 ${publicFormatMoney(totalPay)}</small>
    </article>
    <article class="public-summary-card">
      <span>总订单</span>
      <strong>${publicFormatNumber(totalOrders)}</strong>
      <small>按归属人聚合后对比当前区间表现</small>
    </article>
  `;
}

async function refreshPublicView() {
  try {
    const payload = await loadPublicRankings();
    publicRangeMeta.textContent = `统计范围：${payload.range_label || PUBLIC_RANGE_LABELS[publicState.range]} · ${payload.query_start_date || "--"} 至 ${payload.query_end_date || "--"} · 更新于 ${payload.updated_at || "--"}`;
    renderPublicSummary(payload.items || []);
    renderPublicTable(payload.items || []);
  } catch (error) {
    publicRangeMeta.textContent = error.message || "公开榜加载失败";
    if (publicSummaryStrip) {
      publicSummaryStrip.innerHTML = "";
    }
    publicEmployeeTable.innerHTML = '<tbody><tr><td colspan="8" class="empty-cell">公开榜加载失败</td></tr></tbody>';
  }
}

publicRangeSwitch?.addEventListener("click", (event) => {
  const button = event.target.closest(".range-button");
  if (!button) return;
  setPresetRange(button.dataset.range || "day");
  refreshPublicView();
});

publicDateApply?.addEventListener("click", () => {
  if (!publicDateStart.value || !publicDateEnd.value) return;
  publicState.range = "custom";
  publicState.start = publicDateStart.value;
  publicState.end = publicDateEnd.value;
  syncRangeButtons();
  refreshPublicView();
});

publicSortKey?.addEventListener("change", () => {
  publicState.sortKey = publicSortKey.value || "stat_cost";
  refreshPublicView();
});

publicSortDir?.addEventListener("click", () => {
  publicState.sortDir = publicState.sortDir === "desc" ? "asc" : "desc";
  syncRangeButtons();
  refreshPublicView();
});

setPresetRange("day");
refreshPublicView();
setInterval(refreshPublicView, 60_000);
