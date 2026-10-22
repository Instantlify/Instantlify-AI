import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

/** The CRM is the people who message connected Meta accounts: real profiles in the
 * table, and a contact panel that leads somewhere (chat, tags, notes, cleanup). */

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
});

test("contacts show their Meta profile and open a panel that leads to the chat", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/crm`);
  await expect(page.getByRole("heading", { name: "Contacts" })).toBeVisible();
  await expect(page.getByText("4 contacts")).toBeVisible();
  // Handle under the name, the photo for the one contact that has one.
  const maya = page.getByRole("button", { name: "Open Maya Chen" });
  await expect(maya).toContainText("@maya.chen");
  await expect(maya.locator("img")).toHaveAttribute(
    "src",
    "https://cdn.example.com/maya.jpg",
  );
  await expect(page.getByTitle("Instagram · studio.north")).toHaveCount(2);

  await maya.click();
  const panel = page.getByRole("dialog", { name: "Contact Maya Chen" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("link", { name: "Open chat" })).toHaveAttribute(
    "href",
    /\/inbox\/?\?conversation=v-0$/,
  );
  await expect(panel.getByText("studio.north")).toBeVisible();
  await expect(panel.getByText("Instagram · ID ext-0")).toBeVisible();
  await expect(panel.getByText("Is the guide still available?")).toHaveCount(0);
  await expect(
    panel.getByText("Thanks! Reply with your email for the guide."),
  ).toBeVisible();
  await expect(panel.getByText("Lahore")).toBeVisible();

  // Tags and fields patch the lead.
  await panel.getByLabel("New tag").fill("vip");
  await panel.getByRole("button", { name: "Add tag" }).click();
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/leads/l-0/"))?.body)
    .toEqual({ tags: ["hot", "vip"] });
  await expect(panel.getByText("vip", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Remove tag hot" }).click();
  await expect
    .poll(
      () =>
        calls.filter((call) => call.path.endsWith("/leads/l-0/")).at(-1)?.body,
    )
    .toEqual({ tags: ["vip"] });

  // Stage and assignment.
  await panel.getByLabel("Stage").selectOption("qualified");
  await expect
    .poll(
      () =>
        calls.filter((call) => call.path.endsWith("/leads/l-0/")).at(-1)?.body,
    )
    .toEqual({ stage: "qualified" });
  await panel.getByLabel("Assigned to").selectOption("1");
  await expect
    .poll(
      () =>
        calls.find((call) => call.path.endsWith("/conversations/v-0/"))?.body,
    )
    .toEqual({ assigned_to: 1 });
  await expect(page.getByRole("row", { name: /Maya Chen/ })).toContainText(
    "Alex Morgan",
  );

  // A private note goes to the conversation.
  await panel.getByLabel("New note").fill("Wants the spring guide");
  await panel.getByRole("button", { name: "Add note" }).click();
  await expect
    .poll(
      () =>
        calls.find((call) => call.path.endsWith("/conversations/v-0/notes/"))
          ?.body,
    )
    .toEqual({ text: "Wants the spring guide" });

  // Refresh pulls the profile from the channel.
  await panel.getByRole("button", { name: "Refresh profile" }).click();
  await expect(panel.getByRole("status")).toContainText("Profile refreshed");
  expect(calls.some((call) => call.path.endsWith("/leads/l-0/refresh/"))).toBe(
    true,
  );
  await page.screenshot({
    path: "test-results/crm-contact-panel.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("a contact added by hand explains what comes next and can be merged or deleted", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/crm`);
  await page.getByRole("button", { name: "Filter" }).click();
  await page.getByRole("menuitemradio", { name: "Added by hand" }).click();
  await expect(
    page.getByRole("button", { name: "Open Priya Shah" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open Priya Shah" }).click();
  const panel = page.getByRole("dialog", { name: "Contact Priya Shah" });
  await expect(panel.getByText("Added by hand")).toBeVisible();
  await expect(panel.getByText("Not linked to a channel yet")).toBeVisible();
  await expect(panel.getByText("No conversation yet")).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Refresh profile" }),
  ).toHaveCount(0);
  await expect(panel.getByLabel("Assigned to")).toBeDisabled();

  await panel.getByRole("button", { name: "Delete", exact: true }).click();
  await panel.getByRole("button", { name: "Delete contact" }).click();
  await expect
    .poll(() =>
      calls.some(
        (call) => call.path === `/api/workspaces/${id}/leads/l-manual/`,
      ),
    )
    .toBe(true);
  await expect(panel).toHaveCount(0);
  await expect(page.getByText("No contacts match")).toBeVisible();
});

test("the inbox links a conversation to its contact and back", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/inbox?conversation=v-1`);
  await page.getByRole("button", { name: "Contact details" }).click();
  const details = page.getByRole("complementary", { name: "Contact details" });
  await expect(details).toContainText("+15550100");
  await details.getByRole("link", { name: "View in CRM" }).click();
  await expect(page).toHaveURL(/\/crm\/?\?contact=l-1/);
  const panel = page.getByRole("dialog", { name: "Contact Omar Haddad" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("link", { name: "WhatsApp" })).toHaveAttribute(
    "href",
    "https://wa.me/15550100",
  );
  await panel.getByRole("link", { name: "Open chat" }).click();
  await expect(page).toHaveURL(/\/inbox\/?\?conversation=v-1/);
  await expect(page.getByText("Omar Haddad").first()).toBeVisible();
});
