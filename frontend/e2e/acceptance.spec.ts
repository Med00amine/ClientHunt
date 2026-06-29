import { expect, test } from "@playwright/test";
import fs from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

const PY = path.resolve("../backend/.venv/bin/python");   // has openpyxl
const sheetInfo = (file: string) => JSON.parse(execFileSync(PY, ["-c", `
import json, sys
from openpyxl import load_workbook
wb = load_workbook(sys.argv[1])
out = {ws.title: [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()] for ws in wb}
print(json.dumps(out))`, file]).toString());

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
  await page.getByText("Individual files (archive)").click();            // the per-run files are tucked away by default
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
  const [edl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Only the emails/ }).click()]);
  const etext = fs.readFileSync((await edl.path())!, "utf-8");
  expect(etext).toContain("jobs@acme.example");
  expect(etext.split("\n")[0]).toContain("business_email");
  expect(fs.readFileSync((await edl.path())!)).toEqual(fs.readFileSync(`/tmp/ch-e2e/exports/${edl.suggestedFilename()}`));


  // one ZIP with every CSV (no need to download them one by one)
  await page.getByRole("button", { name: "Runs & exports" }).click();
  await page.getByText("Individual files (archive)").click();
  const [zdl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download all of them \(ZIP\)/ }).click()]);
  expect(zdl.suggestedFilename()).toMatch(/^clienthunt_csvs_.*\.zip$/);
  const names = execFileSync("python3", ["-c", "import zipfile,sys;print('\\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))", (await zdl.path())!]).toString().split("\n");
  expect(names).toContain("manifest.csv");
  expect(names.filter((n) => n.startsWith("opportunities/")).length).toBeGreaterThanOrEqual(2);
  expect(names.filter((n) => n.startsWith("emails/")).length).toBeGreaterThanOrEqual(2);
  const onDisk = fs.readdirSync("/tmp/ch-e2e/exports").filter((f) => f.endsWith(".csv")).length;
  expect(names.filter((n) => n.endsWith(".csv") && n !== "manifest.csv").length).toBe(onDisk);

  // ONE file with everything from all runs (Research tab: compact runs, a single download)
  await page.getByRole("button", { name: "Research", exact: true }).click();
  await expect(page.getByTestId("run-row").first()).toBeVisible();
  expect(await page.getByTestId("run-row").count()).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("link", { name: /opportunities_.*\.csv/ })).toHaveCount(0);   // no pile of per-run links
  const [xdl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ }).click()]);
  expect(xdl.suggestedFilename()).toMatch(/^clienthunt_all_runs_.*\.xlsx$/);
  const xlsxPath = `/tmp/ch-e2e-${Date.now()}.xlsx`;
  await xdl.saveAs(xlsxPath);                                                             // downloads have no extension by default
  const xl = sheetInfo(xlsxPath);
  expect(Object.keys(xl)).toEqual(["Summary", "Leads", "Opportunities", "Prospects", "Emails", "Runs"]);
  const flat = JSON.stringify(xl);
  expect(flat).toContain("jobs@acme.example");
  expect(flat).toContain("https://www.upwork.com/jobs/~0999");
  expect(flat).toContain("https://acme.example/jobs/1");
  expect(xl["Runs"].length).toBeGreaterThanOrEqual(3);                                    // header + the runs so far
  const [cdl] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /or as one CSV/ }).click()]);
  expect(fs.readFileSync((await cdl.path())!, "utf-8")).toContain("jobs@acme.example");

  // Live projects (stubbed Freelancer API): shown, ranked by chance, never stored
  await page.getByRole("button", { name: "Live projects" }).click();
  await expect(page.getByText(/do not allow storing its data/)).toBeVisible();
  await expect(page.getByRole("link", { name: /Stub LLM support agent/ })).toHaveAttribute("href", "https://www.freelancer.com/projects/machine-learning/Stub-LLM-support-agent-9001");
  await expect(page.getByText("few bids", { exact: true })).toBeVisible();
  await page.getByLabel("min hourly rate").fill("0");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("crowded", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Opportunities", exact: true }).click();
  await expect(page.getByText("Stub LLM support agent")).toHaveCount(0);                  // not in the opportunity list

  const again = await page.request.get("/api/export/all");
  const againPath = `/tmp/ch-e2e-again-${Date.now()}.xlsx`;
  fs.writeFileSync(againPath, await again.body());
  expect(JSON.stringify(sheetInfo(againPath))).not.toContain("Stub");                     // and not in the one-file export (parsed, not raw bytes)
  expect((await page.request.get("/api/opportunities")).ok()).toBeTruthy();
  expect(JSON.stringify(await (await page.request.get("/api/opportunities")).json())).not.toContain("Stub");

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

  // ---- Strategy: today's plan is built from the stored data and shows where the email was published
  await page.getByRole("button", { name: "Strategy", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Today" })).toBeVisible();
  await expect(page.getByText("jobs@acme.example", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "where it was published" })).toHaveAttribute("href", "https://acme.example/jobs/1");
  await expect(page.getByRole("heading", { name: "Why there is no Upwork scraper" })).toBeVisible();
  await expect(page.getByText(/Median \$/)).toHaveCount(0);                                                 // a rate is never invented
  await expect(page.getByText(/too few to say what the market pays/)).toBeVisible();
  await expect(page.getByRole("link", { name: /LD Talent ↗/ })).toHaveAttribute("href", "https://www.ldtalentwork.com/");
  await page.getByRole("button", { name: "Details / draft" }).first().click();
  await expect(page.getByRole("dialog", { name: "Opportunity detail" })).toBeVisible();
  await page.getByRole("button", { name: "✕ Close" }).click();

  // ---- Prospects: a company you choose; no network access is needed when "read their website now" is off
  await page.getByRole("button", { name: "Prospects", exact: true }).click();
  await expect(page.getByText(/No prospects yet/)).toBeVisible();
  await page.getByLabel("Websites, one per line").fill("northwind.example\nhttp://localhost:8000\njavascript:alert(1)");
  await page.getByLabel("What are they?").selectOption("agency");
  await page.getByLabel(/What it said/).fill("Offers staff augmentation and dedicated teams");
  await page.getByLabel("read their website now").uncheck();
  await page.getByRole("button", { name: "Add prospects" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Added or updated 1." })).toContainText("Private or local addresses are not allowed");
  const row = page.getByRole("row", { name: /Northwind/ });
  await expect(row).toContainText("Agency");
  await expect(row).toContainText("not read yet");
  expect((await (await page.request.get("/api/opportunities")).json()).total).toBe(2);              // prospects stay out of the job list
  expect((await (await page.request.get("/api/leads?has_email=false&hide_restricted=false")).json()).items.some((i: any) => i.source === "prospect")).toBe(false);
  await row.click();
  const pd = page.getByRole("dialog", { name: "Prospect detail" });
  await expect(pd.getByText("“Offers staff augmentation and dedicated teams”")).toBeVisible();
  await pd.getByRole("button", { name: "Draft a pitch" }).click();
  await expect(pd.getByLabel("draft v1")).toHaveValue(/If this is not relevant for you, please tell me and I will not write again\./);
  await expect(pd.getByRole("button", { name: "I sent this myself" })).toHaveCount(0);              // not before approval
  await pd.getByLabel("I reviewed these warnings").check();
  await pd.getByRole("button", { name: "Approve" }).click();
  await pd.getByRole("button", { name: "I sent this myself" }).click();
  await expect(pd.getByText("contacted", { exact: false }).first()).toBeVisible();
  await expect(pd.getByRole("button", { name: "Remove" })).toBeDisabled();                           // a contacted prospect stays in the record
  await pd.getByRole("button", { name: "✕ Close" }).click();

  // ---- Pipeline: the pitch is there, and your own follow-up can be logged
  await page.getByRole("button", { name: "Pipeline" }).click();
  const card = page.locator(".panel", { hasText: "Northwind" }).first();
  await expect(card).toContainText("their website");
  await card.getByLabel("note type").selectOption("out");
  await card.getByPlaceholder("Log what was said").fill("Follow-up sent");
  await card.getByRole("button", { name: "Add" }).click();
  await expect(card).toContainText("I wrote: Follow-up sent");

  // ---- the one-file download now carries the Prospects sheet with that company and its note
  const again2 = await page.request.get("/api/export/all");
  const p2 = `/tmp/ch-e2e-prospects-${Date.now()}.xlsx`;
  fs.writeFileSync(p2, await again2.body());
  const x2 = sheetInfo(p2);
  expect(x2["Prospects"].length).toBe(2);                                                              // header + Northwind
  expect(JSON.stringify(x2["Prospects"])).toContain("Offers staff augmentation and dedicated teams");
  expect(JSON.stringify(x2["Leads"])).not.toContain("northwind");
});
