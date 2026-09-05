import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/ui",
  timeout: 20000,
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:1420", trace: "retain-on-failure" },
  projects: [{ name: "webkit", use: { ...devices["Desktop Safari"] } }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 1420",
    url: "http://127.0.0.1:1420",
    reuseExistingServer: !process.env.CI,
  },
});
