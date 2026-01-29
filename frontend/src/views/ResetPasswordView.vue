<template>
  <section class="auth">
    <div class="card">
      <h1>修改密码</h1>
      <p class="hint">通过密保口令验证后修改密码（密保口令可中文）。</p>

      <label class="field">
        <span>用户名</span>
        <input v-model="username" placeholder="请输入用户名" />
      </label>

      <label class="field">
        <span>密保口令</span>
        <input v-model="securityPhrase" placeholder="请输入注册时设置的密保口令" />
      </label>

      <label class="field">
        <span>新密码</span>
        <input v-model="newPassword" type="password" placeholder="至少 6 位" />
      </label>

      <label class="field">
        <span>确认新密码</span>
        <input v-model="newPassword2" type="password" placeholder="再次输入新密码" />
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button class="btn" type="button" @click="onReset">确认修改</button>

      <div class="links">
        <RouterLink to="/login">返回登录</RouterLink>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { useRouter, RouterLink } from "vue-router";
import { resetPassword } from "../auth/localAuth";

const router = useRouter();
const username = ref("");
const securityPhrase = ref("");
const newPassword = ref("");
const newPassword2 = ref("");
const error = ref("");

function onReset() {
  error.value = "";
  try {
    if (newPassword.value !== newPassword2.value) {
      throw new Error("两次新密码不一致");
    }
    resetPassword({
      username: username.value,
      securityPhrase: securityPhrase.value,
      newPassword: newPassword.value
    });
    router.push({ name: "login" });
  } catch (e) {
    error.value = e.message || "修改失败";
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
