import { expect, test } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("visitors can ask a question, retain chat and submit a ticket on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let submitted: Record<string, unknown> = {};
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("support-chat/"))
      return route.fulfill({
        json: {
          reply: "Instantlify connects your sales conversations.",
          sentinel: null,
          sources: [],
        },
      });
    if (path.endsWith("/tickets/")) {
      submitted = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { ticket_number: "#1234567890" },
      });
    }
    if (path.endsWith("/plans/"))
      return route.fulfill({ json: { plans: [], trial_days: 7 } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Chat with us" }).click();
  const dialog = page.getByRole("dialog", { name: "Instantlify help and support" });
  await dialog.getByLabel("Message", { exact: true }).fill("What is Instantlify?");
  await dialog.getByRole("button", { name: "Send message" }).click();
  await expect(
    dialog.getByText("Instantlify connects your sales conversations."),
  ).toBeVisible();
  await dialog.getByRole("button", { name: "Close support" }).click();
  await page.getByRole("button", { name: "Chat with us" }).click();
  await expect(
    dialog.getByText("Instantlify connects your sales conversations."),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Raise a ticket", exact: true })
    .click();
  await dialog.getByLabel("Your name", { exact: true }).fill("Sam");
  await dialog
    .getByLabel("Your email", { exact: true })
    .fill("sam@example.com");
  await dialog.getByLabel("Subject", { exact: true }).fill("Need setup help");
  await dialog
    .getByLabel("Describe the issue")
    .fill("How do I connect my first channel?");
  await dialog.getByRole("button", { name: "Submit ticket" }).click();
  await expect(dialog.getByText("Ticket #1234567890 created")).toBeVisible();
  expect(submitted.email).toBe("sam@example.com");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "test-results/support-widget-mobile.png" });
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

test("clients create a ticket, read staff replies, and reopen a resolved request", async ({
  page,
}) => {
  await mockApi(page);
  const ticket = {
    id: 1,
    ticket_number: "#1234567890",
    subject: "Automation stopped",
    body: "My workflow will not run.",
    category: "bug",
    status: "resolved",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    messages: [
      {
        id: 1,
        from_staff: true,
        body: "Please reconnect the channel.",
        created_at: new Date().toISOString(),
      },
    ],
  };
  const tickets: (typeof ticket)[] = [];
  await page.route(`**/api/workspaces/${id}/support/tickets/**`, (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: tickets });
    if (route.request().url().includes("/replies/")) {
      ticket.status = "unresolved";
      ticket.messages.push({
        id: 2,
        from_staff: false,
        body: route.request().postDataJSON().body,
        created_at: new Date().toISOString(),
      });
      return route.fulfill({ status: 201, json: ticket });
    }
    tickets.push(ticket);
    return route.fulfill({ status: 201, json: ticket });
  });
  await page.goto(`/w/${id}/support/`);
  await expect(page.getByRole("heading", { name: "My tickets" })).toBeVisible();
  await expect(page.getByText("No tickets yet")).toBeVisible();
  await page
    .getByRole("button", { name: "Raise a ticket", exact: true })
    .click();
  const form = page
    .getByRole("form", { name: "Raise a ticket" })
    .filter({ visible: true });
  await form.getByLabel("Subject", { exact: true }).fill(ticket.subject);
  await form.getByLabel("Describe the issue").fill(ticket.body);
  await form.getByRole("button", { name: "Submit ticket" }).click();
  await expect(page.getByText("Ticket #1234567890 created")).toBeVisible();
  await page.getByRole("button", { name: /Automation stopped/ }).click();
  await expect(
    page.getByText("Please reconnect the channel.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Reply", { exact: true }).fill("Still not working");
  await page.getByRole("button", { name: "Send reply", exact: true }).click();
  await expect(
    page.getByText("Still not working", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator(".support-ticket-thread .support-ticket-meta"),
  ).toContainText("Open");
  await page.screenshot({
    path: "test-results/support-tickets-desktop.png",
    fullPage: true,
  });
});
