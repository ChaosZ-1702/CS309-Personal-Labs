import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  // 避免使用 node_modules/.vite 目录，规避权限问题
  cacheDir: ".vite-cache",
  optimizeDeps: {
    force: true,
  },
  server: {
    port: 5173
  }
});
