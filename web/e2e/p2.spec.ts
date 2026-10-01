/** P2 behind flags (brief 4.19): Prepare Call and the SIMULATED payment link, through the console. */
import { expect, test } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };

test("Prepare Call and a paid payment link", async ({ page, request, context }) => {
  expect((await request.post("/api/v1/admin/reset", { headers: ADMIN })).ok()).toBeTruthy();
  const flags = await request.patch("/api/v1/admin/settings", {
    headers: ADMIN,
    data: { feature_voice: true, feature_payment_link: true },
  });
  expect(flags.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByRole("button", { name: /Collector/ }).click();
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible(); // not still on Today
  await page.getByRole("link", { name: "ABC Distributors" }).click();

  await page.getByRole("button", { name: "Prepare call" }).click();
  const sheet = page.getByRole("dialog", { name: "Prepare call" });
  await expect(sheet).toContainText("owes ₹7,50,000");
  await expect(sheet).toContainText("INV-1021 for ₹4,00,000, due 11 Sep 2026");
  await expect(sheet).toContainText("Every figure on this sheet matches the ledger");
  await sheet.getByRole("button", { name: "Done" }).click();

  const invoices = page.getByRole("region", { name: "Invoices" });
  await invoices.getByRole("row", { name: /INV-1034/ }).getByRole("button", { name: "Payment link" }).click();
  const link = page.getByRole("status").getByRole("link");
  const url = await link.textContent();
  expect(url).toMatch(/#\/pay\/INV-1034\.\d+\.[0-9a-f]{32}$/);

  const customer = await context.newPage(); // a fresh tab with no role, as the customer would open it
  await customer.evaluate(() => localStorage.clear()).catch(() => undefined);
  await customer.goto(url ?? "");
  await expect(customer.getByRole("note")).toContainText("SIMULATED");
  await expect(customer.getByRole("heading", { name: "Pay INV-1034" })).toBeVisible();
  await customer.getByRole("button", { name: /Pay ₹2,00,000/ }).click();
  await expect(customer.getByRole("status")).toContainText("Paid ₹2,00,000");

  await page.reload();
  await expect(page.getByText("Total outstanding ₹5,50,000")).toBeVisible();
});
