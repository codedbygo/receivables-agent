/** TC-0271 (AC-US-00-023-4): every screen meets WCAG AA colour contrast in the light and the dark theme. */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const ADMIN = { "X-Demo-Role": "admin" };
const SCREENS: { name: string; open: (page: Page) => Promise<void> }[] = [
  { name: "Today", open: async () => {} },
  { name: "Approvals", open: async (page) => page.getByRole("link", { name: "Approvals" }).click() },
  { name: "Customers", open: async (page) => page.getByRole("link", { name: "Customers" }).click() },
  {
    name: "Customer",
    open: async (page) => {
      await page.getByRole("link", { name: "Customers" }).click();
      await expect(page.getByRole("heading", { name: "Customers", level: 1 })).toBeVisible();
      await page.getByRole("link", { name: "ABC Distributors" }).click();
    },
  },
  { name: "Evaluation", open: async (page) => page.getByRole("link", { name: "Evaluation" }).click() },
  { name: "Admin", open: async (page) => page.getByRole("link", { name: "Admin" }).click() },
];

test.beforeAll(async ({ request }) => {
  expect((await request.post("/api/v1/admin/reset", { headers: ADMIN })).ok()).toBeTruthy();
});

for (const theme of ["light", "dark"] as const) {
  for (const screen of SCREENS) {
    test(`${screen.name} has AA contrast in the ${theme} theme`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("ca.theme", t), theme);
      await page.goto("/");
      await page.getByRole("button", { name: /Admin/ }).click();
      await expect(page.getByRole("heading", { name: "Today", level: 1 })).toBeVisible();
      await screen.open(page);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => document.documentElement.getAttribute("data-theme"))).toBe(theme);

      const result = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
      const failures = result.violations.flatMap((v) => v.nodes.map((n) => `${n.target.join(" ")}: ${n.failureSummary}`));
      expect(failures, failures.join("\n")).toEqual([]);
    });
  }
}
