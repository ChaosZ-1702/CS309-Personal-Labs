<template>
  <section class="upload">
    <header class="upload-header">
      <h1>报表解析与上传</h1>
      <p>上传 PDF / Excel 财务报表，由后端 Agent 自动进行解析与指标提取。</p>
      <p class="privacy-tip" v-if="privacyMode">
        当前已开启 <strong>隐私模式</strong>：上传将以 store=false 发送到后端，且本地不会保存历史记录。
      </p>
    </header>

    <div class="upload-body">
      <!-- PDF CARD -->
      <div class="card">
        <h2>上传 PDF 报表</h2>
        <p class="hint">支持多份不同格式的 PDF 财务报表，后端会进行统一解析。</p>

        <div class="action-row">
          <input class="file-input" type="file" accept="application/pdf" @change="onPdfChange" />
          <button
            type="button"
            class="btn"
            :disabled="!pdfFile || loadingPdf"
            @click="handleUploadPdf"
          >
            {{ loadingPdf ? "解析中..." : "上传并解析 PDF" }}
          </button>
        </div>
        <p v-if="pdfError" class="error">{{ pdfError }}</p>

        <div v-if="pdfResult" class="result">
          <h3>解析结果（PDF）</h3>
          <pre class="json-block">{{ prettyJson(pdfResult) }}</pre>

          <div v-if="pdfMeta" class="meta-area">
            <h4>抽取信息</h4>
            <pre class="json-block">{{ prettyJson(pdfMeta) }}</pre>
          </div>

          <div class="chart-area">
            <h4>图表预览</h4>
            <div v-if="pdfCharts && pdfCharts.length" class="chart-wrapper">
              <div v-for="(chart, idx) in pdfCharts" :key="idx" class="chart-card">
                <h5>{{ chart.name }}</h5>
                <img
                  class="chart-img"
                  :alt="chart.name"
                  :src="'data:image/png;base64,' + chart.image_base64"
                  @click="openChartPreview(chart)"
                />
              </div>
            </div>
            <p v-else class="no-chart-msg">
              未能从报表中识别到可视化所需的数值型指标，因此暂未生成图表。
            </p>
          </div>

          <div v-if="pdfAnalysis" class="analysis-area">
            <h4>LLM 解读</h4>
            <div class="analysis-block" v-html="pdfAnalysisHtml"></div>
          </div>
        </div>

        <!-- ✅ PDF 本地历史 -->
        <HistoryPanel
          title="PDF 解析历史（本地）"
          :items="pdfHistory"
          emptyText="暂无 PDF 解析历史（隐私模式开启时不会保存）。"
          @restore="restorePdf"
          @remove="removeUploadRecord"
        />
      </div>

      <!-- EXCEL CARD -->
      <div class="card">
        <h2>上传 Excel 报表</h2>
        <p class="hint">
          支持 Excel 表格读取与数据抽取，可用于仓位统计、收益率计算等。
        </p>

        <div class="action-row">
          <input
            class="file-input"
            type="file"
            accept=".xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            @change="onExcelChange"
          />
          <button
            type="button"
            class="btn"
            :disabled="!excelFile || loadingExcel"
            @click="handleUploadExcel"
          >
            {{ loadingExcel ? "解析中..." : "上传并解析 Excel" }}
          </button>
        </div>
        <p v-if="excelError" class="error">{{ excelError }}</p>

        <div v-if="excelResult" class="result">
          <h3>解析结果（Excel）</h3>
          <pre class="json-block">{{ prettyJson(excelResult) }}</pre>

          <div v-if="excelMeta" class="meta-area">
            <h4>抽取信息</h4>
            <pre class="json-block">{{ prettyJson(excelMeta) }}</pre>
          </div>

          <div class="chart-area">
            <h4>图表预览</h4>
            <div v-if="excelCharts && excelCharts.length" class="chart-wrapper">
              <div v-for="(chart, idx) in excelCharts" :key="idx" class="chart-card">
                <h5>{{ chart.name }}</h5>
                <img
                  class="chart-img"
                  :alt="chart.name"
                  :src="'data:image/png;base64,' + chart.image_base64"
                  @click="openChartPreview(chart)"
                />
              </div>
            </div>
            <p v-else class="no-chart-msg">
              未能从报表中识别到可视化所需的数值型指标，因此暂未生成图表。
            </p>
          </div>

          <div v-if="excelAnalysis" class="analysis-area">
            <h4>LLM 解读</h4>
            <div class="analysis-block" v-html="excelAnalysisHtml"></div>
          </div>
        </div>

        <!-- ✅ Excel 本地历史 -->
        <HistoryPanel
          title="Excel 解析历史（本地）"
          :items="excelHistory"
          emptyText="暂无 Excel 解析历史（隐私模式开启时不会保存）。"
          @restore="restoreExcel"
          @remove="removeUploadRecord"
        />
      </div>
    </div>
  </section>

  <!-- 预览层（与主模板同属一个 template，避免重复模板错误） -->
  <div v-if="showPreview" class="lightbox" @click.self="closePreview">
    <div class="lightbox-body">
      <header class="lightbox-header">
        <h3>{{ previewTitle }}</h3>
        <button class="lightbox-close" type="button" @click="closePreview">×</button>
      </header>
      <div class="lightbox-content">
        <img class="lightbox-img" :src="previewSrc" :alt="previewTitle" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { marked } from "marked";
import HistoryPanel from "../components/HistoryPanel.vue";
import { uploadPdf, uploadExcel } from "../api/upload";

import { getCurrentUser } from "../auth/localAuth";
import {
  getPrivacyMode,
  listUploadRecords,
  appendUploadRecord,
  deleteUploadRecord,
  onLocalHistoryChanged,
  offLocalHistoryChanged
} from "../store/localHistory";

// 这个页面自己独立的会话 ID，用于后端记录解析步骤（不涉及本地历史的 key）
const sessionId = ref(`upload-session-${Date.now()}`);

const username = computed(() => getCurrentUser());

// ✅ tick 用来让 computed 在 localStorage 更新后重新计算
const tick = ref(0);
function bump() {
  tick.value++;
}

onMounted(() => {
  onLocalHistoryChanged(bump);
});

onBeforeUnmount(() => {
  offLocalHistoryChanged(bump);
});


const privacyMode = computed(() => getPrivacyMode(username.value));

// --- PDF ---
const pdfFile = ref(null);
const pdfResult = ref(null);
const pdfCharts = computed(() => (pdfResult.value && pdfResult.value.metrics && pdfResult.value.metrics._charts) || []);
const pdfAnalysis = computed(() => (pdfResult.value && pdfResult.value.metrics && pdfResult.value.metrics._llm_analysis) || "");
const pdfMeta = computed(() => (pdfResult.value && pdfResult.value.metrics && pdfResult.value.metrics._extract_meta) || null);
const pdfError = ref("");
const loadingPdf = ref(false);

// --- EXCEL ---
const excelFile = ref(null);
const excelResult = ref(null);
const excelError = ref("");
const loadingExcel = ref(false);
const excelCharts = computed(() => (excelResult.value && excelResult.value.metrics && excelResult.value.metrics._charts) || []);
const excelAnalysis = computed(() => (excelResult.value && excelResult.value.metrics && excelResult.value.metrics._llm_analysis) || "");
const excelMeta = computed(() => (excelResult.value && excelResult.value.metrics && excelResult.value.metrics._extract_meta) || null);

const showPreview = ref(false);
const previewSrc = ref("");
const previewTitle = ref("");

// ✅ 本地历史（按用户隔离）
const pdfHistory = computed(() => {
  tick.value; // ✅ 依赖 tick，tick 变了就重算
  return listUploadRecords(username.value, "pdf");
});

const excelHistory = computed(() => {
  tick.value;
  return listUploadRecords(username.value, "excel");
});


const pdfAnalysisHtml = computed(() => {
  try {
    return marked.parse(pdfAnalysis.value || "");
  } catch {
    return pdfAnalysis.value || "";
  }
});

const excelAnalysisHtml = computed(() => {
  try {
    return marked.parse(excelAnalysis.value || "");
  } catch {
    return excelAnalysis.value || "";
  }
});

function prettyJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function onPdfChange(e) {
  const f = e?.target?.files?.[0];
  pdfFile.value = f || null;
}

function onExcelChange(e) {
  const f = e?.target?.files?.[0];
  excelFile.value = f || null;
}

async function handleUploadPdf() {
  if (!pdfFile.value) return;
  loadingPdf.value = true;
  pdfError.value = "";
  pdfResult.value = null;
  try {
    const data = await uploadPdf({
      sessionId: sessionId.value,
      file: pdfFile.value,
      store: !privacyMode.value
    });
    pdfResult.value = data;

    // ✅ 保存本地历史（隐私模式开启时 append 会自动跳过）
    appendUploadRecord(username.value, {
      type: "pdf",
      filename: data.filename,
      metrics: data.metrics,
      result: data
    });
  } catch (e) {
    console.error(e);
    pdfError.value = e.message || "上传解析 PDF 失败，请稍后重试。";
  } finally {
    loadingPdf.value = false;
  }
}

async function handleUploadExcel() {
  if (!excelFile.value) return;
  loadingExcel.value = true;
  excelError.value = "";
  excelResult.value = null;
  try {
    const data = await uploadExcel({
      sessionId: sessionId.value,
      file: excelFile.value,
      store: !privacyMode.value
    });
    excelResult.value = data;

    appendUploadRecord(username.value, {
      type: "excel",
      filename: data.filename,
      metrics: data.metrics,
      result: data
    });
  } catch (e) {
    console.error(e);
    excelError.value = e.message || "上传解析 Excel 失败，请稍后重试。";
  } finally {
    loadingExcel.value = false;
  }
}

function restorePdf(item) {
  const data =
    item.result ||
    {
      session_id: sessionId.value,
      filename: item.filename,
      metrics: item.metrics,
      steps: []
    };
  pdfResult.value = data;
}

function restoreExcel(item) {
  const data =
    item.result ||
    {
      session_id: sessionId.value,
      filename: item.filename,
      metrics: item.metrics,
      steps: []
    };
  excelResult.value = data;
}

function removeUploadRecord(item) {
  if (!item || !item.id) return;
  deleteUploadRecord(username.value, item.id);
}

function openChartPreview(chart) {
  try {
    previewSrc.value = "data:image/png;base64," + (chart?.image_base64 || "");
    previewTitle.value = chart?.name || "图表预览";
    if (previewSrc.value) {
      showPreview.value = true;
    }
  } catch {}
}

function closePreview() {
  showPreview.value = false;
  previewSrc.value = "";
  previewTitle.value = "";
}
</script>

<style scoped>
.upload {
  padding: 32px 40px; /* 与 AgentView 保持一致的左右内边距 */
}
.upload-header h1 {
  font-size: 26px;
  margin-bottom: 4px;
}

.upload-header p {
  font-size: 13px;
  color: #9ca3af;
}

.upload-body {
  margin: 12px auto 0; /* 顶部间距 + 横向居中 */
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.card {
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
}

.card h2 {
  font-size: 16px;
  margin-bottom: 4px;
}

.hint {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.72);
  margin-bottom: 8px;
}

input[type="file"] {
  display: block;
  margin: 6px 0 8px;
  font-size: 12px;
  color: #e5e7eb;
  width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 行内布局：选择文件 + 上传并解析 按钮同排，按钮靠右 */
.action-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.action-row .btn {
  margin-left: auto; /* 推到右侧 */
}
.action-row .file-input {
  flex: 1;
  min-width: 0;
}
.action-row input[type="file"] {
  width: auto;     /* 覆盖原本 100% 宽度 */
  margin: 0;       /* 行内去掉额外上下边距 */
}

.btn {
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  padding: 8px 14px;
  font-size: 12px;
  cursor: pointer;
  background: rgba(30, 41, 59, 0.7);
  color: #e5e7eb;
  transition: 0.15s ease;
}

.btn:hover {
  background: rgba(56, 189, 248, 0.18);
  border-color: rgba(56, 189, 248, 0.4);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error {
  margin-top: 8px;
  font-size: 12px;
  color: #fb7185;
}

.result {
  margin-top: 12px;
  border-top: 1px dashed rgba(148, 163, 184, 0.25);
  padding-top: 12px;
}

.json-block {
  margin-top: 8px;
  background: rgba(2, 6, 23, 0.8);
  border-radius: 12px;
  padding: 12px;
  font-size: 12px;
  /* 超过一定高度后可滚动，避免撑开卡片 */
  max-height: 38vh;
  overflow: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  line-height: 1.5;
}

@media (max-width: 640px) {
  .json-block {
    max-height: 50vh; /* 小屏下提高可视高度 */
  }
}

.meta-area {
  margin-top: 12px;
}

.chart-area {
  margin-top: 12px;
}

.chart-wrapper {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.chart-card {
  background: rgba(2, 6, 23, 0.55);
  border-radius: 12px;
  padding: 10px;
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.chart-card h5 {
  font-size: 12px;
  margin-top: 0px;
  margin-bottom: 8px;
  color: rgba(226, 232, 240, 0.85);
}

.chart-img {
  width: 100%;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  cursor: zoom-in;
}

.no-chart-msg {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.65);
  margin-top: 10px;
}

.analysis-area {
  margin-top: 12px;
}

.analysis-block {
  margin-top: 8px;
  background: rgba(2, 6, 23, 0.55);
  padding: 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.analysis-block :deep(p) {
  margin: 0.4em 0;
}

.lightbox {
  position: fixed;
  inset: 0;
  background: rgba(2, 6, 23, 0.72);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 999;
  padding: 24px;
}

.lightbox-body {
  max-width: 720px;
  width: 100%;
  background: rgba(15, 23, 42, 0.95);
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  overflow: hidden;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
}

.lightbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.16);
}

.lightbox-header h3 {
  font-size: 14px;
  margin: 0;
}

.lightbox-close {
  border: none;
  background: transparent;
  color: rgba(226, 232, 240, 0.8);
  font-size: 22px;
  cursor: pointer;
}

.lightbox-content {
  padding: 16px;
}

.lightbox-img {
  width: 100%;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.privacy-tip {
  margin-top: 10px;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.9);
  background: rgba(59, 130, 246, 0.12);
  border: 1px solid rgba(56, 189, 248, 0.22);
  padding: 8px 10px;
  border-radius: 12px;
}
</style>
