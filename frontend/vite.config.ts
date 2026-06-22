/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: { exclude: ["e2e/**", "node_modules/**"], environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"] },
});
