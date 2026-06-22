import { defineConfig } from "@playwright/test";

// Hermetic acceptance test: own temp database/exports, no external network sources are queried.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:8791", acceptDownloads: true },
  webServer: {
    command: "bash -c 'rm -rf /tmp/ch-e2e && mkdir -p /tmp/ch-e2e && cd ../backend && DATABASE_URL=sqlite:////tmp/ch-e2e/e2e.db EXPORTS_DIR=/tmp/ch-e2e/exports BACKUPS_DIR=/tmp/ch-e2e/b PORTFOLIO_PATH=/tmp/ch-e2e/p.json APP_PASSWORD=e2e-pass SESSION_SECRET=e2e .venv/bin/alembic upgrade head && DATABASE_URL=sqlite:////tmp/ch-e2e/e2e.db EXPORTS_DIR=/tmp/ch-e2e/exports BACKUPS_DIR=/tmp/ch-e2e/b PORTFOLIO_PATH=/tmp/ch-e2e/p.json APP_PASSWORD=e2e-pass SESSION_SECRET=e2e .venv/bin/uvicorn app.main:app --port 8791'",
    url: "http://127.0.0.1:8791/api/health",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
