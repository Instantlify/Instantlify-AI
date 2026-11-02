import { test, expect } from "@playwright/test";
import { id, mockApi, manualLead } from "./support/meta-mock";

for (const width of [390, 1440]) {
  test(`incoming messages and note actions remain readable and reachable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    const calls = await mockApi(page);
    await page.goto(`/w/${id}/inbox?conversation=v-0`);
    for (const reload of [false, true]) {
      if (reload) await page.reload();
      const bubble = page.locator(".bubble.inbound").first();
      await expect(bubble).toBeVisible();
      for (const dark of [false, true]) {
        const style = await page.addStyleTag({
          content: `.boosend-inbox-layout { --text-primary: ${dark ? "#edf4f3" : "#0c1b3a"}; --bg-subtle: ${dark ? "#18252b" : "#f3f6fc"}; }`,
        });
        const ratio = await bubble.evaluate((el) => {
          const s = getComputedStyle(el);
          const luminance = (color: string) => {
            const rgb = color
              .match(/[\d.]+/g)!
              .slice(0, 3)
              .map(Number)
              .map((n) => {
                n /= 255;
                return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
              });
            return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
          };
          const fg = luminance(s.color),
            bg = luminance(s.backgroundColor);
          return (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05);
        });
        expect(ratio).toBeGreaterThanOrEqual(4.5);
        await style.evaluate((el) => el.parentNode?.removeChild(el));
      }
      await page
        .getByLabel("Internal note")
        .fill(`Readable note ${width} ${reload}`);
      const add = page.getByRole("button", { name: "Add note", exact: true });
      await add.scrollIntoViewIfNeeded();
      expect(
        await add.evaluate((el) => {
          const r = el.getBoundingClientRect();
          return el.contains(
            document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2),
          );
        }),
      ).toBe(true);
      await add.click();
      await expect
        .poll(() => calls.filter((c) => c.path.endsWith("/notes/")).length)
        .toBe(reload ? 2 : 1);
    }
  });

  test(`contact details contain focus and restore the opener at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    await mockApi(page);
    await page.goto(`/w/${id}/crm`);
    const opener = page.getByRole("button", { name: "Open Maya Chen" });
    await opener.click();
    const dialog = page.getByRole("dialog", { name: "Contact Maya Chen" });
    await dialog.getByLabel("Contact name").focus();
    await page.keyboard.press("Shift+Tab");
    await expect
      .poll(() => dialog.evaluate((el) => el.contains(document.activeElement)))
      .toBe(true);
    const last = dialog.locator("button").last();
    await last.focus();
    await page.keyboard.press("Tab");
    await expect(dialog.getByLabel("Contact name")).toBeFocused();
    await expect(dialog).toHaveJSProperty("open", true);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
  });
}

test("form provenance appears in the contact badge and merge choices after reload", async ({
  page,
}) => {
  await mockApi(page);
  const form = {
    ...manualLead,
    id: "l-form",
    name: "Form Contact",
    fields: { source: "form", form: "qa-form" },
  };
  await page.route(`**/api/workspaces/${id}/leads/?**`, (route) =>
    route.fulfill({ json: { results: [form, manualLead], count: 2 } }),
  );
  await page.goto(`/w/${id}/crm`);
  for (const reload of [false, true]) {
    if (reload) await page.reload();
    await page.getByRole("button", { name: "Open Form Contact" }).click();
    await expect(
      page.getByRole("dialog").getByText("Added via form", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Open Priya Shah" }).click();
    await expect(
      page
        .getByLabel("Merge a duplicate into this contact")
        .locator('option[value="l-form"]'),
    ).toContainText("Added via form");
    await page.keyboard.press("Escape");
  }
});
