import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target:
          process.env.API_PROXY_TARGET ?? process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.{test,spec}.ts"],
    // Keep vue-tsc/build clean: tests live outside src/.
    globals: false,
    clearMocks: true,
  },
});
