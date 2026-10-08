/** HACK-009 against a stack with no Google client set up: the console says so plainly and nothing breaks. The
 * connected flows are covered against a faked Google in backend/tests/service/test_google.py. */
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

test("the Admin page says Google is not set up yet", async ({ page }) => {
  await signIn(page, "Admin");
  await page.getByRole("link", { name: "Admin" }).click();

  const panel = page.getByRole("region", { name: "Google (Gmail and Calendar)" });
  await expect(panel).toContainText("Not connected");
  await expect(panel).toContainText("Google is not set up on the server");
  await expect(panel.getByRole("button", { name: "Connect Google" })).toHaveCount(0);
});

test("incoming replies is empty and a check explains what is missing", async ({ page }) => {
  await signIn(page, "Collector");
  await page.getByRole("link", { name: "Incoming replies" }).click();

  await expect(page.getByRole("heading", { name: "Incoming replies", level: 1 })).toBeVisible();
  await expect(page.getByText("No replies waiting.")).toBeVisible();
  await page.getByRole("button", { name: "Check for replies" }).click();
  await expect(page.getByRole("alert")).toContainText("Google is not set up");
});

test("a viewer sees the queue but cannot check or act", async ({ page }) => {
  await signIn(page, "Viewer");
  await page.getByRole("link", { name: "Incoming replies" }).click();

  await expect(page.getByRole("button", { name: "Check for replies" })).toHaveCount(0);
});
