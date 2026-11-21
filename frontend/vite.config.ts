import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const target = process.env.API_PROXY || "http://127.0.0.1:8001";
const proxy = {
  "/api": { target },
  "/openapi.json": { target },
  "/compat": {
    target,
    rewrite: (path: string) => path.replace(/^\/compat/, ""),
  },
};
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: { input: { main: "index.html", legacy: "legacy.html" } },
  },
  server: { port: 5173, proxy },
  preview: { port: 5173, proxy },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
