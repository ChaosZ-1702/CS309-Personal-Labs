import { createRouter, createWebHistory } from "vue-router";

import HomeView from "../views/HomeView.vue";
import AgentView from "../views/AgentView.vue";
import UploadView from "../views/UploadView.vue";
import NewsAgentView from "../views/NewsAgentView.vue";

import LoginView from "../views/LoginView.vue";
import RegisterView from "../views/RegisterView.vue";
import ResetPasswordView from "../views/ResetPasswordView.vue";

import { isLoggedIn } from "../auth/localAuth";

const routes = [
  // auth
  { path: "/login", name: "login", component: LoginView },
  { path: "/register", name: "register", component: RegisterView },
  { path: "/reset-password", name: "reset-password", component: ResetPasswordView },

  // app
  { path: "/", name: "home", component: HomeView, meta: { requiresAuth: true } },
  { path: "/agent", name: "agent", component: AgentView, meta: { requiresAuth: true } },
  { path: "/upload", name: "upload", component: UploadView, meta: { requiresAuth: true } },
  { path: "/news-agent", name: "news-agent", component: NewsAgentView, meta: { requiresAuth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  if (to.meta && to.meta.requiresAuth) {
    if (!isLoggedIn()) {
      return { name: "login" };
    }
  }
  if ((to.name === "login" || to.name === "register") && isLoggedIn()) {
    return { name: "agent" };
  }
  return true;
});

export default router;
