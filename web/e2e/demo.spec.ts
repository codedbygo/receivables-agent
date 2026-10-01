/** The ABC demo story (brief 4.24, REQ-110) through the console against a running stack. */
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };

async function openAbc(page: Page) {
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible(); // not still on Today
  await page.getByRole("link", { name: "ABC Distributors" }).click();
  await expect(page.getByRole("heading", { name: "ABC Distributors", level: 1 })).toBeVisible();
}

async function recordReply(page: Page, text: string) {
  await page.getByRole("button", { name: "Record a reply" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Paste what the customer wrote").fill(text);
  await dialog.getByRole("button", { name: "Record and classify" }).click();
  return dialog;
}

// TC-0192 (AC-US-00-008-3)
test("ABC Distributors: reminder, approval, promise, payment, dispute", async ({ page, request }) => {
  const reset = await request.post("/api/v1/admin/reset", { headers: ADMIN });
  expect(reset.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByRole("button", { name: /Admin/ }).click();
  await expect(page.getByRole("heading", { name: "Today", level: 1 })).toBeVisible();
  await expect(page.getByText("30 Sep 2026").first()).toBeVisible();

  // Selected with reasons, from the ledger.
  await openAbc(page);
  await expect(page.getByText("Total outstanding ₹7,50,000")).toBeVisible();
  await expect(page.getByRole("region", { name: "Why this priority" })).toContainText("missed promise");

  // The bounded agent drafts; the trajectory is visible.
  await page.getByRole("button", { name: "Run agent now" }).click();
  const run = page.getByRole("dialog", { name: "Agent run" });
  await expect(run).toContainText("Wait for approval");
  await expect(run).toContainText("draft_message");
  await run.getByRole("button", { name: "Close" }).click();

  // Guardrails verified every figure; a human approves.
  await page.getByRole("link", { name: "Approvals" }).click();
  await page.getByRole("list", { name: "Drafts" }).getByRole("button", { name: /ABC Distributors/ }).first().click();
  const report = page.getByRole("complementary", { name: "Guardrail report" });
  await expect(report).toContainText("Every figure matches the ledger");
  await expect(page.getByRole("article")).toContainText("₹7,50,000");
  await page.getByRole("button", { name: /^Approve/ }).click();

  // The worker sends it.
  await openAbc(page);
  await expect(async () => {
    await page.reload();
    // "Record a reply" appears only once a message's status is sent.
    await expect(page.getByRole("button", { name: "Record a reply" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 60_000 });

  // The customer promises ₹3 lakh on 5 October.
  let dialog = await recordReply(page, "We can pay ₹3 lakh on October 5 and the remaining amount later.");
  await expect(dialog).toContainText("Promise");
  await expect(dialog).toContainText("₹3,00,000");
  await expect(dialog).toContainText("05 Oct 2026");
  await dialog.getByRole("button", { name: "Done" }).click();

  // The clock moves; the bank credit arrives and is matched.
  await page.getByRole("link", { name: "Admin" }).click();
  await page.getByRole("button", { name: "Advance the clock" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Days to advance (1 to 60)").fill("5");
  await dialog.getByRole("button", { name: "Advance 5 days" }).click();
  await expect(page.getByText("05 Oct 2026").first()).toBeVisible();

  await page.getByRole("button", { name: "Simulate a bank credit" }).click();
  dialog = page.getByRole("dialog");
  await dialog.getByLabel("Customer").selectOption({ label: "ABC Distributors (₹7,50,000 outstanding)" });
  await dialog.getByLabel(/Amount in rupees/).fill("300000");
  await dialog.getByLabel("Bank reference").fill("NEFT ABC Distributors UTR 4411");
  await dialog.getByRole("button", { name: "Post credit" }).click();
  await expect(dialog).toContainText("Matched");
  await dialog.getByRole("button", { name: "Done" }).click();

  await openAbc(page);
  await expect(page.getByText("Total outstanding ₹4,50,000")).toBeVisible();
  await expect(page.getByRole("region", { name: "Promises" })).toContainText("Fulfilled");

  // A dispute is detected and escalated to a human.
  dialog = await recordReply(page, "INV-1047 was billed for 50 units but we received only 40. Please correct it.");
  await expect(dialog).toContainText("Dispute");
  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("region", { name: "Disputes" })).toContainText("INV-1047");
  const timeline = page.getByRole("region", { name: "Timeline" });
  for (const kind of ["promise fulfilled", "payment received", "classified", "sent", "approved"]) {
    await expect(timeline).toContainText(kind);
  }
});

test("Evaluation page shows the generated numbers", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Viewer/ }).click();
  await page.getByRole("link", { name: "Evaluation" }).click();
  await expect(page.getByText("Red team rejected")).toBeVisible();
  await expect(page.getByText("18/18")).toBeVisible();
});
