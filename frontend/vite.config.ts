/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 테스트는 KST 기준 (마감 D-day, 시각 표시)
process.env.TZ = "Asia/Seoul";

export default defineConfig({
  plugins: [react()],
  // 빌드 산출물은 백엔드 패키지 안에 둬서 휠에 포함되게 한다
  build: { outDir: "../backend/app/static", emptyOutDir: true },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["./src/test/setup.ts"],
  },
});
