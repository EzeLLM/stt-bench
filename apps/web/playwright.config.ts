import { defineConfig } from "@playwright/test";
import { mkdtempSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const apiPort = process.env.STT_API_PORT || "8000";
const webPort = process.env.STT_WEB_PORT || "5173";
const testData = mkdtempSync(join(tmpdir(), "stt-lab-browser-"));
export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    browserName: "chromium",
    launchOptions: {
      executablePath:
        process.env.CHROMIUM_PATH ||
        (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
    },
  },
  workers: 1,
  metadata: { testData },
  webServer: [
    {
      command: `STT_LAB_DATA=${testData} ../../.venv/bin/uvicorn stt_lab.api:app_factory --factory --host 127.0.0.1 --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/api/v1/health`,
      reuseExistingServer: false,
    },
    {
      command: "npm run dev",
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
    },
  ],
});
