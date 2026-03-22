const PUBLIC_RANGE_LABELS = {
  day: "今日",
  week: "近 7 天",
  month: "当月",
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
      </tr>
    </thead>
    <tbody>${rows || '<tr><td colspan="6" class="empty-cell">当前时间范围内暂无数据</td></tr>'}</tbody>
  `;
}

async function refreshPublicView() {
  try {
    const payload = await loadPublicRankings();
    publicRangeMeta.textContent = `统计范围：${payload.range_label || PUBLIC_RANGE_LABELS[publicState.range]} · ${payload.query_start_date || "--"} 至 ${payload.query_end_date || "--"} · 更新于 ${payload.updated_at || "--"}`;
    renderPublicTable(payload.items || []);
  } catch (error) {
    publicRangeMeta.textContent = error.message || "公开榜加载失败";
    publicEmployeeTable.innerHTML = '<tbody><tr><td colspan="6" class="empty-cell">公开榜加载失败</td></tr></tbody>';
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
