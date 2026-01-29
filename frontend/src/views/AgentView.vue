<template>
  <div class="agent">
    <header class="agent-header">
      <div class="header-left">
        <h1>AI 智能分析</h1>
        <p>多轮对话、任务规划、工具调用与文件解析（支持隐私模式与本地历史）。</p>
      </div>

      <div class="header-actions">
        <button class="btn" type="button" :disabled="loadingAk" @click="runAkShareAnalyze">
          {{ loadingAk ? "分析中..." : "一键分析 AkShare 指数行情" }}
        </button>
        <button class="btn ghost" type="button" @click="newChatSession">
          新建会话
        </button>
      </div>
    </header>

    <section class="layout">
      <!-- 左：Chat -->
      <div class="panel chat">
        <div class="chat-scroll" ref="chatScrollRef">
          <div v-for="(m, idx) in messages" :key="idx" class="msg" :class="m.role">
            <div class="meta">
              <span class="role">{{ m.role === "user" ? "你" : "Agent" }}</span>
              <span class="time">{{ m.time }}</span>
            </div>
            <div class="bubble" v-html="m.html"></div>
          </div>
        </div>

        <div class="composer">
          <input
            v-model="input"
            class="chat-input"
            placeholder="输入问题，例如：对比最近三个月新能源行业股价走势"
            @keyup.enter="handleSend"
          />
          <button class="send" type="button" :disabled="sending" @click="handleSend">
            {{ sending ? "发送中..." : "发送" }}
          </button>
        </div>

        <!-- ✅ 对话历史（仅在发生对话后才出现） -->
        <HistoryPanel
          title="对话历史（本地）"
          :items="chatSessions"
          emptyText="暂无对话历史（隐私模式开启时不会保存）。"
          @restore="restoreChat"
          @remove="removeChat"
        />
      </div>

      <!-- 右：Timeline + Upload -->
      <div class="panel side">
        <div class="timeline" :style="timelineStyle">
          <h3>任务规划与工具调用时间线</h3>
          <div v-if="stepsTimeline.length" class="timeline-body">
            <div v-for="s in stepsTimeline" :key="s.id" class="step">
              <div class="badge">{{ mapStepType(s.type) }}</div>
              <div class="content">
                <div class="title">{{ s.title }}</div>
                <div class="detail" v-html="s.detailHtml || renderMarkdown(s.detail)"></div>
                <div class="ts">{{ s.timestamp }}</div>
              </div>
            </div>
          </div>
          <p v-else class="placeholder">暂无任务记录。发起对话或点击一键分析后将展示过程。</p>
        </div>

        <div class="upload" :style="uploadStyle">
          <h3>PDF / Excel 财报解析与图表</h3>

          <div class="u-row">
            <input type="file" accept="application/pdf" @change="onSelectPdf" />
            <button class="upload-btn" type="button" :disabled="!pdfFile || uploadingPdf" @click="uploadPdf">
              {{ uploadingPdf ? "解析中..." : "上传并解析 PDF" }}
            </button>
          </div>

          <div class="u-row">
            <input type="file" accept=".xls,.xlsx" @change="onSelectExcel" />
            <button class="upload-btn" type="button" :disabled="!excelFile || uploadingExcel" @click="uploadExcel">
              {{ uploadingExcel ? "解析中..." : "上传并解析 Excel" }}
            </button>
          </div>

          <div v-if="lastFileSummary" class="file-result">
            <h4>最近一次解析结果</h4>
            <p class="file-name">文件：{{ lastFileSummary.filename }}</p>

            <div class="chart-grid" v-if="charts && charts.length">
              <div class="chart-card" v-for="(c, i) in charts" :key="i">
                <div class="chart-title">{{ c.name }}</div>
                <img class="chart-img" :src="'data:image/png;base64,' + c.image_base64" :alt="c.name" />
              </div>
            </div>
          </div>

          <!-- ✅ 上传历史分开：PDF / Excel -->
          <HistoryPanel
            title="PDF 解析历史（本地）"
            :items="pdfUploadHistory"
            emptyText="暂无 PDF 解析历史（隐私模式开启时不会保存）。"
            :open="pdfPanelOpen"
            @update:open="setPdfOpen"
            @restore="restoreUpload"
            @remove="removeUpload"
          />
          <HistoryPanel
            title="Excel 解析历史（本地）"
            :items="excelUploadHistory"
            emptyText="暂无 Excel 解析历史（隐私模式开启时不会保存）。"
            :open="excelPanelOpen"
            @update:open="setExcelOpen"
            @restore="restoreUpload"
            @remove="removeUpload"
          />
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, onBeforeUnmount, onMounted } from "vue";
import { marked } from "marked";
import HistoryPanel from "../components/HistoryPanel.vue";
import { uploadPdf as apiUploadPdf, uploadExcel as apiUploadExcel } from "../api/upload";

import { getCurrentUser } from "../auth/localAuth";
import {
  listChatSessions,
  getChatSession,
  deleteChatSession,
  appendChatMessage,
  listUploadRecords,
  appendUploadRecord,
  deleteUploadRecord,
  getPrivacyMode,
  onLocalHistoryChanged,
  offLocalHistoryChanged
} from "../store/localHistory";

const username = computed(() => getCurrentUser());
const privacyMode = computed(() => getPrivacyMode(username.value));

// ✅ 只生成 sessionId，不自动写历史
const sessionId = ref(`sess-${Date.now()}`);

const input = ref("");
const messages = ref([]);
const stepsTimeline = ref([]);
// 记录已添加的步骤 ID，避免重复展示
const seenStepIds = ref(new Set());
const sending = ref(false);
const loadingAk = ref(false);
const streamController = ref(null);

// 上传相关
const pdfFile = ref(null);
const excelFile = ref(null);
const uploadingPdf = ref(false);
const uploadingExcel = ref(false);
const lastFileSummary = ref(null);
const charts = ref([]);

const chatScrollRef = ref(null);

// 解析历史面板展开态（互斥）
const pdfPanelOpen = ref(false);
const excelPanelOpen = ref(false);

function setPdfOpen(v) {
  pdfPanelOpen.value = !!v;
  if (v) excelPanelOpen.value = false;
}

function setExcelOpen(v) {
  excelPanelOpen.value = !!v;
  if (v) pdfPanelOpen.value = false;
}

// ✅ 用 tick 触发 computed 重新读取 localStorage
const tick = ref(0);
function bump(){ tick.value++; }
onMounted(() => onLocalHistoryChanged(bump));
onBeforeUnmount(() => offLocalHistoryChanged(bump));

const newsHistory = computed(() => {
  tick.value;
  return listNewsRecords(username.value);
});


// computed 里引用 tick，确保删除/新增立即刷新
const chatSessions = computed(() => {
  tick.value;
  return listChatSessions(username.value);
});

const pdfUploadHistory = computed(() => {
  tick.value;
  return listUploadRecords(username.value, "pdf");
});

const excelUploadHistory = computed(() => {
  tick.value;
  return listUploadRecords(username.value, "excel");
});

// 自适应：当两者都有内容时，上下各最多 50%；
// 当其一无内容时，另一者可占满，但为无内容的区域保留必要空间（标题/占位）
const hasTimelineContent = computed(() => stepsTimeline.value.length > 0);
const hasUploadContent = computed(() => !!lastFileSummary.value || (charts.value && charts.value.length > 0));
const bothContent = computed(() => hasTimelineContent.value && hasUploadContent.value);

const timelineStyle = computed(() => {
  if (bothContent.value) return { flex: '1 1 0', maxHeight: '50%' };
  if (hasTimelineContent.value) return { flex: '1 1 auto', maxHeight: '100%' };
  return { flex: '0 0 auto', minHeight: '140px' };
});

const uploadStyle = computed(() => {
  if (bothContent.value) return { flex: '1 1 0', maxHeight: '50%' };
  if (hasUploadContent.value) return { flex: '1 1 auto', maxHeight: '100%' };
  return { flex: '0 0 auto', minHeight: '140px' };
});

function scrollToBottom() {
  nextTick(() => {
    if (chatScrollRef.value) chatScrollRef.value.scrollTop = chatScrollRef.value.scrollHeight;
  });
}

function nowTime() {
  return new Date().toLocaleTimeString();
}

function renderMarkdown(text) {
  try {
    const normalized = String(text || "")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]+\n/g, "\n")
      .trimEnd();
    return marked.parse(normalized);
  } catch {
    return String(text || "");
  }
}


function pushMessage(role, text, saveToHistory = true) {
  const raw = String(text || "");
  messages.value.push({
    role,
    time: nowTime(),
    raw,
    html: renderMarkdown(raw),
  });
  scrollToBottom();

  // ✅ 只有用户真实对话才保存；且隐私模式下 append 会自动跳过
  if (saveToHistory) {
    appendChatMessage(username.value, sessionId.value, role, raw);
  }
}

function prettyJson(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function mapStepType(t) {
  if (t === "plan") return "任务规划";
  if (t === "tool") return "工具调用";
  if (t === "summary") return "结果汇总";
  return t;
}

function formatTimestamp(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts || "");
  const pad = (n) => String(n).padStart(2, "0");
  const year = d.getFullYear();
  const month = pad(d.getMonth() + 1);
  const date = pad(d.getDate());
  const hh = pad(d.getHours());
  const mm = pad(d.getMinutes());
  const ss = pad(d.getSeconds());
  return `${year}/${month}/${date} ${hh}:${mm}:${ss}`;
}

function addTimelineStep(s) {
  const id = s.id || "step-" + Date.now() + Math.random().toString(16).slice(2);
  if (seenStepIds.value.has(id)) return;
  seenStepIds.value.add(id);
  const ts = s.timestamp || new Date().toISOString();
  const normalized = {
    id,
    type: s.type || "tool",
    title: s.title || "步骤",
    detail: s.detail || "",
    detailHtml: renderMarkdown(s.detail || ""),
    timestamp: formatTimestamp(ts),
    payload: s.payload || null,
  };
  stepsTimeline.value = [...stepsTimeline.value, normalized];
}

function newChatSession() {
  // ✅ 新会话只重置页面状态，不写历史
  sessionId.value = `sess-${Date.now()}`;
  messages.value = [];
  stepsTimeline.value = [];
  // 给用户一个提示，但不进历史
  pushMessage("assistant", "已创建新会话。你可以开始提问。", false);
}

function restoreChat(item) {
  const sess = getChatSession(username.value, item.sessionId);
  if (!sess) return;
  sessionId.value = sess.sessionId;
  messages.value = (sess.messages || []).map((m) => ({
    role: m.role,
    time: new Date(m.ts).toLocaleTimeString(),
    raw: m.text,
    html: renderMarkdown(m.text),
  }));
  stepsTimeline.value = [];
  scrollToBottom();
}

function removeChat(item) {
  deleteChatSession(username.value, item.sessionId);
  // ✅ 如果删的是当前会话，不要刷新自动创建；只清空页面
  if (item.sessionId === sessionId.value) {
    sessionId.value = `sess-${Date.now()}`;
    messages.value = [];
    stepsTimeline.value = [];
  }
}

function restoreUpload(item) {
  lastFileSummary.value = {
    filename: item.filename,
    metrics: item.metrics,
  };
  charts.value = (item.metrics && item.metrics._charts) || [];
}

function removeUpload(item) {
  deleteUploadRecord(username.value, item.id);
}

async function handleSend() {
  if (!input.value.trim() || sending.value) return;
  const q = input.value.trim();
  input.value = "";

  // ✅ 用户的第一句话会触发 appendChatMessage，进而创建 session 历史
  pushMessage("user", q, true);
  sending.value = true;

  if (streamController.value) {
    try { streamController.value.abort(); } catch {}
  }
  const controller = new AbortController();
  streamController.value = controller;

  try {
    const resp = await fetch("http://localhost:8000/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId.value,
        query: q,
        language: "zh",
        export_markdown: false,
        export_pdf: false,
      }),
      signal: controller.signal,
    });

    if (!resp.ok || !resp.body) throw new Error(`后端返回错误 ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let assistantIndex = -1;
    let assistantRaw = "";

    const ensureAssistantMessage = () => {
      if (assistantIndex >= 0) return assistantIndex;
      const msg = { role: "assistant", time: nowTime(), raw: "", html: renderMarkdown("") };
      assistantIndex = messages.value.push(msg) - 1;
      scrollToBottom();
      return assistantIndex;
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const packet = buffer.slice(0, sep).trim();
        buffer = buffer.slice(sep + 2);
        if (!packet.startsWith("data:")) continue;

        const jsonStr = packet.replace(/^data:\s*/, "");
        let payload;
        try { payload = JSON.parse(jsonStr); } catch { continue; }

        if (payload.type === "step" && payload.step) {
          addTimelineStep(payload.step);
        }

        if (payload.type === "chunk") {
          ensureAssistantMessage();
          assistantRaw += payload.content || "";
          messages.value[assistantIndex].raw = assistantRaw;
          messages.value[assistantIndex].html = renderMarkdown(assistantRaw);
          scrollToBottom();
        }

        if (payload.type === "done") {
          ensureAssistantMessage();
          const reply = payload.reply || assistantRaw || "";
          messages.value[assistantIndex].raw = reply;
          messages.value[assistantIndex].html = renderMarkdown(reply);
          scrollToBottom();

          // ✅ DONE 时保存 assistant 完整内容
          appendChatMessage(username.value, sessionId.value, "assistant", reply);

          if (Array.isArray(payload.steps)) {
            payload.steps.forEach((s) => addTimelineStep(s));
          }
        }

        if (payload.type === "error") {
          throw new Error(payload.message || "流式错误");
        }
      }
    }
  } catch (e) {
    console.error(e);
    pushMessage("assistant", `请求失败：${e.message || e}`, true);
  } finally {
    sending.value = false;
  }
}

async function runAkShareAnalyze() {
  loadingAk.value = true;
  // 这里算用户操作，但不一定算“对话”，你可以决定是否入历史；
  // 我这里不入 chat 历史，只作为页面消息显示
  pushMessage("user", "一键分析 AkShare 指数行情。", false);

  try {
    const resp = await fetch("http://localhost:8000/api/akshare/analyze?language=zh");
    if (!resp.ok) throw new Error("后端 AkShare 分析接口请求失败");
    const data = await resp.json();
    const text = data.analysis || "后端未返回分析文本。";
    pushMessage("assistant", text, false);

    const step = {
      id: "akshare-" + Date.now(),
      type: "tool",
      title: "AkShare 指数行情分析",
      detail: "调用 /api/akshare/analyze，对当前主要指数进行整体解读。",
      detailHtml: renderMarkdown("调用 /api/akshare/analyze，对当前主要指数进行整体解读。"),
      timestamp: new Date().toISOString(),
      payload: { indices: (data.snapshot && data.snapshot.indices) || [] },
    };
    stepsTimeline.value = [...stepsTimeline.value, step];
  } catch (e) {
    console.error(e);
    pushMessage("assistant", `AkShare 分析失败：${e.message || e}`, false);
  } finally {
    loadingAk.value = false;
  }
}

function onSelectPdf(ev) {
  const files = ev.target.files;
  pdfFile.value = files && files[0] ? files[0] : null;
}

function onSelectExcel(ev) {
  const files = ev.target.files;
  excelFile.value = files && files[0] ? files[0] : null;
}

async function uploadPdf() {
  if (!pdfFile.value || uploadingPdf.value) return;
  uploadingPdf.value = true;
  try {
    const data = await apiUploadPdf({
      sessionId: sessionId.value,
      file: pdfFile.value,
      store: !privacyMode.value
    });

    lastFileSummary.value = { filename: data.filename, metrics: data.metrics };
    charts.value = (data.metrics && data.metrics._charts) || [];

    appendUploadRecord(username.value, { type: "pdf", filename: data.filename, metrics: data.metrics });
  } catch (e) {
    console.error(e);
    pushMessage("assistant", `PDF 解析失败：${e.message || e}`, false);
  } finally {
    uploadingPdf.value = false;
  }
}

async function uploadExcel() {
  if (!excelFile.value || uploadingExcel.value) return;
  uploadingExcel.value = true;
  try {
    const data = await apiUploadExcel({
      sessionId: sessionId.value,
      file: excelFile.value,
      store: !privacyMode.value
    });

    lastFileSummary.value = { filename: data.filename, metrics: data.metrics };
    charts.value = (data.metrics && data.metrics._charts) || [];

    appendUploadRecord(username.value, { type: "excel", filename: data.filename, metrics: data.metrics });
  } catch (e) {
    console.error(e);
    pushMessage("assistant", `Excel 解析失败：${e.message || e}`, false);
  } finally {
    uploadingExcel.value = false;
  }
}


// 初次进入：不保存会话，只给页面一个提示（不进历史）
onMounted(() => {
  pushMessage("assistant", "欢迎使用 AI 智能分析：输入问题即可开始。", false);
});
</script>

<style scoped>
/* 保持你们原有风格不变（省略：与你现有 AgentView 样式相同即可） */

/* 我只放你之前那份样式的关键结构；如果你原文件里样式更多，直接保留原样式也行 */
.agent { height: 125vh; padding: 32px 40px; background: radial-gradient(circle at top, #020617 0, #000 60%, #020617 100%); color: #e5e7eb; display: flex; flex-direction: column; overflow: hidden; }
.agent-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.header-left h1 { margin: 0 0 4px; font-size: 26px; }
.header-left p { margin: 0; font-size: 13px; color: #9ca3af; }
.header-actions { display: flex; gap: 10px; align-items: center; }
.btn { padding: 10px 14px; border-radius: 12px; border: 1px solid rgba(56, 189, 248, 0.35); background: rgba(59, 130, 246, 0.18); color: rgba(226, 232, 240, 0.92); font-weight: 700; cursor: pointer; }
.btn:hover { border-color: rgba(56, 189, 248, 0.55); }
.btn.ghost { border-color: rgba(148, 163, 184, 0.18); background: rgba(2, 6, 23, 0.25); font-weight: 650; }
.layout { display: grid; grid-template-columns: 1.3fr 1fr; gap: 18px; flex: 1; min-height: 0; }
.panel { border: 1px solid rgba(148, 163, 184, 0.18); border-radius: 18px; background: rgba(2, 6, 23, 0.55); overflow: hidden; min-height: 0; }
.chat { display: flex; flex-direction: column; padding: 16px; min-height: 0; }
.chat-scroll { flex: 1; overflow: auto; padding-right: 6px; }
.msg { margin-bottom: 14px; }
.meta { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; color: rgba(148, 163, 184, 0.9); font-size: 12px; }
.role { font-weight: 700; color: rgba(226, 232, 240, 0.88); }
.bubble { padding: 12px 12px; border-radius: 14px; border: 1px solid rgba(148, 163, 184, 0.14); background: rgba(15, 23, 42, 0.55); color: rgba(226, 232, 240, 0.9); }
.composer { display: flex; gap: 10px; margin-top: 12px; }
.chat-input { flex: 1; padding: 11px 12px; border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.2); background: rgba(15, 23, 42, 0.55); color: rgba(226, 232, 240, 0.9); outline: none; }
.send { padding: 11px 14px; border-radius: 12px; border: 1px solid rgba(56, 189, 248, 0.35); background: rgba(59, 130, 246, 0.18); color: rgba(226, 232, 240, 0.92); font-weight: 800; cursor: pointer; }
/* 右侧不要用 1fr 1fr，否则会强行拉高产生巨大空白 */
.side { display: flex; flex-direction: column; gap: 14px; padding: 16px; overflow: hidden; min-height: 0; }

/* 让两个区块按内容自然高度排列 */
.timeline,
.upload { flex: 1 1 0; min-height: 0; }

/* 时间线卡片内部滚动，不影响标题与外部控件 */
.timeline { display: flex; flex-direction: column; }
.timeline-body { flex: 1; overflow: auto; min-height: 0; }

/* 上传卡片内部布局与滚动：仅解析结果区域滚动 */
.upload { display: flex; flex-direction: column; }
.file-result { flex: 1; overflow: auto; min-height: 0; }
.bubble :deep(p) { margin: 0.35em 0; }
.bubble :deep(p:last-child) { margin-bottom: 0; }
.bubble :deep(pre) { margin: 0.5em 0; }

.bubble :deep(ul), .bubble :deep(ol) { padding-left: 2rem; margin: 0.5em 0; }
.bubble :deep(ol) { list-style: decimal; }
.bubble :deep(ul) { list-style: disc; }
.bubble :deep(li) { margin: 0.25em 0; }
.bubble :deep(li ul), .bubble :deep(li ol) { padding-left: 1rem; margin-top: 0.25em; }

.timeline h3, .upload h3 { margin: 0 0 10px; font-size: 15px; color: rgba(226, 232, 240, 0.92); }
.step { display: flex; font-size: 14px; gap: 10px; padding: 12px; border-radius: 14px; border: 1px solid rgba(148, 163, 184, 0.14); background: rgba(15, 23, 42, 0.55); margin-bottom: 10px; }
.badge { min-width: 68px; height: 26px; display: grid; place-items: center; border-radius: 999px; border: 1px solid rgba(56, 189, 248, 0.35); background: rgba(59, 130, 246, 0.14); color: rgba(226, 232, 240, 0.88); font-size: 12px; font-weight: 700; }
.timeline .detail :deep(ul), .timeline .detail :deep(ol) { padding-left: 1rem; margin: 0.5em 0; }
.timeline .detail :deep(li) { margin: 0.25em 0; }
.u-row { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.upload-btn { padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.2); background: rgba(2, 6, 23, 0.3); color: rgba(226, 232, 240, 0.9); cursor: pointer; }
.chart-grid { margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.chart-img { width: 100%; border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.12); }
</style>
