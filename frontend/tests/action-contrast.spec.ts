import { expect, test, type Locator } from "@playwright/test";
import { colorContrast } from "../lib/workspace-theme";
import { id, mockApi, workspace } from "./support/meta-mock";

async function contrast(element: Locator) {
  const colors = await element.evaluate((el) => {
    const hex = (rgb: string) =>
      "#" +
      (rgb.match(/[\d.]+/g) || [])
        .slice(0, 3)
        .map((value) => Math.round(Number(value)).toString(16).padStart(2, "0"))
        .join("");
    const style = getComputedStyle(el);
    let parent: Element | null = el;
    let background = style.backgroundColor;
    while (
      parent &&
      (background === "rgba(0, 0, 0, 0)" || background === "transparent")
    ) {
      parent = parent.parentElement;
      if (parent) background = getComputedStyle(parent).backgroundColor;
    }
    return { foreground: hex(style.color), background: hex(background) };
  });
  return colorContrast(colors.foreground, colors.background);
}

for (const primary of ["#b4f277", "#7c3aed", "#bb8877", "#777777"]) {
  test(`workflow text and action states remain readable with ${primary}`, async ({
    page,
  }) => {
    await mockApi(page);
    await page.route("**/api/workspaces/", (route) =>
      route.fulfill({
        json: {
          results: [
            {
              ...workspace,
              branding: {
                ...workspace.branding,
                primary_color: primary,
                sidebar_bg_color: "#0e161a",
                sidebar_text_color: "#dce6e5",
              },
            },
          ],
          count: 1,
        },
      }),
    );
    await page.goto(`/w/${id}/automations/`);
    await page.getByRole("button", { name: "Templates", exact: true }).click();
    const hero = page.locator(".speak-to-generate-hero-card");
    await expect(hero).toBeVisible();
    const headingColor = await hero
      .locator("h2")
      .evaluate((el) => getComputedStyle(el).color);
    const descriptionColor = await hero
      .locator("p")
      .evaluate((el) => getComputedStyle(el).color);
    expect(headingColor).toBe("rgb(237, 244, 243)");
    expect(descriptionColor).toBe("rgb(193, 207, 206)");
    const generate = page.getByRole("button", {
      name: "Generate",
      exact: true,
    });
    await expect(generate).toBeDisabled();
    expect(await contrast(generate)).toBeGreaterThanOrEqual(4.5);
    await page
      .getByLabel("Describe the automation")
      .fill("Send a guide when someone comments LEADS");
    await expect(generate).toBeEnabled();
    const actions = [
      generate,
      ...(await page.locator(".import-template-btn").all()),
    ];
    expect(actions.length).toBeGreaterThan(1);
    for (const action of actions) {
      expect(await contrast(action)).toBeGreaterThanOrEqual(4.5);
      await action.hover();
      await expect.poll(() => contrast(action)).toBeGreaterThanOrEqual(4.5);
      await action.focus();
      expect(await contrast(action)).toBeGreaterThanOrEqual(4.5);
    }
    if (primary === "#b4f277")
      await page.screenshot({
        path: "test-results/workflow-contrast-desktop.png",
        fullPage: true,
      });
    if (primary === "#b4f277") {
      await page.setViewportSize({ width: 390, height: 850 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: "test-results/workflow-contrast-mobile.png",
        fullPage: true,
      });
      await page.setViewportSize({ width: 1280, height: 720 });
    }
    // Exercise the other affected shared action classes with their actual loaded styles.
    await page.locator("[data-workspace-theme]").evaluate((el) => {
      const probe = document.createElement("section");
      probe.id = "contrast-probes";
      for (const className of [
        "save-changes-black-btn",
        "update-password-btn",
        "add-black-btn",
        "upgrade-plan-black-btn",
      ]) {
        const button = document.createElement("button");
        button.className = className;
        button.textContent = className;
        probe.appendChild(button);
      }
      el.appendChild(probe);
    });
    for (const action of await page.locator("#contrast-probes button").all()) {
      expect(await contrast(action)).toBeGreaterThanOrEqual(4.5);
      await action.hover();
      await expect.poll(() => contrast(action)).toBeGreaterThanOrEqual(4.5);
    }
  });
}

test("workspace text buttons retain contrast across screens", async ({
  page,
}) => {
  await mockApi(page);
  test.setTimeout(90000);
  const failures: string[] = [];
  for (const path of [
    "overview",
    "automations",
    "crm",
    "integrations",
    "app-store",
    "settings",
  ]) {
    await page.goto(`/w/${id}/${path}/`);
    await expect(page.locator("[data-workspace-theme]")).toBeVisible();
    await page.addStyleTag({
      content:
        "*, *::before, *::after { transition: none !important; animation: none !important; }",
    });
    const ids = await page.locator("main button").evaluateAll((buttons) =>
      buttons.map((button, index) => {
        button.setAttribute("data-contrast-id", String(index));
        return index;
      }),
    );
    for (const index of ids) {
      const button = page.locator(`[data-contrast-id="${index}"]`);
      if (!(await button.isVisible()) || !(await button.isEnabled())) continue;
      const text = (await button.innerText()).trim();
      if (!text) continue;
      const normal = await contrast(button);
      await button.hover();
      const hover = await contrast(button);
      if (Math.min(normal, hover) < 4.5)
        failures.push(
          `${path}: ${text}: normal=${normal.toFixed(2)}, hover=${hover.toFixed(2)}`,
        );
    }
  }
  expect(failures).toEqual([]);
});
