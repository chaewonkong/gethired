import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

process.env.PLAYWRIGHT_BROWSERS_PATH ??= path.join(here, ".playwright");
process.env.E2E_PORT ??= "8765";
process.env.E2E_TMP ??= mkdtempSync(path.join(tmpdir(), "gethired-e2e-"));

const baseURL = `http://127.0.0.1:${process.env.E2E_PORT}`;
const demoSize = { width: 1000, height: 720 };

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", testIgnore: "**/demo.spec.ts", use: { ...devices["Desktop Chrome"], headless: true } },
    {
      name: "demo",
      testMatch: "**/demo.spec.ts",
      use: {
        ...devices["Desktop Chrome"],
        headless: true,
        viewport: demoSize,
        deviceScaleFactor: 1,
        timezoneId: "Asia/Seoul",
        locale: "ko-KR",
        video: { mode: "on", size: demoSize },
      },
    },
  ],
  webServer: {
    command: "sh e2e/server.sh",
    url: `${baseURL}/api/companies`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
