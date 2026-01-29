// 演示级本地认证：数据存 localStorage
// 注意：真实生产不会把密码存在前端；这里用于课程项目/原型展示。

import { ref } from "vue";

const LS_USERS = "auth.users";
const LS_CURRENT = "auth.currentUser";

// 响应式状态，用于触发 UI 更新
export const currentUser = ref(localStorage.getItem(LS_CURRENT) || "");

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
}

export function getCurrentUser() {
  return currentUser.value;
}

export function isLoggedIn() {
  return !!currentUser.value;
}

export function logout() {
  localStorage.removeItem(LS_CURRENT);
  currentUser.value = "";
}

export function register({ username, password, securityPhrase }) {
  const u = String(username || "").trim();
  const p = String(password || "");
  const sp = String(securityPhrase || "").trim();

  if (u.length < 3) throw new Error("用户名至少 3 个字符");
  if (p.length < 6) throw new Error("密码至少 6 位");
  if (!sp) throw new Error("密保口令不能为空（可用汉字）");

  const users = _readJson(LS_USERS, []);
  if (users.find((x) => x.username === u)) {
    throw new Error("用户名已存在");
  }

  users.push({
    username: u,
    password: p,
    securityPhrase: sp
  });

  _writeJson(LS_USERS, users);
  return true;
}

export function login({ username, password }) {
  const u = String(username || "").trim();
  const p = String(password || "");
  const users = _readJson(LS_USERS, []);
  const found = users.find((x) => x.username === u);
  if (!found) throw new Error("用户不存在");
  if (found.password !== p) throw new Error("密码错误");
  localStorage.setItem(LS_CURRENT, u);
  currentUser.value = u; // 更新响应式状态
  return true;
}

export function resetPassword({ username, securityPhrase, newPassword }) {
  const u = String(username || "").trim();
  const sp = String(securityPhrase || "").trim();
  const np = String(newPassword || "");

  if (!u) throw new Error("请输入用户名");
  if (!sp) throw new Error("请输入密保口令");
  if (np.length < 6) throw new Error("新密码至少 6 位");

  const users = _readJson(LS_USERS, []);
  const idx = users.findIndex((x) => x.username === u);
  if (idx < 0) throw new Error("用户不存在");
  if (users[idx].securityPhrase !== sp) throw new Error("密保口令不正确");

  users[idx].password = np;
  _writeJson(LS_USERS, users);
  return true;
}
