import { expect, test } from "@playwright/test";
import fs from "node:fs";
import { execFileSync } from "node:child_process";

const EMAIL = `From: Upwork <donotreply@upwork.com>
Date: Mon, 20 Oct 2026 10:00:00 +0000
Subject: New jobs
Content-Type: text/html; charset=utf-8

<html><body><p>Python FastAPI RAG developer wanted for an LLM document pipeline on AWS with Docker. Remote, worldwide.</p>
<a href="https://www.upwork.com/jobs/~0999">Python FastAPI RAG developer</a></body></html>`;

test("login, empty dashboard, import, draft, approve, record, CSV download", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByLabel("Password")).toBeVisible();
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("Wrong password");
  await page.getByLabel("Password").fill("e2e-pass");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("No opportunities yet")).toBeVisible();   // honest empty dashboard

  await page.getByRole("button", { name: "Sources & settings" }).click();
  await expect(page.getByText("not available / needs authorisation").first()).toBeVisible();
  await page.getByLabel("alert email text").fill(EMAIL);
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Parsed 1 job link" })).toBeVisible();

  await page.getByRole("button", { name: "Runs & exports" }).click();
  const csvLink = page.getByRole("link", { name: /opportunities_.*\.csv/ }).first();
  await expect(csvLink).toBeVisible();
  const [dl] = await Promise.all([page.waitForEvent("download"), csvLink.click()]);
  const path = await dl.path();
  const text = fs.readFileSync(path!, "utf-8");
  expect(text).toContain("https://www.upwork.com/jobs/~0999");
  expect(text.split("\n")[0]).toContain("run_id,discovered_at,source_platform");
  expect(fs.readFileSync(path!)).toEqual(fs.readFileSync(`/tmp/ch-e2e/exports/${dl.suggestedFilename()}`));

  // manual listing whose company published an application email -> Leads tab -> download emails CSV
  await page.getByRole("button", { name: "Sources & settings" }).click();
  await page.getByLabel("title", { exact: true }).fill("Python FastAPI LLM contractor");
  await page.getByLabel("url", { exact: true }).fill("https://acme.example/jobs/1");
  await page.getByLabel("company name").fill("Acme");
  await page.getByLabel("description").fill("Contract Python FastAPI LLM RAG AWS Docker engineer, remote worldwide, start ASAP. To apply, email your CV to jobs@acme.example");
  await page.getByRole("button", { name: "Add", exact: true }).first().click();
  await expect(page.getByRole("status").filter({ hasText: "Added" })).toBeVisible();
  await page.getByRole("button", { name: "Leads (emails)" }).click();
  await expect(page.getByText("jobs@acme.example", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://acme.example/jobs/1");
  const [edl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Download all emails/ }).click()]);
  const etext = fs.readFileSync((await edl.path())!, "utf-8");
  expect(etext).toContain("jobs@acme.example");
  expect(etext.split("\n")[0]).toContain("business_email");
  expect(fs.readFileSync((await edl.path())!)).toEqual(fs.readFileSync(`/tmp/ch-e2e/exports/${edl.suggestedFilename()}`));


  // one ZIP with every CSV (no need to download them one by one)
  await page.getByRole("button", { name: "Runs & exports" }).click();
  const [zdl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download ALL CSVs/ }).click()]);
  expect(zdl.suggestedFilename()).toMatch(/^clienthunt_csvs_.*\.zip$/);
  const names = execFileSync("python3", ["-c", "import zipfile,sys;print('\\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))", (await zdl.path())!]).toString().split("\n");
  expect(names).toContain("manifest.csv");
  expect(names.filter((n) => n.startsWith("opportunities/")).length).toBeGreaterThanOrEqual(2);
  expect(names.filter((n) => n.startsWith("emails/")).length).toBeGreaterThanOrEqual(2);
  const onDisk = fs.readdirSync("/tmp/ch-e2e/exports").filter((f) => f.endsWith(".csv")).length;
  expect(names.filter((n) => n.endsWith(".csv") && n !== "manifest.csv").length).toBe(onDisk);

  await page.getByRole("button", { name: "Opportunities" }).click();
  await page.getByRole("row", { name: /Python FastAPI RAG developer/ }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg.getByRole("link", { name: /Open original listing/ })).toHaveAttribute("href", "https://www.upwork.com/jobs/~0999");
  await dlg.getByRole("button", { name: "Generate proposal draft" }).click();
  await expect(dlg.getByText("Client Acquisition Studio").first()).toBeVisible();
  await expect(dlg.getByRole("button", { name: "I submitted this on the platform" })).toHaveCount(0); // not before approval
  const approve = dlg.getByRole("button", { name: "Approve" });
  if (await dlg.getByLabel("I reviewed these warnings").count()) await dlg.getByLabel("I reviewed these warnings").check();
  await approve.click();
  await dlg.getByRole("button", { name: "I submitted this on the platform" }).click();
  await expect(dlg.getByText(/Recorded as/)).toBeVisible();
  await page.getByRole("button", { name: "✕ Close" }).click();

  await page.getByRole("button", { name: "Pipeline" }).click();
  await expect(page.getByText("Python FastAPI RAG developer")).toBeVisible();
  await page.getByRole("button", { name: "Overview" }).click();
  await expect(page.getByText("Applications submitted")).toBeVisible();
});
