<template>
  <div class="history">
    <details class="history-details" :open="open ?? undefined" @toggle="onToggle">
      <summary class="history-summary">
        <span>{{ title }}</span>
        <span class="count">({{ items.length }})</span>
      </summary>

      <div class="history-body">
        <div v-if="items.length" class="history-list">
          <div v-for="it in items" :key="it.id || it.sessionId" class="history-item">
            <div class="left">
              <div class="main">{{ displayTitle(it) }}</div>
              <div class="sub">{{ displayTime(it) }}</div>
            </div>
            <div class="right">
              <button type="button" class="btn mini" @click="$emit('restore', it)">恢复</button>
              <button type="button" class="btn mini danger" @click="$emit('remove', it)">删除</button>
            </div>
          </div>
        </div>

        <p v-else class="empty">{{ emptyText }}</p>
      </div>
    </details>
  </div>
</template>

<script setup>
const props = defineProps({
  title: { type: String, default: "历史记录" },
  items: { type: Array, default: () => [] },
  emptyText: { type: String, default: "暂无历史记录" },
  titleField: { type: String, default: "title" },
  // 可选受控展开态；不传时为非受控，交给原生 <details>
  open: { type: Boolean, default: undefined },
});

const emit = defineEmits(["restore", "remove", "update:open"]);

function onToggle(ev) {
  try {
    const isOpen = !!ev?.target?.open;
    emit("update:open", isOpen);
  } catch {}
}

function displayTitle(it) {
  if (!it) return "-";
  if (it.sessionId) return it.title || it.sessionId;
  if (it.query) return it.query;
  return it[props.titleField] || it.filename || it.id || "-";
}

function displayTime(it) {
  const ts = it.updatedAt || it.createdAt || it.ts;
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}
</script>

<style scoped>
.history {
  margin-top: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.5);
}

.history-details {
  padding: 10px 12px;
}

.history-summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(226, 232, 240, 0.92);
  font-weight: 650;
}

.count {
  opacity: 0.7;
  font-weight: 500;
}

.history-body {
  margin-top: 10px;
}

.history-list {
  display: grid;
  gap: 10px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.14);
}

.left .main {
  color: rgba(226, 232, 240, 0.95);
  font-size: 14px;
  font-weight: 650;
}

.left .sub {
  margin-top: 4px;
  color: rgba(148, 163, 184, 0.9);
  font-size: 12px;
}

.right {
  display: flex;
  gap: 8px;
}

.btn.mini {
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(2, 6, 23, 0.35);
  color: rgba(226, 232, 240, 0.9);
  cursor: pointer;
}

.btn.mini:hover {
  border-color: rgba(56, 189, 248, 0.45);
}

.btn.mini.danger:hover {
  border-color: rgba(248, 113, 113, 0.55);
}

.empty {
  color: rgba(148, 163, 184, 0.9);
  font-size: 13px;
  padding: 6px 2px;
}
</style>
