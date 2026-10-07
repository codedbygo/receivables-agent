/** HACK-003: the collections employee screens through the console. Why? factors, a SIMULATED AI call that records
 * the brief's promise, the customer portal (valid and invalid links), the CFO view and the AI Safety Center. */
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };

async function openAbc(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: /Collector/ }).click();
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible();
  await page.getByRole("link", { name: "ABC Distributors" }).click();
}

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/v1/admin/reset", { headers: ADMIN })).ok()).toBeTruthy();
  const flags = await request.patch("/api/v1/admin/settings", {
    headers: ADMIN,
    data: { feature_voice: true, feature_payment_link: true },
  });
  expect(flags.ok()).toBeTruthy();
});

test("priority Why? and a SIMULATED AI call that records the promise", async ({ page }) => {
  await openAbc(page);
  const why = page.getByRole("region", { name: /Why is this customer HIGH priority/ });
  await expect(why).toContainText("Overdue outstanding");
  await expect(why).toContainText("₹7,50,000");
  await expect(why).toContainText("not model reasoning");

  await page.getByRole("tab", { name: /Messages and runs/ }).click(); // calls moved to this tab in 38f83eb (HACK-004)
  const calls = page.getByRole("region", { name: "Voice calls" });
  await calls.getByRole("button", { name: "Call with AI" }).click();
  await expect(calls).toContainText(/simulated: no phone rang/i);
  await expect(calls).toContainText("₹7,50,000");
  await calls.getByLabel("What the customer says").fill("We can pay ₹2 lakh this Friday.");
  await calls.getByRole("button", { name: "Send" }).click();
  await expect(calls).toContainText("recorded a payment promise of ₹2,00,000");
  await calls.getByLabel("What the customer says").fill("Yes please");
  await calls.getByRole("button", { name: "Send" }).click();
  await expect(calls).toContainText("Promise amount: ₹2,00,000");
});

test("the customer portal shows one customer and refuses a bad link", async ({ page, context }) => {
  await openAbc(page);
  const contact = page.getByRole("region", { name: "Contact" });
  await contact.getByRole("button", { name: "Create link" }).click();
  const url = await contact.getByRole("link").filter({ hasText: "#/portal/" }).textContent();

  const customer = await context.newPage();
  await customer.goto(url ?? "");
  await expect(customer.getByRole("heading", { name: "ABC Distributors" })).toBeVisible();
  await expect(customer.getByRole("note")).toContainText("SIMULATED");
  await expect(customer.getByText("INV-1047")).toBeVisible();
  await customer.getByRole("button", { name: "Promise to pay" }).click();
  await customer.getByLabel(/Amount in rupees/).fill("300000");
  await customer.getByLabel("Payment date").fill("2026-10-05");
  await customer.getByRole("button", { name: "Confirm promise" }).click();
  await expect(customer.getByRole("status")).toContainText("Your promise is recorded");

  await customer.goto("/#/portal/" + "x".repeat(43));
  await expect(customer.getByText(/not valid/)).toBeVisible();
});

test("CFO view and AI Safety Center read from the ledger and the event log", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Viewer/ }).click();
  await page.getByRole("link", { name: "CFO view" }).click();
  await expect(page.getByRole("heading", { name: "CFO view" })).toBeVisible();
  await expect(page.getByText("Total receivables", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "What needs attention today?" })).toContainText("ABC Distributors");

  await page.getByRole("link", { name: "AI Safety" }).click();
  await expect(page.getByText("Automatic sends", { exact: true })).toBeVisible();
  await expect(page.getByText(/ready \(sending on\)|engaged \(sending paused\)/i)).toBeVisible();
});
