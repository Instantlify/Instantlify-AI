import { expect, test, type Page } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

async function mockLanding(page: Page) {
  await mockApi(page);
  await page.route("**/api/public/plans/", (route) =>
    route.fulfill({ json: { plans: [], trial_days: 7 } }),
  );
}

test("the supplied animated logo loads and the landing header logo returns to the top", async ({
  page,
}) => {
  await mockLanding(page);
  await page.goto("/");
  const home = page
    .locator(".nm-nav")
    .getByRole("link", { name: "Nemio home", exact: true });
  const image = home.locator('img[src="/brand/nemio-ai-logo.gif"]');
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate(
        (element: HTMLImageElement) =>
          element.complete && element.naturalWidth === 900,
      ),
    )
    .toBe(true);
  await page.locator("#pricing").scrollIntoViewIfNeeded();
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(500);
  await home.click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page).toHaveURL(/\/$/);
  // Show a representative frame of the user-supplied animation for visual review.
  await page.waitForTimeout(2200);
  await page.screenshot({ path: "test-results/nemio-animated-logo.png" });
});

test("the footer logo also returns to the top with reduced motion", async ({
  page,
}) => {
  await mockLanding(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const home = page
    .locator("footer")
    .getByRole("link", { name: "Nemio home", exact: true });
  await home.scrollIntoViewIfNeeded();
  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(500);
  await home.click();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});

test("the portal rail uses the supplied logo and remains usable when expanded", async ({
  page,
}) => {
  await mockApi(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/w/${id}/overview/`);
  const sidebar = page.locator("#workspace-sidebar");
  await page.mouse.move(900, 100);
  await expect(sidebar.locator(".nemio-mark")).toBeVisible();
  await expect(sidebar.locator(".nemio-mark-image")).toHaveAttribute(
    "src",
    "/brand/nemio-ai-logo.gif",
  );
  await sidebar.hover();
  await expect(
    sidebar
      .getByRole("link", { name: "Home", exact: true })
      .locator(".nav-label-text"),
  ).toBeVisible();
});

test("Product dropdown closes on scrolling and outside clicks", async ({
  page,
}) => {
  await mockLanding(page);
  await page.goto("/");
  const menu = page.locator(".nm-mega");
  const trigger = menu.locator("summary");
  await trigger.click();
  await expect(menu).toHaveAttribute("open", "");
  await page.getByRole("heading", { level: 1 }).click();
  await expect(menu).not.toHaveAttribute("open");
  await trigger.click();
  await expect(menu).toHaveAttribute("open", "");
  await page.mouse.move(1100, 500);
  await page.mouse.wheel(0, 500);
  await expect(menu).not.toHaveAttribute("open");
});

test("Product dropdown closes on keyboard navigation links and Escape", async ({
  page,
}) => {
  await mockLanding(page);
  await page.goto("/");
  const menu = page.locator(".nm-mega");
  const trigger = menu.locator("summary");
  await trigger.click();
  await page.keyboard.press("Escape");
  await expect(menu).not.toHaveAttribute("open");
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(menu).toHaveAttribute("open", "");
  const pricing = page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Pricing", exact: true });
  await pricing.focus();
  await page.keyboard.press("Enter");
  await expect(menu).not.toHaveAttribute("open");
  await expect(page).toHaveURL(/#pricing$/);
});
