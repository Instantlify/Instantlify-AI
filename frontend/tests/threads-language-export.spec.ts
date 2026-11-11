import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { id, mockApi } from "./support/meta-mock";

for (const width of [390, 1440]) {
  test(`discussion replies expand inline with real nested replies at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    await mockApi(page);
    const post = {
      id: "thread",
      author: "Alex",
      body: "How do you structure a useful follow-up?",
      created_at: new Date().toISOString(),
      pinned: false,
      likes: 2,
      dislikes: 0,
      my_vote: 0,
      reply_count: 2,
      can_edit: false,
      can_delete: false,
      can_pin: false,
    };
    const replies = [
      {
        id: "r1",
        parent_id: null as string | null,
        author: "Alex",
        body: "Start with a clear next step.",
        created_at: post.created_at,
        can_delete: false,
      },
      {
        id: "r2",
        parent_id: "r1",
        author: "Maya",
        body: "And keep the message personal.",
        created_at: post.created_at,
        can_delete: false,
      },
    ];
    let target = "";
    await page.route("**/api/community/**", (route) => {
      if (route.request().url().includes("/replies/")) {
        if (route.request().method() === "POST") {
          const data = route.request().postDataJSON();
          target = data.parent_id;
          const created = {
            ...replies[0],
            id: "r3",
            parent_id: data.parent_id,
            body: data.body,
          };
          replies.push(created);
          return route.fulfill({ json: created, status: 201 });
        }
        return route.fulfill({
          json: { count: replies.length, results: replies },
        });
      }
      return route.fulfill({ json: { count: 1, results: [post] } });
    });
    await page.goto(`/w/${id}/forum/`);
    await page
      .getByRole("button", { name: "Replies (2)", exact: true })
      .click();
    const thread = page.getByRole("region", { name: "Discussion replies" });
    await expect(thread).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(thread.locator(".community-thread-branch")).toContainText(
      "And keep the message personal.",
    );
    await thread
      .getByRole("button", { name: "Reply to Maya", exact: true })
      .click();
    await thread
      .getByLabel("Your reply", { exact: true })
      .fill("That makes the handoff clearer.");
    await thread
      .getByRole("button", { name: "Post reply", exact: true })
      .click();
    await expect(
      thread.getByText("That makes the handoff clearer.", { exact: true }),
    ).toBeVisible();
    expect(target).toBe("r2");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/inline-thread-${width}.png`,
      fullPage: true,
    });
    await thread.getByRole("button", { name: "Hide replies" }).click();
    await expect(thread).toHaveCount(0);
  });
}

test("language menu matches the dark sidebar and supports selection and Escape", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/overview/`);
  await page.locator("#workspace-sidebar").hover();
  const trigger = page.locator(".sidebar-language > summary");
  await trigger.click();
  const menu = page.getByRole("menu", { name: "Language", exact: true });
  await expect(menu).toBeVisible();
  await expect(menu.getByRole("menuitemradio")).toHaveCount(6);
  await expect(menu).toHaveCSS("background-color", "rgb(17, 25, 29)");
  await menu.screenshot({ path: "test-results/language-menu-dark.png" });
  await menu
    .getByRole("menuitemradio", { name: "Español", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await trigger.click();
  await page.keyboard.press("Escape");
  await expect(page.locator(".sidebar-language")).not.toHaveAttribute(
    "open",
    "",
  );
  await expect(trigger).toBeFocused();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
});

test("workspace export downloads an Excel workbook rather than serializing JSON", async ({
  page,
}) => {
  await mockApi(page);
  const bytes = Buffer.from("PK-excel-download-fixture");
  await page.route("**/data-operations/**", (route) =>
    route.request().url().includes("/download/")
      ? route.fulfill({
          body: bytes,
          contentType:
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
      : route.fulfill({
          json: [
            {
              id: "export-one",
              kind: "export",
              status: "complete",
              error_code: "",
              created_at: "2026-11-11T00:00:00Z",
            },
          ],
        }),
  );
  await page.goto(`/w/${id}/settings/`);
  await page
    .getByRole("button", { name: "Data & privacy", exact: true })
    .click();
  await expect(
    page.getByText("An Excel workbook", { exact: false }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Download Excel", exact: true })
    .click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("instantlify-export-2026-11-11.xlsx");
  expect(readFileSync((await file.path())!)).toEqual(bytes);
});
