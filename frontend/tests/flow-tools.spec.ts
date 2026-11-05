import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { id, mockApi } from "./support/meta-mock";
import type { FlowGraph } from "../lib/api";

const automationId = "44444444-4444-4444-8444-444444444444";
const graph: FlowGraph = {
  start: "hello",
  triggers: [{ kind: "dm", channel: "instagram", keyword: "hello" }],
  nodes: [
    {
      id: "hello",
      data: { kind: "send_message", text: "Hello from this draft" },
    },
    { id: "done", data: { kind: "end" } },
  ],
  edges: [{ source: "hello", target: "done" }],
};

test("the builder tests a draft, shows retained executions and exports the same graph", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(
    `**/api/workspaces/${id}/automations/${automationId}/`,
    (route) =>
      route.fulfill({
        json: {
          id: automationId,
          name: "Tools check",
          draft: graph,
          published: {},
          enabled: false,
          revision: 0,
        },
      }),
  );
  let tested: FlowGraph | undefined;
  let sampleEvent: unknown;
  await page.route(`**/api/workspaces/${id}/automations/preview/`, (route) => {
    tested = route.request().postDataJSON().graph;
    sampleEvent = route.request().postDataJSON().trigger_event;
    return route.fulfill({
      json: {
        side_effects: false,
        trigger_matched: true,
        trace: [
          {
            node_id: "hello",
            kind: "send_message",
            status: "simulated",
            detail: "Hello from this draft",
          },
          {
            node_id: "done",
            kind: "end",
            status: "simulated",
            detail: "End of this graph",
          },
        ],
      },
    });
  });
  await page.route(
    new RegExp(`/api/workspaces/${id}/automation-runs/\\?automation=`),
    (route) =>
      route.fulfill({
        json: [
          {
            id: "run-one",
            automation_id: automationId,
            conversation_id: "conversation-one",
            status: "completed",
            steps: 1,
            node_id: "done",
            error_code: "",
            revision: 1,
            created_at: new Date().toISOString(),
            trace: [
              { node_id: "hello", steps: 0, status: "running" },
              { node_id: "done", steps: 1, status: "completed" },
            ],
          },
        ],
      }),
  );
  await page.goto(`/w/${id}/automations/${automationId}`);
  await page.getByRole("button", { name: "Test flow", exact: true }).click();
  const testDialog = page.getByRole("dialog");
  await testDialog.getByRole("button", { name: "Close dialog" }).focus();
  await page.keyboard.press("Shift+Tab");
  await expect
    .poll(() =>
      testDialog.evaluate((el) => el.contains(document.activeElement)),
    )
    .toBe(true);
  await page.keyboard.press("Escape");
  await expect(testDialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Test flow", exact: true }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Test flow", exact: true }).click();

  await testDialog.getByLabel("Sample incoming text (optional)").fill("hello");
  await page
    .getByRole("button", { name: "Run walkthrough", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByText("End of this graph", { exact: true }),
  ).toBeVisible();
  expect(tested?.nodes[0].data.text).toBe("Hello from this draft");
  expect(sampleEvent).toEqual({
    kind: "dm",
    channel: "instagram",
    text: "hello",
  });
  await expect(testDialog.getByRole("status")).toContainText(
    "matches a draft trigger",
  );
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Execution history", exact: true })
    .click();
  await page.getByRole("dialog").locator("summary").click();
  await expect(
    page
      .getByRole("dialog")
      .getByText("hello · running · step 0", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open conversation", exact: true }),
  ).toHaveAttribute("href", `/w/${id}/inbox/?conversation=conversation-one`);
  await page.getByRole("button", { name: "Close dialog", exact: true }).click();
  const pending = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export template", exact: true })
    .click();
  const download = await pending;
  const path = await download.path();
  expect(path).toBeTruthy();
  const exported = JSON.parse(await readFile(path!, "utf8"));
  expect(exported).toMatchObject({
    format: "nemio.automation",
    version: 1,
    name: "Tools check",
  });
  expect(exported.graph.nodes[0].data.text).toBe("Hello from this draft");
});

test("voice, calling and avatar settings survive saving the advanced draft", async ({
  page,
}) => {
  await mockApi(page);
  const integrations = ["elevenlabs", "vapi", "heygen"].map(
    (provider, index) => ({
      id: `55555555-5555-4555-8555-55555555555${index}`,
      provider,
      enabled: true,
      is_test: true,
      options: {},
      configured: true,
    }),
  );
  await page.route(
    new RegExp(`/api/workspaces/${id}/integrations/(?:\\?.*)?$`),
    (route) =>
      route.fulfill({
        json: { results: integrations, count: integrations.length, next: null },
      }),
  );
  let saved: FlowGraph | undefined;
  await page.route(
    `**/api/workspaces/${id}/automations/${automationId}/`,
    (route) => {
      if (route.request().method() === "PATCH")
        saved = route.request().postDataJSON().draft;
      return route.fulfill({
        json: {
          id: automationId,
          name: "Provider nodes",
          draft: saved || graph,
          published: {},
          enabled: false,
          revision: 0,
        },
      });
    },
  );
  await page.goto(`/w/${id}/automations/${automationId}`);
  await page
    .getByRole("button", { name: "Generate voice", exact: true })
    .click();
  await page
    .getByLabel("Voice integration", { exact: true })
    .selectOption(integrations[0].id);
  await page
    .getByRole("textbox", { name: /^Message Use/ })
    .fill("A saved voice script");
  await page
    .getByRole("button", { name: "AI phone call", exact: true })
    .click();
  await page
    .getByLabel("Calling integration", { exact: true })
    .selectOption(integrations[1].id);
  await page.getByLabel("Timezone", { exact: true }).fill("Asia/Karachi");
  await page
    .getByLabel("Exact customer call request", { exact: false })
    .fill("Yes, call me");
  await page.getByRole("button", { name: "Avatar video", exact: true }).click();
  await page
    .getByLabel("HeyGen integration", { exact: true })
    .selectOption(integrations[2].id);
  await page
    .getByRole("textbox", { name: /^Message Use/ })
    .fill("A saved avatar script");
  await page
    .getByRole("combobox", { name: /Aspect ratio/ })
    .selectOption("9:16");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect.poll(() => saved?.nodes.length).toBe(5);
  expect(
    saved?.nodes.find((node) => node.data.kind === "generate_voice")?.data,
  ).toMatchObject({
    text: "A saved voice script",
    integration_id: integrations[0].id,
  });
  expect(
    saved?.nodes.find((node) => node.data.kind === "ai_call")?.data,
  ).toMatchObject({
    timezone: "Asia/Karachi",
    consent_reply: "Yes, call me",
    integration_id: integrations[1].id,
  });
  expect(
    saved?.nodes.find((node) => node.data.kind === "avatar_video")?.data,
  ).toMatchObject({
    text: "A saved avatar script",
    aspect_ratio: "9:16",
    integration_id: integrations[2].id,
  });
});
