import { getCurrentUser } from "../auth/localAuth";

const EVT = "local-history-changed";

function _emitChange() {
  try {
    window.dispatchEvent(new Event(EVT));
  } catch {}
}

export function onLocalHistoryChanged(handler) {
  window.addEventListener(EVT, handler);
}

export function offLocalHistoryChanged(handler) {
  window.removeEventListener(EVT, handler);
}

function _key(ns, username) {
  return `${ns}:${username}`;
}

function _readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function _writeJson(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
  _emitChange();
}

/** 隐私模式开关（按用户存） */
export function getPrivacyMode(username) {
  const u = username || getCurrentUser();
  if (!u) return false;
  return !!_readJson(_key("settings.privacyMode", u), false);
}

export function setPrivacyMode(username, on) {
  const u = username || getCurrentUser();
  if (!u) return;
  _writeJson(_key("settings.privacyMode", u), !!on);
}

/** 对话历史（按用户隔离） */
export function listChatSessions(username) {
  const u = username || getCurrentUser();
  if (!u) return [];
  return _readJson(_key("history.chat", u), []);
}

export function getChatSession(username, sessionId) {
  const u = username || getCurrentUser();
  if (!u) return null;
  const sessions = _readJson(_key("history.chat", u), []);
  return sessions.find((s) => s.sessionId === sessionId) || null;
}

export function deleteChatSession(username, sessionId) {
  const u = username || getCurrentUser();
  if (!u) return;
  const listKey = _key("history.chat", u);
  const sessions = _readJson(listKey, []);
  _writeJson(listKey, sessions.filter((s) => s.sessionId !== sessionId));
}

/**
 * ✅ 关键：只有当第一次 appendChatMessage 时才“创建会话记录”
 * 这样 “没发问就不会出现在历史列表”
 */
function _ensureChatSessionExists(u, sessionId) {
  const listKey = _key("history.chat", u);
  const sessions = _readJson(listKey, []);
  let idx = sessions.findIndex((s) => s.sessionId === sessionId);
  if (idx >= 0) return { sessions, idx, listKey };

  sessions.unshift({
    sessionId,
    title: "新会话",
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: []
  });
  idx = 0;
  return { sessions, idx, listKey };
}

export function appendChatMessage(username, sessionId, role, text) {
  const u = username || getCurrentUser();
  if (!u) return;
  if (getPrivacyMode(u)) return;

  const { sessions, idx, listKey } = _ensureChatSessionExists(u, sessionId);

  const msg = {
    role,
    text: String(text || ""),
    ts: Date.now()
  };
  sessions[idx].messages.push(msg);
  sessions[idx].updatedAt = Date.now();

  // 用第一条 user 消息作为标题
  if (role === "user" && (!sessions[idx].title || sessions[idx].title === "新会话")) {
    sessions[idx].title = msg.text.slice(0, 16);
  }

  _writeJson(listKey, sessions);
}

/** 上传历史（按用户隔离） */
export function listUploadRecords(username, type = "all") {
  const u = username || getCurrentUser();
  if (!u) return [];
  const list = _readJson(_key("history.uploads", u), []);
  if (type === "all") return list;
  return list.filter((x) => x.type === type);
}

export function appendUploadRecord(username, record) {
  const u = username || getCurrentUser();
  if (!u) return;
  if (getPrivacyMode(u)) return;

  const listKey = _key("history.uploads", u);
  const list = _readJson(listKey, []);
  list.unshift({
    id: `up-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: Date.now(),
    ...record
  });
  _writeJson(listKey, list);
}

export function deleteUploadRecord(username, id) {
  const u = username || getCurrentUser();
  if (!u) return;
  const listKey = _key("history.uploads", u);
  const list = _readJson(listKey, []);
  _writeJson(listKey, list.filter((x) => x.id !== id));
}

/** 新闻历史（按用户隔离） */
export function listNewsRecords(username) {
  const u = username || getCurrentUser();
  if (!u) return [];
  return _readJson(_key("history.news", u), []);
}

export function appendNewsRecord(username, record) {
  const u = username || getCurrentUser();
  if (!u) return;
  if (getPrivacyMode(u)) return;

  const listKey = _key("history.news", u);
  const list = _readJson(listKey, []);
  list.unshift({
    id: `news-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: Date.now(),
    ...record
  });
  _writeJson(listKey, list);
}

export function deleteNewsRecord(username, id) {
  const u = username || getCurrentUser();
  if (!u) return;
  const listKey = _key("history.news", u);
  const list = _readJson(listKey, []);
  _writeJson(listKey, list.filter((x) => x.id !== id));
}
