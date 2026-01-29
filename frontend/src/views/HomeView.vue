
<template>
  <section class="home">
    <header class="home-header">
      <div class="logo-orb"></div>
      <div>
        <h1>实时金融量化中枢</h1>
        <p>接入后端 AkShare 指数行情与多源新闻，为后续智能体分析提供底层数据。</p>
      </div>
    </header>

    <div class="home-main">
      <aside class="home-sidebar" ref="sidebarEl">
        <div class="sidebar-fixed">
          <h2>核心指数雷达</h2>
          <p class="hint">数据来源：AkShare / 东方财富 / 新浪指数接口。</p>
          <button
            class="refresh-btn"
            type="button"
            :disabled="loading"
            @click="loadSnapshot"
          >
            {{ loading ? "刷新中..." : "刷新指数快照" }}
          </button>
          <div class="as-of" v-if="snapshot">
            截止时间：{{ formatTime(snapshot.as_of) }}
          </div>
        </div>

        <div class="sidebar-scroll">
          <ul class="index-list">
            <li
              v-for="idx in indices"
              :key="idx.code"
              class="index-card"
              :data-bias="idx.change_pct"
            >
              <div class="idx-header">
                <span class="code">{{ idx.code }}</span>
                <span class="name">{{ idx.name }}</span>
              </div>
              <div class="idx-body">
                <div class="price">
                  <span class="label">最新价</span>
                  <span class="value">{{ formatNumber(idx.last) }}</span>
                </div>
                <div class="change" :class="{ up: idx.change_pct > 0, down: idx.change_pct < 0 }">
                  <span class="label">涨跌幅</span>
                  <span class="value">
                    <span v-if="idx.change_pct === null">--</span>
                    <span v-else>{{ idx.change_pct.toFixed(2) }}%</span>
                  </span>
                </div>
              </div>
              <div class="idx-footer">
                <span>最高: {{ formatNumber(idx.high) }}</span>
                <span>最低: {{ formatNumber(idx.low) }}</span>
              </div>
            </li>
          </ul>
        </div>
      </aside>

      <section class="home-right" ref="rightColEl">
        <div class="panel glass">
          <h2>今日市场扫描</h2>
          <p class="hint">
            在「Agent 分析」页面，你可以基于这些行情发起自然语言提问，或上传 PDF / Excel 进行组合分析。
          </p>
          <ul class="scan-list">
            <li v-for="idx in indices" :key="idx.code" class="scan-item">
              <span class="dot"></span>
              <span class="text">
                {{ idx.name }}（{{ idx.code }}）
                <span v-if="idx.change_pct !== null">
                  今日 {{ idx.change_pct > 0 ? "上涨" : idx.change_pct < 0 ? "下跌" : "基本持平" }}
                  {{ Math.abs(idx.change_pct).toFixed(2) }}%
                </span>
                <span v-else>暂无实时涨跌幅数据</span>
              </span>
            </li>
            <li v-if="!indices.length" class="scan-item empty">
              <span class="dot"></span>
              <span class="text">暂未获取到指数数据，请点击左侧“刷新指数快照”。</span>
            </li>
          </ul>
        </div>

        <!-- 股票搜索与折线图（移至右侧“今日市场扫描”下方） -->
        <section class="panel glass">
          <h2>股票搜索与行情</h2>
          <p class="hint">输入公司关键词或股票代码，选择后查看近况折线图。</p>
          <div class="stock-search">
            <div class="search-row">
              <input
                type="text"
                class="search-input"
                v-model="searchQuery"
                placeholder="例如：茅台 或 600519 / AAPL"
                @input="onSearchInput"
                @focus="onSearchFocus"
                @blur="onSearchBlur"
                @keydown.enter="onEnter"
              />
              <div class="chart-controls inline">
                <label class="control">
                  <span>时间范围</span>
                  <select v-model.number="selectedDays" @change="onDaysChange" :disabled="chartLoading">
                    <option v-for="d in DAY_OPTIONS" :key="d" :value="d">近 {{ d }} 天</option>
                  </select>
                </label>
              </div>
            </div>
            <ul v-if="showSuggestions" class="suggest-list" @mousedown.prevent>
              <li v-if="!searchQuery" class="suggest-header">
                <span>最近搜索</span>
                <button
                  v-if="recentSearches.length"
                  type="button"
                  class="clear-recent"
                  @mousedown.prevent
                  @click="clearRecentSearches"
                >清空最近搜索</button>
              </li>
              <li
                v-for="item in suggestions"
                :key="item.symbol"
                class="suggest-item"
                @click="selectSuggestion(item)"
              >
                <span class="suggest-name">{{ item.name }}</span>
                <span class="suggest-code">{{ item.code || item.symbol }}</span>
                <span class="suggest-market">{{ item.market || "" }}</span>
              </li>
              <li v-if="!suggestions.length && searchQuery" class="suggest-item empty">无匹配结果</li>
              <li v-if="!suggestions.length && !searchQuery" class="suggest-item empty">暂无最近搜索记录</li>
            </ul>
          </div>

          <div class="chart-wrap" v-if="chartPoints.length">
            <canvas ref="chartEl" height="120"></canvas>
          </div>
          <div v-else class="hint">
            {{
              chartLoading
                ? "行情加载中..."
                : selectedSymbol
                  ? "未获取到行情数据，请稍后重试或换个代码。"
                  : "请选择一只股票查看折线图。"
            }}
          </div>
        </section>

        <div class="panel secondary">
          <h2>下一步：进入 Agent 工作台</h2>
          <p class="hint">
            在上方导航中切换到「AI 智能分析」，即可与 Agent 进行对话，查看任务规划时间线，并上传文件。
          </p>
          <p class="hint">
            Agent 会自动调用：AkShare 接口 + 新闻抓取工具 + PDF/Excel 解析工具，为你生成结构化分析报告。
          </p>
        </div>
      </section>

      
    </div>

    <div class="bg-grid"></div>
  </section>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from "vue";
import { searchStocks, getStockHistory } from "../api/stocks";
import Chart from "chart.js/auto";

const snapshot = ref(null);
const indices = ref([]);
const loading = ref(false);
const DAY_OPTIONS = [30, 90, 180, 365];

// 搜索与图表状态
const searchQuery = ref("");
const suggestions = ref([]);
const recentSearches = ref([]);
const showSuggestions = ref(false);
const selectedSymbol = ref("");
const selectedDays = ref(90);
const chartPoints = ref([]);
const chartEl = ref(null);
let chartInstance = null;
let searchTimer = null;
const historySource = ref("");
const chartLoading = ref(false);
const isFocused = ref(false);
const lastSuggestionQuery = ref("");
const lastSuggestions = ref([]);

// 同步左侧高度
const sidebarEl = ref(null);
const rightColEl = ref(null);
let rightResizeObs = null;

function syncSidebarHeight() {
  const sidebar = sidebarEl.value;
  const right = rightColEl.value;
  if (!sidebar) return;
  const isSingleColumn = window.matchMedia("(max-width: 900px)").matches;
  if (isSingleColumn || !right) {
    sidebar.style.height = "auto";
    return;
  }
  // 同步为右侧列总高度
  sidebar.style.height = right.offsetHeight + "px";
}

function prefixCnSymbol(code) {
  const s = String(code || "").trim();
  if (!s) return s;
  const low = s.toLowerCase();
  if (low.startsWith("sh") || low.startsWith("sz")) return low;
  if (/^\d{6}$/.test(s)) {
    if (/^[023]/.test(s)) return `sz${s}`;
    if (/^6/.test(s)) return `sh${s}`;
  }
  return s;
}

function formatTime(t) {
  if (!t) return "";
  try {
    const d = new Date(t);
    return d.toLocaleString();
  } catch {
    return t;
  }
}

function formatNumber(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toFixed(2);
}

function inferCurrency(sym, source) {
  const s = String(sym || "").toUpperCase().trim();
  const fallback = source === "yfinance" ? "USD" : "CNY";
  if (!s) return fallback;

  // 港股：8 开头为人民币柜台，其余为港币柜台
  if (s.endsWith(".HK") || /^\d{4,5}$/.test(s)) {
    const codePart = s.endsWith(".HK") ? s.slice(0, -3) : s;
    return codePart.startsWith("8") ? "CNY" : "HKD";
  }

  // A 股
  if (s.startsWith("SH") || s.startsWith("SZ") || /^\d{6}$/.test(s)) return "CNY";

  // 其他（美股等）
  if (/^[A-Z0-9.:-]+$/.test(s)) return "USD";

  return fallback;
}

async function loadSnapshot() {
  loading.value = true;
  try {
    const resp = await fetch("http://localhost:8000/api/akshare/index_snapshot");
    if (!resp.ok) {
      throw new Error("后端 AkShare 接口请求失败");
    }
    const data = await resp.json();
    snapshot.value = data;
    indices.value = data.indices || [];
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadSnapshot();
  try {
    const saved = localStorage.getItem("recentStocks");
    if (saved) {
      const arr = JSON.parse(saved);
      if (Array.isArray(arr)) {
        recentSearches.value = arr;
      }
    }
  } catch {}

  // 观察右侧列高度变化（图表渲染、数据刷新等）并同步左侧
  try {
    if (rightColEl.value && typeof ResizeObserver !== "undefined") {
      rightResizeObs = new ResizeObserver(() => syncSidebarHeight());
      rightResizeObs.observe(rightColEl.value);
    }
  } catch {}
  window.addEventListener("resize", syncSidebarHeight);
  // 初次同步
  nextTick(() => syncSidebarHeight());
});

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
  try {
    if (rightResizeObs) {
      rightResizeObs.disconnect();
      rightResizeObs = null;
    }
  } catch {}
  window.removeEventListener("resize", syncSidebarHeight);
});

function onSearchInput() {
  const q = searchQuery.value.trim();
  if (!q) {
    // 展示最近搜索
    suggestions.value = [...recentSearches.value];
    // 即便没有最近搜索也展示空态
    showSuggestions.value = isFocused.value;
    return;
  }
  showSuggestions.value = true;
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const results = await computeSuggestionsForQuery(q);
    suggestions.value = results;
    lastSuggestionQuery.value = q;
    lastSuggestions.value = results;
  }, 200);
}

function onSearchFocus() {
  isFocused.value = true;
  const q = searchQuery.value.trim();
  // 若已有查询内容，优先展示该内容的联想缓存，不做网络更新
  if (q) {
    if (lastSuggestionQuery.value === q && lastSuggestions.value.length) {
      suggestions.value = [...lastSuggestions.value];
      showSuggestions.value = true;
    } else {
      // 无缓存则保持现状，不主动更新
      showSuggestions.value = !!suggestions.value.length;
    }
  } else {
    // 输入为空时展示最近搜索
    suggestions.value = [...recentSearches.value];
    // 即便为空也展示空态
    showSuggestions.value = true;
  }
}

function onSearchBlur() {
  // 延迟隐藏以支持点击候选项
  setTimeout(() => {
    isFocused.value = false;
    showSuggestions.value = false;
  }, 150);
}

function addRecent(item) {
  try {
    const key = String(item.symbol || item.code || "").toUpperCase();
    if (!key) return;
    recentSearches.value = [
      { symbol: key, code: item.code || key, name: item.name || key, market: item.market || "" },
      ...recentSearches.value.filter((x) => String(x.symbol || x.code).toUpperCase() !== key),
    ].slice(0, 8);
    localStorage.setItem("recentStocks", JSON.stringify(recentSearches.value));
  } catch {}
}

async function selectSuggestion(item) {
  showSuggestions.value = false;
  searchQuery.value = item.name || item.symbol;
  selectedSymbol.value = item.symbol || item.code;
  addRecent(item);
  // 内容已变更：预先计算该内容的联想供下次聚焦使用（不立刻展示）
  try {
    const q = searchQuery.value.trim();
    if (q) {
      const results = await computeSuggestionsForQuery(q);
      lastSuggestionQuery.value = q;
      lastSuggestions.value = results;
    }
  } catch {}
  await loadHistory(selectedSymbol.value, selectedDays.value);
}

function clearRecentSearches() {
  try {
    recentSearches.value = [];
    localStorage.removeItem("recentStocks");
    // 若当前聚焦且输入为空，保持下拉展示为空态
    if (isFocused.value && !searchQuery.value.trim()) {
      suggestions.value = [];
      showSuggestions.value = true;
    }
  } catch {}
}

async function onEnter() {
  const q = searchQuery.value.trim();
  if (!q) return;
  if (suggestions.value.length) {
    await selectSuggestion(suggestions.value[0]);
    return;
  }
  // 无建议时，尝试直接按代码加载（美股/港股常用）
  if (/^[A-Za-z0-9.:-]+$/.test(q)) {
    selectedSymbol.value = q.toUpperCase();
    // 记录到最近搜索，尽可能推断市场
    const up = selectedSymbol.value;
    const digits = up.replace(/\D/g, "");
    let market = "us";
    if (/^\d{6}$/.test(up) || up.toLowerCase().startsWith("sh") || up.toLowerCase().startsWith("sz")) {
      market = "cn";
    } else if (up.endsWith(".HK") || (/^\d{4,5}$/.test(up))) {
      market = "hk";
    }
    addRecent({ symbol: up, code: up, name: up, market });
    await loadHistory(selectedSymbol.value, selectedDays.value);
  }
}

async function computeSuggestionsForQuery(q) {
  try {
    // 优先请求后端搜索（包括 6 位 A 股代码），若无结果再回退到本地前缀候选
    const results = await searchStocks(q, 8);
    if (results.length) return results;

    // 回退逻辑：识别常见代码形态
    if (/^\d{6}$/.test(q)) {
      const sym = prefixCnSymbol(q);
      return [{ symbol: sym, code: q, name: q, market: "cn" }];
    }
    if (/^[A-Za-z0-9.:-]+$/.test(q)) {
      return [{ symbol: q.toUpperCase(), code: q.toUpperCase(), name: q.toUpperCase(), market: "us" }];
    }
    return [];
  } catch (e) {
    console.error(e);
    return [];
  }
}

async function onDaysChange() {
  if (!selectedSymbol.value) return;
  await loadHistory(selectedSymbol.value, selectedDays.value);
}

async function loadHistory(symbol, days = selectedDays.value) {
  try {
    chartLoading.value = true;
    const data = await getStockHistory(symbol, days);
    chartPoints.value = data.points || [];
    historySource.value = data.source || "";
    if (data.symbol) {
      selectedSymbol.value = data.symbol;
    }
    await nextTick();
    drawChart();
  } catch (e) {
    console.error(e);
    chartPoints.value = [];
  } finally {
    chartLoading.value = false;
  }
}

function drawChart() {
  if (!chartEl.value) return;

  const labels = chartPoints.value.map(p => p.date);
  const values = chartPoints.value.map(p => p.close);
  const currency = inferCurrency(selectedSymbol.value, historySource.value);
  const data = {
    labels,
    datasets: [
      {
        label: selectedSymbol.value || "Close",
        data: values,
        borderColor: "#60a5fa",
        backgroundColor: "rgba(96,165,250,0.2)",
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHitRadius: 12,
      },
    ],
  };
  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      mode: "nearest",
      intersect: false,
      axis: "x",
    },
    scales: {
      x: {
        ticks: { color: "#9ca3af" },
        grid: { color: "rgba(55,65,81,0.2)" },
        title: {
          display: true,
          text: "日期",
          color: "#e5e7eb",
        },
      },
      y: {
        ticks: { color: "#9ca3af" },
        grid: { color: "rgba(55,65,81,0.2)" },
        title: {
          display: true,
          text: `收盘价 (${currency})`,
          color: "#e5e7eb",
        },
      },
    },
    plugins: {
      legend: { labels: { color: "#e5e7eb" } },
      tooltip: { enabled: true, intersect: false, mode: "index" },
    },
    elements: {
      point: {
        radius: 0,
        hoverRadius: 4,
        hitRadius: 12,
      },
    },
  };
  if (chartInstance) chartInstance.destroy();
  chartInstance = new Chart(chartEl.value.getContext("2d"), { type: "line", data, options });
}
</script>

<style scoped>
.home {
  position: relative;
  min-height: 100vh;
  padding: 32px 40px;
  background: radial-gradient(circle at top, #0f172a 0, #020617 45%, #000 100%);
  color: #e5e7eb;
  overflow: hidden;
}

.bg-grid {
  position: fixed;
  inset: 0;
  background-image: linear-gradient(rgba(31, 41, 55, 0.35) 1px, transparent 1px),
    linear-gradient(90deg, rgba(31, 41, 55, 0.35) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.3;
  pointer-events: none;
  mask-image: radial-gradient(circle at center, black 0, transparent 70%);
}

.home-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  position: relative;
  z-index: 1;
}

.logo-orb {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  background:
    radial-gradient(circle at 30% 20%, #38bdf8, transparent 55%),
    radial-gradient(circle at 70% 80%, #4f46e5, transparent 55%);
  box-shadow: 0 0 30px rgba(56, 189, 248, 0.7);
}

.home-header h1 {
  font-size: 26px;
  margin: 0 0 4px;
}

.home-header p {
  margin: 0;
  font-size: 13px;
  color: #9ca3af;
}

.home-main {
  display: grid;
  grid-template-columns: 330px minmax(0, 1fr);
  gap: 18px;
  position: relative;
  z-index: 1;
  align-items: stretch; /* 使同一行的两列在高度上对齐 */
}

/* 左侧指数面板 */

.home-sidebar {
  border-radius: 18px;
  padding: 16px 14px;
  background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.25), #020617);
  border: 1px solid rgba(148, 163, 184, 0.3);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(20px);
  height: 100%; /* 跟随右侧整体高度 */
  display: flex;
  flex-direction: column;
  overflow: hidden; /* 自身不滚动，交由内部滚动区域 */
}

.sidebar-fixed {
  flex: 0 0 auto;
}

.sidebar-scroll {
  flex: 1 1 auto;
  min-height: 0; /* 允许在 flex 容器中正确滚动 */
  overflow: auto;
}

.home-sidebar h2 {
  font-size: 15px;
  margin: 0 0 4px;
}

.hint {
  font-size: 12px;
  color: #9ca3af;
  margin: 2px 0 10px;
}

.refresh-btn {
  border-radius: 999px;
  border: 1px solid #4b5563;
  background: linear-gradient(135deg, #0f172a, #020617);
  color: #e5e7eb;
  font-size: 12px;
  padding: 6px 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.refresh-btn:hover {
  border-color: #38bdf8;
  box-shadow: 0 12px 30px rgba(56, 189, 248, 0.35);
  transform: translateY(-1px);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: default;
  transform: none;
  box-shadow: none;
}

.as-of {
  margin-top: 8px;
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.index-list {
  list-style: none;
  padding: 0;
  margin: 12px 0 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.index-card {
  position: relative;
  border-radius: 14px;
  padding: 10px 10px 8px;
  background: radial-gradient(circle at top, rgba(15, 23, 42, 0.85), #020617);
  border: 1px solid rgba(31, 41, 55, 0.9);
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.85);
  overflow: hidden;
}

.index-card::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at top right, rgba(56, 189, 248, 0.35), transparent 60%);
  opacity: 0.15;
  pointer-events: none;
}

.idx-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
}

.code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New",
    monospace;
  color: #a5b4fc;
}

.name {
  color: #e5e7eb;
}

.idx-body {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 4px;
}

.price .label,
.change .label {
  display: block;
  color: #9ca3af;
  font-size: 10px;
}

.price .value,
.change .value {
  font-size: 14px;
}

.change.up .value {
  color: #4ade80;
}

.change.down .value {
  color: #f97373;
}

.idx-footer {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #9ca3af;
}

/* 右侧说明面板 */

.home-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel {
  border-radius: 18px;
  padding: 14px 16px;
}

.panel.glass {
  background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.32), rgba(15, 23, 42, 0.92));
  border: 1px solid rgba(148, 163, 184, 0.4);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(26px);
}

.panel.secondary {
  background: radial-gradient(circle at bottom right, rgba(56, 189, 248, 0.1), #020617);
  border: 1px solid rgba(55, 65, 81, 0.9);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.9);
}

.panel h2 {
  font-size: 16px;
  margin: 0 0 6px;
}

.stock-search {
  position: relative;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.search-input {
  width: 100%;
  border-radius: 10px;
  border: 1px solid #374151;
  background: rgba(2, 6, 23, 0.8);
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
}

.chart-controls.inline {
  margin: 0;
}

.suggest-list {
  position: absolute;
  z-index: 10;
  margin: 6px 0 0;
  padding: 6px;
  width: 100%;
  list-style: none;
  background: radial-gradient(circle at top, rgba(15, 23, 42, 0.95), #020617);
  border: 1px solid rgba(55, 65, 81, 0.8);
  border-radius: 12px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.9);
}

.suggest-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 6px 4px;
  font-size: 12px;
  color: #9ca3af;
}

.clear-recent {
  border: none;
  background: transparent;
  color: #93c5fd;
  font-size: 12px;
  padding: 0;
  cursor: pointer;
}

.clear-recent:hover {
  color: #bfdbfe;
  text-decoration: underline;
}

.suggest-item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 6px;
  font-size: 12px;
  cursor: pointer;
  color: #e5e7eb;
}

.suggest-item:hover {
  background: rgba(2, 6, 23, 0.7);
}

.suggest-item.empty {
  color: #9ca3af;
  cursor: default;
}

.suggest-name { flex: 1; }
.suggest-code { color: #a5b4fc; }
.suggest-market { color: #9ca3af; }

.chart-wrap {
  position: relative;
  height: 220px;
  margin-top: 10px;
}

.chart-controls {
  display: flex;
  justify-content: flex-end;
  margin: 8px 0 6px;
}

.chart-controls .control {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: 13px;
}

.chart-controls .control span {
  white-space: nowrap;
}

.chart-controls select {
  background: #0b1220;
  color: #e5e7eb;
  border: 1px solid #1f2937;
  border-radius: 8px;
  padding: 6px 10px;
  outline: none;
}

.scan-list {
  list-style: none;
  padding: 0;
  margin: 10px 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.scan-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.scan-item.empty {
  color: #9ca3af;
}

.dot {
  margin-top: 5px;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: radial-gradient(circle at center, #22d3ee, transparent);
  box-shadow: 0 0 12px rgba(45, 212, 191, 0.8);
}

.text {
  flex: 1;
}

/* 响应式 */

@media (max-width: 900px) {
  .home {
    padding: 20px 16px 32px;
  }
  .home-main {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
