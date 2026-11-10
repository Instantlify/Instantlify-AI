import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

/** Deep links, the comment shield and the web chat widget read and write the API. */

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
});

test("deep links list the API's links and create new ones through it", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/deeplinks`);
  await expect(page.getByRole("cell", { name: /Profile link/ })).toBeVisible();
  await expect(page.getByText("/go/ig-profile/")).toBeVisible();
  await page.getByRole("button", { name: "Create deep link" }).click();
  await page
    .getByPlaceholder("e.g. Instagram VIP Profile Link")
    .fill("Order chat");
  await page.getByRole("dialog").getByRole("combobox").selectOption("whatsapp");
  await page
    .getByPlaceholder("https://wa.me/15550100200")
    .fill("https://wa.me/15550100200");
  await page.getByPlaceholder("e.g. vip-chat").fill("order-chat");
  await page.getByRole("button", { name: "Generate Smart Link" }).click();
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/deeplinks/"))?.body)
    .toEqual({
      title: "Order chat",
      platform: "whatsapp",
      target: "https://wa.me/15550100200",
      code: "order-chat",
      campaign: "",
      source: "",
      medium: "",
    });
  await expect(page.getByText("/go/order-chat/")).toBeVisible();
});

test("comment shield shows real rules and events and saves new rules", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/shield`);
  await expect(page.getByText("Matches: dm me, crypto")).toBeVisible();
  await expect(page.getByRole("cell", { name: /lead-9/ })).toBeVisible();
  await expect(page.getByText("Hidden automatically")).toBeVisible();
  await page.getByPlaceholder("e.g. Hate Speech & Slurs").fill("Refund spam");
  await page
    .getByPlaceholder("e.g. scam, liar, fraud, refund now")
    .fill("refund now, Scam");
  await page.getByRole("button", { name: "Add shield rule" }).click();
  await expect
    .poll(
      () => calls.find((call) => call.path.endsWith("/shield/rules/"))?.body,
    )
    .toEqual({
      name: "Refund spam",
      keywords: ["refund now", "scam"],
      // A keyword rule: no AI description and no public reply.
      prompt: "",
      reply_text: "",
      action: "hide",
    });
  await expect(page.getByText("Refund spam")).toBeVisible();
});

test("web chat settings load from the API and save back to it", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/webchat`);
  await expect(page.getByLabel("Widget Title")).toHaveValue(
    "Studio North chat",
  );
  await expect(page.getByText("/widget.js")).toBeVisible();
  await page.getByLabel("Widget Title").fill("Help desk");
  await page.getByRole("button", { name: "Save Widget Settings" }).click();
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/webchat/"))?.body)
    .toMatchObject({
      title: "Help desk",
      allowed_domains: ["example.com"],
      color: "#112233",
    });
  await expect(page.getByRole("status")).toContainText(
    "Web chat settings saved",
  );
});
