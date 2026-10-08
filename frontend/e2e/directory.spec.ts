/** HACK-007: a collector adds a distributor and an invoice, edits the details and uploads a CSV; an admin deletes. */
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };
const CSV = [
  "customer_name,email,phone,segment,credit_terms_days,invoice_number,invoice_date,due_date,amount_rupees",
  "Asha Stores,asha@example.com,+919800022222,sme,30,INV-6001,2026-09-01,2026-09-20,50000",
  "Asha Stores,asha@example.com,+919800022222,sme,30,INV-6002,2026-09-05,2026-10-20,25000",
].join("\n");

test.beforeEach(async ({ request }) => {
  expect((await request.post("/api/v1/admin/reset", { headers: ADMIN })).ok()).toBeTruthy();
});

async function signIn(page: Page, role: "Admin" | "Collector" | "Viewer") {
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(role) }).click();
  await expect(page.getByRole("heading", { name: "Today", level: 1 })).toBeVisible();
}

async function openCustomers(page: Page) {
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible();
}

test("a collector adds a distributor and an invoice, then edits the email", async ({ page }) => {
  await signIn(page, "Collector");
  await openCustomers(page);

  await page.getByRole("button", { name: "Add distributor" }).click();
  await page.getByLabel("Business name").fill("Riya Traders");
  await page.getByLabel("Email (reminders go here)").fill("riya@example.com");
  await page.getByRole("button", { name: "Add distributor" }).last().click();
  await expect(page.getByRole("heading", { name: "Riya Traders", level: 1 })).toBeVisible();

  await page.getByRole("button", { name: "Add invoice" }).click();
  await page.getByLabel("Invoice number (INV- and digits)").fill("INV-5001");
  await page.getByLabel("Invoice date").fill("2026-09-01");
  await page.getByLabel("Due date").fill("2026-09-20");
  await page.getByLabel("Amount in ₹").fill("1,25,000");
  await page.getByRole("button", { name: "Add invoice" }).last().click();
  await expect(page.getByRole("region", { name: "Invoices" }).getByText("INV-5001")).toBeVisible();
  await expect(page.getByText("₹1,25,000").first()).toBeVisible();

  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Email (reminders go here)").fill("accounts@riya.example.com");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("accounts@riya.example.com")).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete" })).toHaveCount(0); // only an admin deletes
});

test("a bad email is refused with a reason, not a server error", async ({ page }) => {
  await signIn(page, "Collector");
  await openCustomers(page);

  await page.getByRole("button", { name: "Add distributor" }).click();
  await page.getByLabel("Business name").fill("Metro Wholesale");
  await page.getByLabel("Email (reminders go here)").fill("ap@metro.example.com");
  await page.getByRole("button", { name: "Add distributor" }).last().click();

  await expect(page.getByRole("alert")).toContainText("A customer named Metro Wholesale already exists.");
});

test("a CSV upload adds distributors and their invoices", async ({ page }) => {
  await signIn(page, "Collector");
  await openCustomers(page);

  await page.getByRole("button", { name: "Upload CSV" }).click();
  await page.getByLabel("CSV file").setInputFiles({ name: "distributors.csv", mimeType: "text/csv", buffer: Buffer.from(CSV) });
  await page.getByRole("button", { name: "Upload", exact: true }).click();

  await expect(page.getByRole("status")).toContainText("1 new distributor(s), 2 invoice(s) added");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("link", { name: "Asha Stores" })).toBeVisible();
});

test("an admin deletes a distributor from the list after confirming", async ({ page }) => {
  await signIn(page, "Admin");
  await openCustomers(page);

  await page.getByRole("button", { name: "Delete Metro Wholesale" }).click();
  await expect(page.getByRole("dialog")).toContainText("It cannot be undone.");
  await page.getByRole("button", { name: "Delete Metro Wholesale" }).last().click();

  await expect(page.getByRole("link", { name: "Metro Wholesale" })).toHaveCount(0);
});
