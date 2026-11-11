import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { id, mockApi } from "./support/meta-mock";

for (const width of [390, 1440]) {
  test(`channel confirmations cancel safely and approve once at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    const calls = await mockApi(page);
    let nativeDialogs = 0;
    page.on("dialog", async (dialog) => {
      nativeDialogs++;
      await dialog.dismiss();
    });
    await page.goto(`/w/${id}/integrations/?tab=channels`);
    const disconnect = page
      .getByRole("button", { name: "Disconnect", exact: true })
      .first();
    const requests = () =>
      calls.filter((call) => call.path.endsWith("/disconnect/"));
    await disconnect.click();
    const dialog = page.getByRole("alertdialog", {
      name: "Disconnect?",
      exact: true,
    });
    await expect(dialog).toContainText("Instantlify");
    await expect(dialog).toContainText("Disconnect studio.north?");
    await expect(
      dialog.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    if (width === 390)
      await page.screenshot({
        path: "test-results/instantlify-confirmation-mobile.png",
      });
    expect(requests()).toHaveLength(0);
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(disconnect).toBeFocused();
    expect(requests()).toHaveLength(0);
    await disconnect.click();
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    expect(requests()).toHaveLength(0);
    await disconnect.click();
    await dialog
      .getByRole("button", { name: "Disconnect", exact: true })
      .click();
    await expect.poll(() => requests().length).toBe(1);
    expect(nativeDialogs).toBe(0);
  });
}

test("admin confirmations cancel and preserve the approved form submitter", async ({
  page,
}) => {
  const template = readFileSync(
    path.resolve(
      __dirname,
      "../../backend/apps/platform_ops/templates/platform_ops/console.html",
    ),
    "utf8",
  );
  const fragment = template.slice(
    template.indexOf('<dialog id="console-confirmation"'),
    template.lastIndexOf("</body>"),
  );
  await page.setContent(
    `<form id="test-form"><button name="action" value="delete" data-confirm="Delete this tier?">Delete tier</button></form><output id="result"></output>${fragment}`,
  );
  await page.evaluate(() => {
    document
      .getElementById("test-form")!
      .addEventListener("submit", (event) => {
        if (event.defaultPrevented) return;
        event.preventDefault();
        const submitter = (event as SubmitEvent).submitter as HTMLButtonElement;
        document.getElementById("result")!.textContent +=
          `${submitter.name}:${submitter.value};`;
      });
  });
  await page.getByRole("button", { name: "Delete tier", exact: true }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toContainText("Delete this tier?");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator("#result")).toHaveText("");
  await page.getByRole("button", { name: "Delete tier", exact: true }).click();
  await dialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.locator("#result")).toHaveText("action:delete;");
});
