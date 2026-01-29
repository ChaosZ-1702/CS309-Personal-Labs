<template>
  <div class="news-agent-page">
    <header class="news-header">
      <h1>新闻智能体 · 金融资讯阅读</h1>
      <p>通过 Agent 聚合实时金融新闻，并支持查看原网址。</p>
    </header>

    <section class="news-query">
      <label class="field">
        <span>提问 / 需求：</span>
        <input
          v-model="userQuery"
          type="text"
          :disabled="loading"
          placeholder="例如：请给我几条今天的全球市场新闻并解读一下"
        />
      </label>

      <label class="field">
        <span>语言：</span>
        <select v-model="language" :disabled="loading">
          <option value="zh">中文</option>
          <option value="en">English</option>
          <option value="auto">自动</option>
        </select>
      </label>

      <button class="btn primary" :disabled="loading" @click="send">
        {{ loading ? "正在获取新闻…" : "发送到 Agent" }}
      </button>
    </section>

    <section class="news-layout">
      <main class="news-main" ref="leftCardRef">
        <div class="header-row">
          <h2>Agent 解读</h2>
          <div class="btn-row">
            <button class="btn ghost" :disabled="!reply" @click="exportMarkdown">
              导出资讯汇总为 Markdown
            </button>
            <button class="btn ghost" :disabled="!reply" @click="exportPdf">
              导出资讯汇总为 PDF
            </button>
          </div>
        </div>
        <div v-if="reply" class="reply-card" v-html="replyHtml"></div>
        <p v-else class="placeholder">这里将展示 Agent 对新闻的结构化解读。</p>
      </main>

      <aside class="news-list" ref="rightCardRef" :style="rightMaxHeightStyle">
        <header class="news-list-header">
          <h2>新闻源网址</h2>
        </header>

        <div v-if="newsItems && newsItems.length" class="news-items">
          <article
            v-for="(item, idx) in newsItems"
            :key="idx"
            class="news-item"
          >
            <div class="meta">
              <span class="source">{{ item.source || "未知来源" }}</span>
              <span class="lang-tag">{{ item.lang }}</span>
            </div>
            <a class="title" :href="item.link" target="_blank">
              {{ displayTitle(item) }}
            </a>
            <p class="summary" v-html="displaySummary(item)"></p>
          </article>
        </div>

        <p v-else class="placeholder">
          暂无新闻数据，请在上方输入问题并发送到 Agent。
        </p>
      </aside>
    </section>

    <!-- ✅ 查询历史（本地） -->
    <HistoryPanel
      title="查询历史（本地）"
      :items="newsHistory"
      emptyText="暂无查询历史（隐私模式开启时不会保存）。"
      @restore="restoreHistory"
      @remove="removeHistory"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { marked } from "marked";

import HistoryPanel from "../components/HistoryPanel.vue";
import { getCurrentUser } from "../auth/localAuth";
import {
  getPrivacyMode,
  listNewsRecords,
  appendNewsRecord,
  deleteNewsRecord,
  onLocalHistoryChanged,
  offLocalHistoryChanged
} from "../store/localHistory";


// 这个页面自己独立的会话 ID，用于上下文记忆
const sessionId = ref("news-session-1");
const username = computed(() => getCurrentUser());

const tick = ref(0);
function bump() { tick.value++; }

onMounted(() => onLocalHistoryChanged(bump));
onBeforeUnmount(() => offLocalHistoryChanged(bump));


const privacyMode = computed(() => getPrivacyMode(username.value));
const newsHistory = computed(() => {
  tick.value;
  return listNewsRecords(username.value);
});


const userQuery = ref("请给我几条今天的金融新闻并解读一下");
const language = ref("zh");
const loading = ref(false);
const streamController = ref(null);

const reply = ref("");
const replyHtml = computed(() => {
  try {
    const normalized = String(reply.value || "")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[ \t]+\n/g, "\n")
      .trimEnd();
    return marked.parse(normalized);
  } catch {
    return reply.value || "";
  }
});


const newsItems = ref([]);

const leftCardRef = ref(null);
const rightCardRef = ref(null);
const rightMaxHeightStyle = ref({});

// --- 右侧列表高度随左侧变化（保持原交互）---
let resizeObserver = null;

function measureHeights() {
  try {
    const leftRect = leftCardRef.value?.getBoundingClientRect?.();
    if (!leftRect) return;
    rightMaxHeightStyle.value = {
      maxHeight: `${Math.max(260, leftRect.height)}px`,
      overflow: "auto"
    };
  } catch {}
}

onMounted(() => {
  measureHeights();
  resizeObserver = new ResizeObserver(() => measureHeights());
  if (leftCardRef.value) {
    resizeObserver.observe(leftCardRef.value);
  }
  window.addEventListener("resize", measureHeights);
});

onBeforeUnmount(() => {
  if (resizeObserver && leftCardRef.value) {
    resizeObserver.unobserve(leftCardRef.value);
  }
  if (resizeObserver) resizeObserver.disconnect();
  window.removeEventListener("resize", measureHeights);
  if (streamController.value) {
    try {
      streamController.value.abort();
    } catch {}
  }
});

watch([reply, newsItems], () => nextTick(measureHeights));

async function send() {
  if (!userQuery.value.trim()) return;
  if (loading.value) return;

  // 终止上一条未完成的流
  if (streamController.value) {
    try {
      streamController.value.abort();
    } catch {}
  }

  loading.value = true;
  reply.value = "";
  newsItems.value = [];
  streamController.value = new AbortController();

  try {
    const res = await fetch("http://localhost:8000/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream"
      },
      body: JSON.stringify({
        session_id: sessionId.value,
        query: userQuery.value,
        language: language.value,
        export_markdown: false,
        export_pdf: false
      }),
      signal: streamController.value.signal
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`后端返回错误 ${res.status}: ${text}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let accum = "";
    let doneFlag = false;

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
        try {
          payload = JSON.parse(jsonStr);
        } catch (err) {
          console.error("SSE parse error", err, jsonStr);
          continue;
        }

        if (payload.type === "chunk") {
          accum += payload.content || "";
          reply.value = accum;
        } else if (payload.type === "done") {
          const finalText = payload.reply || accum;
          reply.value = finalText;
          newsItems.value =
            (payload.structured_data && payload.structured_data.news_items) || [];

          // ✅ 保存本地查询历史（隐私模式开启时 append 会自动跳过）
          appendNewsRecord(username.value, {
            query: userQuery.value,
            language: language.value,
            reply: finalText,
            newsItems: newsItems.value
          });

          doneFlag = true;
          break;
        } else if (payload.type === "error") {
          reply.value =
            accum + `\n\n(流式出错：${payload.message || "未知错误"})`;
          newsItems.value = [];
          doneFlag = true;
          break;
        }
      }

      if (doneFlag) break;
    }
  } catch (e) {
    if (e?.name === "AbortError") {
      // 用户发起新请求导致的中断
    } else {
      console.error(e);
      reply.value = e.message || "请求失败，请稍后重试。";
    }
  } finally {
    loading.value = false;
  }
}

function displayTitle(item) {
  return item.title || item.headline || "未命名新闻";
}

function displaySummary(item) {
  const txt = item.summary || item.abstract || "";
  try {
    const normalized = String(txt || "").replace(/\n{3,}/g, "\n\n").trimEnd();
    return marked.parse(normalized);
  } catch {
    return txt;
  }
}



function exportMarkdown() {
  if (!reply.value) return;
  const blob = new Blob([reply.value], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(
    now.getHours()
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  a.download = `news-summary-${stamp}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

async function exportPdf() {
  if (!reply.value) return;

  // ✅ 动态导入，避免页面初始化就因依赖问题白屏
  const { default: html2pdf } = await import("html2pdf.js/dist/html2pdf.min.js");

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}${pad(
    now.getHours()
  )}${pad(now.getMinutes())}${pad(now.getSeconds())}`;

  const container = document.createElement("div");
  container.innerHTML = replyHtml.value;
  container.style.padding = "18px";
  container.style.color = "#0f172a";
  container.style.fontSize = "14px";
  container.style.lineHeight = "1.7";
  container.style.background = "#ffffff";
  container.style.maxWidth = "720px";

  html2pdf()
    .set({
      margin: 10,
      filename: `news-summary-${stamp}.pdf`,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true },
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" }
    })
    .from(container)
    .save();
}


function restoreHistory(item) {
  if (!item) return;
  userQuery.value = item.query || "";
  language.value = item.language || "zh";
  reply.value = item.reply || "";
  newsItems.value = item.newsItems || [];
  nextTick(measureHeights);
}

function removeHistory(item) {
  if (!item || !item.id) return;
  deleteNewsRecord(username.value, item.id);
}
</script>

<style scoped>
.news-agent-page {
  min-height: 100vh;
  padding: 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  background: radial-gradient(circle at top, #1f2933 0, #020617 45%, #000 100%);
  color: #e5e7eb;
}

.news-header h1 {
  font-size: 26px;
  margin-bottom: 4px;
}

.news-header p {
  font-size: 13px;
  color: #9ca3af;
}

.news-query {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-end;
  background: rgba(15, 23, 42, 0.75);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  padding: 14px 16px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

.news-query .field {
  flex: none;
}

.news-query .field:first-of-type {
  flex: 1 1 0;
  min-width: 240px;
  position: relative;
}

.field span {
  white-space: nowrap;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.75);
  margin-bottom: 4px;
  display: block;
}

.field input,
.field select {
  width: 100%;
  background: rgba(2, 6, 23, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  padding: 10px 12px;
  color: #e5e7eb;
  outline: none;
  font-size: 13px;
}

.field input:focus,
.field select:focus {
  border-color: rgba(56, 189, 248, 0.55);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18);
}

.btn {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 999px;
  padding: 10px 14px;
  background: rgba(30, 41, 59, 0.75);
  color: #e5e7eb;
  cursor: pointer;
  transition: 0.15s ease;
  font-size: 13px;
}

.btn:hover {
  background: rgba(56, 189, 248, 0.18);
  border-color: rgba(56, 189, 248, 0.4);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn.primary {
  background: rgba(56, 189, 248, 0.28);
  border-color: rgba(56, 189, 248, 0.5);
}

.btn.primary:hover {
  background: rgba(56, 189, 248, 0.34);
}

.btn.ghost {
  background: transparent;
}

.news-layout {
  display: grid;
  grid-template-columns: 1.35fr 0.85fr;
  gap: 16px;
  align-items: start;
}

.news-main,
.news-list {
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.38);
}

.news-main {
  padding: 18px 18px 16px;
  overflow: hidden;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.header-row h2 {
  font-size: 18px;
  margin: 0;
}

.btn-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.reply-card {
  background: rgba(2, 6, 23, 0.55);
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  padding: 14px;
  font-size: 14px;
  line-height: 1.75;
}

.reply-card :deep(h1),
.reply-card :deep(h2),
.reply-card :deep(h3) {
  margin-top: 0.8em;
}

.placeholder {
  color: rgba(226, 232, 240, 0.65);
  font-size: 14px;
  padding: 12px;
}

.news-list {
  padding: 14px 14px 12px;
}

.news-list-header h2 {
  font-size: 16px;
  margin: 0 0 10px 0;
}

.news-items {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.news-item {
  background: rgba(2, 6, 23, 0.5);
  border: 1px solid rgba(148, 163, 184, 0.14);
  border-radius: 14px;
  padding: 12px;
}

.meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.65);
  margin-bottom: 6px;
}

.source {
  font-weight: 600;
}

.lang-tag {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.18);
  border: 1px solid rgba(56, 189, 248, 0.24);
  color: rgba(226, 232, 240, 0.85);
}

.title {
  display: block;
  color: rgba(226, 232, 240, 0.92);
  font-weight: 650;
  text-decoration: none;
  margin-bottom: 6px;
}

.title:hover {
  text-decoration: underline;
}

.summary {
  font-size: 13px;
  line-height: 1.6;
  color: rgba(226, 232, 240, 0.75);
  margin: 0;
}

@media (max-width: 980px) {
  .news-layout {
    grid-template-columns: 1fr;
  }
}
</style>
