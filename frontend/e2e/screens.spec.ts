/** Screen-level acceptance criteria (S-01 to S-17) through the console against a running stack. */
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/v1/admin/reset", { headers: ADMIN })).ok()).toBeTruthy();
});

async function signIn(page: Page, role: "Admin" | "Collector" | "Viewer") {
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(role) }).click();
  await expect(page.getByRole("heading", { name: "Today", level: 1 })).toBeVisible();
}

async function openCustomer(page: Page, name: string) {
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible();
  await page.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
}

// TC-0168 (AC-US-00-003-4): an attention group with nothing in it keeps its place and says so. The reset stack has
// open disputes, so the empty group checked is "Today's promises and ready reminders".
test("an empty attention group shows its empty state", async ({ page }) => {
  await signIn(page, "Viewer");
  const group = page.getByRole("region", { name: "Today's promises and ready reminders" });
  await expect(group).toBeVisible();
  await expect(group.getByText("No promise is due today and nothing is waiting to send.")).toBeVisible();
});

// TC-0169 (AC-US-00-004-1): a customer with no history still shows every section, each with an empty state.
test("a customer with no history shows every section with empty states", async ({ page }) => {
  await signIn(page, "Viewer");
  await openCustomer(page, "Ganesh Traders");
  for (const label of ["Outstanding", "Oldest overdue", "Priority", "Next action"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  for (const title of ["Why is this customer", "Timeline", "Invoices", "Promises", "Disputes"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "Promises" }).getByText("No promises recorded.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Disputes" }).getByText("No disputes.")).toBeVisible();
  await page.getByRole("tab", { name: /Messages and runs/ }).click();
  for (const title of ["Messages", "Agent runs"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "Agent runs" }).getByText("The agent has not run for this customer.")).toBeVisible();
});

// TC-0193 (AC-US-00-009-1): the approval queue shows everything needed to decide, beside the draft.
test("a queued draft shows its full context", async ({ page }) => {
  await signIn(page, "Admin");
  await openCustomer(page, "ABC Distributors");
  await page.getByRole("button", { name: "Run agent now" }).click();
  await page.getByRole("button", { name: "Close" }).click();
  await page.getByRole("link", { name: "Approvals" }).click();
  await page.getByRole("button", { name: /ABC Distributors/ }).first().click();

  const context = page.getByRole("region", { name: "Draft context" });
  await expect(context.getByText("₹7,50,000").first()).toBeVisible();
  for (const invoice of ["INV-1021", "INV-1034", "INV-1047"]) await expect(context.getByText(invoice)).toBeVisible();
  await expect(context.getByText(/days overdue/).first()).toBeVisible();
  await expect(context.getByText(/missed promise/i).first()).toBeVisible(); // a priority reason
  await expect(page.getByText(/· email ·/).first()).toBeVisible(); // channel
  await expect(page.getByText(/reminder · (gentle|firm|final)/).first()).toBeVisible(); // tone
  await expect(page.getByRole("button", { name: "View run" })).toBeVisible(); // trajectory
});

// TC-0223 (AC-US-00-020-4): a missed promise is flagged on Today and on the customer, with a follow-up proposed.
test("a missed promise shows a warning and proposes a follow-up", async ({ page }) => {
  await signIn(page, "Admin");
  const missed = page.getByRole("region", { name: "Missed promises" });
  await expect(missed.getByText("⚠").first()).toBeVisible();
  await expect(missed.getByRole("link", { name: "Kumar Electricals" }).first()).toBeVisible();
  await missed.getByRole("link", { name: "Kumar Electricals" }).first().click();
  await expect(page.getByRole("heading", { name: "Kumar Electricals", level: 1 })).toBeVisible();
  // The worker's daily run may already have drafted the follow-up; then reviewing it is the next action.
  await expect(page.getByText(/^(Send follow-up on missed promise|Review the draft in Approvals)$/)).toBeVisible();

  await page.getByRole("button", { name: "Run agent now" }).click();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Review the draft in Approvals")).toBeVisible();
  await page.getByRole("tab", { name: /Messages and runs/ }).click();
  await expect(page.getByRole("region", { name: "Messages" }).getByText(/pending approval/i).first()).toBeVisible();
});

// TC-0225 (AC-US-00-022-3): the timeline runs in time order; every event has an icon and an actor label.
test("the timeline is ordered and every event names its actor", async ({ page }) => {
  await signIn(page, "Viewer");
  await openCustomer(page, "ABC Distributors");
  const events = page.getByRole("region", { name: "Timeline" }).getByRole("listitem");
  const n = await events.count();
  expect(n).toBeGreaterThan(1);
  const stamps: string[] = [];
  for (let i = 0; i < n; i++) {
    const meta = (await events.nth(i).locator("div").last().innerText()).trim();
    expect(meta).toMatch(/^(AI|Human|System|Customer)\b/);
    await expect(events.nth(i).locator("span[aria-hidden] svg")).toHaveCount(1); // the event icon
    stamps.push(meta.split(" · ").at(-1) ?? "");
  }
  const times = stamps.map((s) => Date.parse(s.replace(/,/, "")));
  const ascending = times.every((t, i) => i === 0 || Number.isNaN(t) || Number.isNaN(times[i - 1]) || t >= times[i - 1]);
  const descending = times.every((t, i) => i === 0 || Number.isNaN(t) || Number.isNaN(times[i - 1]) || t <= times[i - 1]);
  expect(ascending || descending).toBeTruthy();
});

// TC-0236 (AC-US-01-006-2): Admin shows the sending state, autonomy mode, spend against budget, runs and failures.
test("the admin page shows sending, mode, spend, runs and guardrail failures", async ({ page }) => {
  await signIn(page, "Admin");
  await page.getByRole("link", { name: "Admin" }).click();
  await expect(page.getByRole("heading", { name: "Admin", level: 1 })).toBeVisible();
  for (const title of ["Kill switch", "Autonomy", "LLM spend"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }
  await expect(page.getByRole("region", { name: "LLM spend" }).getByText(/\$/).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Autonomy" }).getByText(/Manual/i).first()).toBeVisible();
  await page.getByRole("tab", { name: "Activity" }).click();
  for (const title of ["Recent runs", "Guardrail events"]) {
    await expect(page.getByRole("region", { name: title })).toBeVisible();
  }
});
