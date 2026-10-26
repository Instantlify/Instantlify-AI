import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("ZorroMail configuration separates the API key from sender options", async ({
  page,
}) => {
  await mockApi(page);
  let saved: Record<string, unknown> | undefined;
  await page.route(`**/api/workspaces/${id}/integrations/`, (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { id: "zorro", ...saved, configured: true },
      });
    }
    return route.fulfill({ json: { results: [] } });
  });
  await page.goto(`/w/${id}/integrations/`);
  const card = page
    .locator(".boosend-int-card")
    .filter({ hasText: "ZorroMail" });
  await expect(card.getByText("Coming Soon")).toHaveCount(0);
  await card
    .getByRole("button", { name: "Create Integration", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Verified sender email", exact: true })
    .fill("sender@example.com");
  await page
    .getByLabel("Transactional API key", { exact: true })
    .fill("private-key");
  await page
    .getByRole("button", { name: "Save Configuration", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      provider: "zorromail",
      credentials: { api_key: "private-key" },
      options: { sender_email: "sender@example.com" },
    });
});

test("call agent creation shows its outcome and assigning a default preserves credentials", async ({
  page,
}) => {
  await mockApi(page);
  let defaultUpdate: Record<string, unknown> | undefined;
  await page.route(`**/api/workspaces/${id}/integrations/`, (route) => {
    if (route.request().method() === "POST") {
      defaultUpdate = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { id: "vapi", provider: "vapi", configured: true },
      });
    }
    return route.fulfill({
      json: {
        results: [
          {
            id: "vapi",
            provider: "vapi",
            configured: true,
            enabled: true,
            status: "active",
            is_test: false,
            options: {},
          },
        ],
      },
    });
  });
  let created: Record<string, unknown> | undefined;
  const agentId = "55555555-5555-4555-8555-555555555555";
  const row = {
    id: "created-job",
    name: "Helpful team agent",
    status: "pending",
    agent_id: "",
    llm_id: "",
    error: "",
    is_test: false,
  };
  await page.route(
    `**/api/workspaces/${id}/integrations/vapi/call-agents/`,
    (route) => {
      if (route.request().method() === "POST") {
        created = route.request().postDataJSON();
        return route.fulfill({ status: 202, json: row });
      }
      return route.fulfill({
        json: created
          ? [{ ...row, status: "complete", agent_id: agentId }]
          : [],
      });
    },
  );
  await page.goto(`/w/${id}/integrations/`);
  const card = page.locator(".boosend-int-card").filter({ hasText: "Vapi" });
  await card
    .getByRole("button", { name: "Create AI call agent", exact: true })
    .click();
  const section = card.getByRole("region", {
    name: "Vapi call agents",
    exact: true,
  });
  await section
    .getByRole("textbox", { name: "Agent name", exact: true })
    .fill("Helpful team agent");
  await section
    .getByRole("textbox", { name: "Agent instructions", exact: true })
    .fill("Help with product questions.");
  await section
    .getByRole("textbox", { name: "First message", exact: true })
    .fill("Hello, I am an AI assistant.");
  await section
    .getByRole("textbox", { name: "Vapi OpenAI model ID", exact: true })
    .fill("gpt-4.1");
  await section
    .getByRole("textbox", { name: "ElevenLabs voice ID", exact: true })
    .fill("voice_one");
  await section
    .getByRole("button", { name: "Create and publish agent", exact: true })
    .click();
  await expect
    .poll(() => created)
    .toMatchObject({
      name: "Helpful team agent",
      model: "gpt-4.1",
      voice_id: "voice_one",
    });
  await expect(section.getByText("Agent ready", { exact: true })).toBeVisible({
    timeout: 10000,
  });
  await section
    .getByRole("button", { name: "Use as default call agent", exact: true })
    .click();
  await expect
    .poll(() => defaultUpdate)
    .toEqual({ provider: "vapi", options: { agent_id: agentId } });
});
