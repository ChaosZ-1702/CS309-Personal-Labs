<template>
  <div class="app-shell">
    <div class="bg-grid"></div>
    <div class="bg-glow"></div>

    <header class="app-header">
      <div class="logo">
        <span class="dot"></span>
        <span class="brand">
          FinAgent<span class="brand-sub">.AI</span>
        </span>
      </div>

      <nav class="nav" v-if="loggedIn">
        <RouterLink to="/" class="nav-link" :class="{ active: route.name === 'home' }">
          实时资讯
        </RouterLink>
        <RouterLink to="/agent" class="nav-link" :class="{ active: route.name === 'agent' }">
          AI 智能分析
        </RouterLink>
        <RouterLink to="/upload" class="nav-link" :class="{ active: route.name === 'upload' }">
          报表解析 / 上传
        </RouterLink>
        <RouterLink to="/news-agent" class="nav-link" :class="{ active: route.name === 'news-agent' }">
          新闻总结
        </RouterLink>
      </nav>

      <div class="user-area">
        <template v-if="!loggedIn">
          <RouterLink to="/login" class="user-link">登录</RouterLink>
          <RouterLink to="/register" class="user-link">注册</RouterLink>
        </template>

        <template v-else>
          <label class="privacy">
            <input type="checkbox" :checked="privacyMode" @change="togglePrivacy" />
            <span>隐私模式</span>
          </label>
          <span class="user">Hi, {{ username }}</span>
          <button class="logout" type="button" @click="handleLogout">退出</button>
        </template>
      </div>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { useRoute, useRouter, RouterLink, RouterView } from "vue-router";
import { getCurrentUser, isLoggedIn, logout } from "./auth/localAuth";
import { getPrivacyMode, setPrivacyMode } from "./store/localHistory";

const route = useRoute();
const router = useRouter();

const loggedIn = computed(() => isLoggedIn());
const username = computed(() => getCurrentUser());
const privacyMode = computed(() => getPrivacyMode(username.value));

function togglePrivacy(ev) {
  const on = !!ev.target.checked;
  setPrivacyMode(username.value, on);
}

function handleLogout() {
  logout();
  router.push({ name: "login" });
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: radial-gradient(circle at top, #020617 0, #000 60%, #020617 100%);
  color: #e5e7eb;
  position: relative;
  overflow: hidden;
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(circle at 30% 10%, #000 0, transparent 60%);
  pointer-events: none;
}

.bg-glow {
  position: absolute;
  inset: -40%;
  background: radial-gradient(circle at center, rgba(59, 130, 246, 0.22), transparent 55%);
  filter: blur(80px);
  pointer-events: none;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 22px;
  padding: 20px 34px;
  backdrop-filter: blur(18px);
  background: rgba(2, 6, 23, 0.65);
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: conic-gradient(from 180deg, #22c55e, #22c55e, #3b82f6, #8b5cf6, #22c55e);
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.8);
  animation: dotPulse 1.8s ease-in-out infinite;
}

.brand {
  font-weight: 700;
  letter-spacing: 0.4px;
  color: rgba(226, 232, 240, 0.95);
}

.brand-sub {
  color: rgba(56, 189, 248, 0.95);
}

.nav {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.nav-link {
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(2, 6, 23, 0.25);
  color: rgba(226, 232, 240, 0.85);
  text-decoration: none;
  font-weight: 600;
  transition: all 0.2s ease;
}

.nav-link:hover {
  border-color: rgba(56, 189, 248, 0.4);
  color: rgba(226, 232, 240, 0.95);
}

.nav-link.active {
  border-color: rgba(56, 189, 248, 0.55);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.25) inset;
}

.user-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-link {
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  color: rgba(226, 232, 240, 0.85);
  text-decoration: none;
  background: rgba(2, 6, 23, 0.25);
}

.user-link:hover {
  border-color: rgba(56, 189, 248, 0.45);
}

.privacy {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.85);
  padding: 6px 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 999px;
  background: rgba(2, 6, 23, 0.25);
}

.user {
  color: rgba(226, 232, 240, 0.9);
  font-weight: 650;
}

.logout {
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(2, 6, 23, 0.25);
  color: rgba(226, 232, 240, 0.85);
  cursor: pointer;
}

.logout:hover {
  border-color: rgba(248, 113, 113, 0.5);
}

.app-main {
  padding: 0;
}

@keyframes dotPulse {
  0%,
  100% {
    transform: scale(0.9);
    opacity: 0.9;
  }
  50% {
    transform: scale(1.15);
    opacity: 1;
  }
}
</style>
