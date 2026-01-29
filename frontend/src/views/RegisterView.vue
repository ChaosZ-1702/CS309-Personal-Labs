<template>
  <section class="auth">
    <div class="card">
      <h1>注册</h1>
      <p class="hint">设置密保口令（可中文），用于“修改密码”的验证。</p>

      <label class="field">
        <span>用户名</span>
        <input v-model="username" placeholder="至少 3 个字符" />
      </label>

      <label class="field">
        <span>密码</span>
        <input v-model="password" type="password" placeholder="至少 6 位" />
      </label>

      <label class="field">
        <span>确认密码</span>
        <input v-model="password2" type="password" placeholder="再次输入密码" />
      </label>

      <label class="field">
        <span>密保口令（可中文）</span>
        <input v-model="securityPhrase" placeholder="例如：我最喜欢的城市是上海" />
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button class="btn" type="button" @click="onRegister">注册</button>

      <div class="links">
        <RouterLink to="/login">返回登录</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { register } from "../auth/localAuth";

const router = useRouter();
const username = ref("");
const password = ref("");
const password2 = ref("");
const securityPhrase = ref("");
const error = ref("");

function onRegister() {
  error.value = "";
  try {
    if (password.value !== password2.value) {
      throw new Error("两次密码不一致");
    }
    register({
      username: username.value,
      password: password.value,
      securityPhrase: securityPhrase.value
    });
    router.push({ name: "login" });
  } catch (e) {
    error.value = e.message || "注册失败";
  }
}
</script>

<style scoped>
.auth {
  min-height: calc(100vh - 84px);
  display: grid;
  place-items: center;
  padding: 40px 16px;
}

.card {
  width: min(560px, 92vw);
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(2, 6, 23, 0.6);
  padding: 22px 22px;
}

h1 {
  margin: 0;
  font-size: 22px;
  color: rgba(226, 232, 240, 0.95);
}

.hint {
  margin: 10px 0 18px;
  color: rgba(148, 163, 184, 0.9);
  font-size: 13px;
}

.field {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
}

.field span {
  color: rgba(226, 232, 240, 0.9);
  font-size: 13px;
  font-weight: 650;
}

input {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(15, 23, 42, 0.55);
  color: rgba(226, 232, 240, 0.9);
  outline: none;
}

input:focus {
  border-color: rgba(56, 189, 248, 0.45);
}

.error {
  color: rgba(248, 113, 113, 0.95);
  margin: 6px 0 10px;
  font-size: 13px;
}

.btn {
  width: 100%;
  padding: 11px 14px;
  border-radius: 12px;
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: rgba(59, 130, 246, 0.18);
  color: rgba(226, 232, 240, 0.92);
  font-weight: 700;
  cursor: pointer;
}

.btn:hover {
  border-color: rgba(56, 189, 248, 0.55);
}

.links {
  margin-top: 14px;
}

.links a {
  color: rgba(56, 189, 248, 0.9);
  text-decoration: none;
  font-size: 13px;
}
</style>
