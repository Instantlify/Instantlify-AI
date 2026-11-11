import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

for (const width of [390, 1440]) {
  test(`community layout, composer and subtle brand motion work at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    await mockApi(page);
    const posts = [
      {
        id: "first",
        author: "Alex Morgan",
        body: "A small workflow that made a big difference: start with one clear question, collect an email with consent, and follow up with something useful.",
        likes: 8,
        reply_count: 3,
        pinned: true,
      },
      {
        id: "second",
        author: "Maya Chen",
        body: "What is your approach to keeping customer handoffs personal when an automation starts the conversation?",
        likes: 4,
        reply_count: 2,
        pinned: false,
      },
    ].map((post) => ({
      ...post,
      created_at: new Date().toISOString(),
      dislikes: 0,
      my_vote: 0,
      can_edit: false,
      can_delete: false,
      can_pin: false,
    }));
    let submitted = "";
    await page.route("**/api/community/**", (route) => {
      if (route.request().url().includes("/assistant/"))
        return route.fulfill({
          json: {
            answer: "Start with a clear question and a consented follow-up.",
            sources: [],
          },
        });
      if (route.request().method() === "POST") {
        submitted = route.request().postDataJSON().body;
        posts.unshift({
          ...posts[0],
          id: "new",
          body: submitted,
          pinned: false,
        });
      }
      return route.fulfill({ json: { count: posts.length, results: posts } });
    });
    await page.goto(`/w/${id}/forum/`);
    await expect(page.locator(".community-post")).toHaveCount(2);
    await expect(page.getByLabel("Your post", { exact: true })).toHaveCount(0);
    const feed = await page.locator(".community-feed").boundingBox();
    const sidebar = await page.locator(".community-sidebar").boundingBox();
    if (width > 760) expect(sidebar!.x).toBeGreaterThan(feed!.x + feed!.width);
    else expect(sidebar!.y).toBeGreaterThanOrEqual(feed!.y + feed!.height);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    const mark = page.locator(".instantlify-mark-image").first();
    await expect(mark).toHaveCSS("animation-name", "instantlify-spark");
    await page.mouse.move(width - 20, 100);
    if (width > 760)
      await expect
        .poll(() =>
          page
            .locator("#workspace-sidebar")
            .evaluate((el) => el.getBoundingClientRect().width),
        )
        .toBeLessThan(100);
    await page.screenshot({
      path: `test-results/community-redesign-${width}.png`,
      fullPage: true,
    });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(mark).toHaveCSS("animation-name", "none");
    await page
      .getByRole("button", { name: "Start a discussion", exact: true })
      .click();
    const composer = page.getByRole("dialog", {
      name: "Start a discussion",
      exact: true,
    });
    await composer
      .getByLabel("Your post", { exact: true })
      .fill("A useful workflow to share.");
    await composer
      .getByRole("button", { name: "Post discussion", exact: true })
      .click();
    await expect(composer).toHaveCount(0);
    expect(submitted).toBe("A useful workflow to share.");
    await expect(page.getByText(submitted, { exact: true })).toBeVisible();
    await page
      .getByLabel("Ask the community assistant", { exact: true })
      .fill("How should I start?");
    await page
      .getByRole("button", { name: "Search discussions", exact: true })
      .click();
    await expect(
      page.getByText("Start with a clear question and a consented follow-up.", {
        exact: true,
      }),
    ).toBeVisible();
  });
}
