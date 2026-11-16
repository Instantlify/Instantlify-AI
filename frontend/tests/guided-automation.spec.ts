import { test, expect } from "@playwright/test";
import {
  compileGuidedAutomation,
  type GuidedSettings,
} from "../lib/guided-automation";
import { id, mockApi } from "./support/meta-mock";

const settings = (): GuidedSettings => ({
  platform: "instagram",
  connectionId: "account-one",
  trigger: "comment",
  matchAny: false,
  keywords: "guide, INFO",
  opening: true,
  openingText: "Would you like the guide?",
  openingButton: "Send guide",
  collectEmail: true,
  emailQuestion: "Your email?",
  resourceText: "Your resources",
  links: [
    { title: "Guide", url: "https://example.com/guide" },
    { title: "Book", url: "https://example.com/book" },
  ],
  tag: "interested",
  assignee: "7",
  transfer: "",
});

test("guided flow requires opt-in and email before delivering multiple resources and CRM actions", () => {
  const graph = compileGuidedAutomation(
    settings(),
    "instantlify:continue:test",
  );
  expect(graph.connection_id).toBe("account-one");
  expect(graph.triggers).toEqual([
    { kind: "comment", keyword: "guide", channel: "instagram" },
    { kind: "comment", keyword: "INFO", channel: "instagram" },
  ]);
  expect(graph.nodes.map((n) => n.data.kind)).toEqual([
    "send_buttons",
    "wait",
    "send_message",
    "capture_email",
    "send_buttons",
    "add_tag",
    "assign_member",
    "end",
  ]);
  expect(graph.nodes[0].data.buttons?.[0]).toEqual({
    type: "postback",
    title: "Send guide",
    payload: "instantlify:continue:test",
  });
  expect(graph.nodes[1].data.expected_reply).toBe("instantlify:continue:test");
  expect(
    graph.nodes.find((n) => n.id === "resources")?.data.buttons,
  ).toHaveLength(2);
  expect(graph.nodes.find((n) => n.id === "assign")?.data.user_id).toBe(7);
});

test("an empty specific-keyword configuration never silently becomes match-all", () => {
  expect(() =>
    compileGuidedAutomation({ ...settings(), keywords: " , " }, "test"),
  ).toThrow(/keywords/);
  expect(
    compileGuidedAutomation(
      { ...settings(), matchAny: true, keywords: "" },
      "test",
    ).triggers[0].keyword,
  ).toBe("*");
});

test("unsupported triggers and credential-bearing resource URLs cannot be saved", () => {
  expect(() =>
    compileGuidedAutomation({ ...settings(), platform: "whatsapp" }, "test"),
  ).toThrow(/Comments require/);
  expect(() =>
    compileGuidedAutomation({ ...settings(), connectionId: "" }, "test"),
  ).toThrow(/connected account/);
  expect(() =>
    compileGuidedAutomation(
      {
        ...settings(),
        links: [{ title: "Bad", url: "https://user:secret@example.com" }],
      },
      "test",
    ),
  ).toThrow(/without credentials/);
});

test("guided builder previews consent and retries a failed publish without creating duplicate drafts", async ({
  page,
}) => {
  await mockApi(page);
  const newId = "33333333-3333-4333-8333-333333333333";
  let creates = 0;
  let updates = 0;
  let saved: Record<string, unknown> = {
    id: newId,
    revision: 0,
    enabled: false,
    published: {},
    folder: "",
    installed_from: null,
  };
  await page.route(
    new RegExp(`/api/workspaces/${id}/automations/(?:\\?.*)?$`),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      creates += 1;
      saved = { ...saved, ...route.request().postDataJSON() };
      return route.fulfill({ status: 201, json: saved });
    },
  );
  await page.route(
    `**/api/workspaces/${id}/automations/${newId}/publish/`,
    (route) =>
      route.fulfill({
        status: 400,
        json: { detail: "Review the published destination first." },
      }),
  );
  await page.route(
    `**/api/workspaces/${id}/automations/${newId}/`,
    async (route) => {
      if (route.request().method() === "PATCH") {
        updates += 1;
        saved = { ...saved, ...route.request().postDataJSON() };
      }
      return route.fulfill({ json: saved });
    },
  );
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: "Create New", exact: true }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  await expect(
    page.getByLabel("Connected account", { exact: true }),
  ).toHaveValue("c-ig");
  await page.getByLabel("Trigger keywords", { exact: true }).fill("GUIDE");
  await page
    .getByLabel("Link 1 URL", { exact: true })
    .fill("https://example.com/guide");
  await expect(
    page.getByText("Waiting for the lead to tap the button. Try it above."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Send me the link", exact: true })
    .click();
  await expect(
    page
      .locator(".nm-guided-preview")
      .getByText("Here are the resources you asked for."),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("guided-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Publish automation", exact: true })
    .click();
  await expect(
    page
      .getByRole("region", { name: "Guided automation builder" })
      .getByRole("alert"),
  ).toContainText("Review the published destination first.");
  expect(creates).toBe(1);
  await page
    .getByRole("button", { name: "Save as Draft", exact: true })
    .click();
  await expect.poll(() => updates).toBe(1);
  expect(creates).toBe(1);
  expect(saved.draft).toMatchObject({ connection_id: "c-ig" });
});

test("the guided builder fits a phone without horizontal overflow", async ({
  page,
}) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: "Create New", exact: true }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  await expect(
    page.getByLabel("Automation name", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("guided-mobile.png"),
    fullPage: true,
  });
  const layout = await page.evaluate(() => ({
    width: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflow: [...document.querySelectorAll("body *")]
      .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
      .map((el) => ({
        tag: el.tagName,
        class: el.className,
        right: el.getBoundingClientRect().right,
      }))
      .slice(0, 12),
  }));
  expect(layout.scrollWidth, JSON.stringify(layout)).toBeLessThanOrEqual(
    layout.width,
  );
});

test("saving a guided flow in the canvas preserves its account scope and CRM nodes", async ({
  page,
}) => {
  await mockApi(page);
  const automationId = "44444444-4444-4444-8444-444444444444";
  const draft = compileGuidedAutomation(
    {
      ...settings(),
      connectionId: "c-ig",
      postScope: "specific",
      postIds: ["test-post-1"],
      publicReplies: ["Check your messages!", "Sent you the details."],
    },
    "test-response",
  );
  let savedGraph: unknown;
  const automation = {
    id: automationId,
    name: "Scoped workflow",
    draft,
    published: {},
    enabled: false,
    revision: 0,
  };
  await page.route(
    `**/api/workspaces/${id}/automations/${automationId}/`,
    async (route) => {
      if (route.request().method() === "PATCH")
        savedGraph = route.request().postDataJSON().draft;
      return route.fulfill({ json: automation });
    },
  );
  await page.goto(`/w/${id}/automations/${automationId}`);
  await expect(
    page.getByRole("heading", { name: "Scoped workflow", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect.poll(() => savedGraph).toMatchObject({ connection_id: "c-ig" });
  const graph = savedGraph as ReturnType<typeof compileGuidedAutomation>;
  expect(graph.comment_post_ids).toEqual(["test-post-1"]);
  expect(graph.comment_replies).toEqual([
    "Check your messages!",
    "Sent you the details.",
  ]);
  expect(graph.nodes.map((node) => node.data.kind)).toContain("capture_email");
  expect(
    graph.nodes.find((node) => node.data.kind === "wait")?.data.expected_reply,
  ).toBe("test-response");
  expect(
    graph.nodes.find((node) => node.data.kind === "add_tag")?.data.tag,
  ).toBe("interested");
  // Incremental typing must keep separators until the next ID is entered.
  await page.getByLabel(/^Comment post IDs/).press("End");
  await page.getByLabel(/^Comment post IDs/).pressSequentially(",test-post-2");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect
    .poll(() => (savedGraph as typeof graph).comment_post_ids)
    .toEqual(["test-post-1", "test-post-2"]);
});

test("next-post targeting arms a fresh target without keeping selected post IDs", () => {
  const graph = compileGuidedAutomation(
    { ...settings(), postScope: "next", postIds: ["old-post"] },
    "test",
  );
  expect(graph.comment_post_mode).toBe("next");
  expect(graph.comment_post_ids).toBeUndefined();
  expect(graph.comment_since).toBeUndefined();
  expect(graph.resolved_next_post_id).toBeUndefined();
});

test("conditional follow-up compiles tracked resources and a bounded reminder delay", () => {
  const graph = compileGuidedAutomation(
    {
      ...settings(),
      reminder: true,
      reminderDelay: 3600,
      reminderText: "Need help opening the guide?",
    },
    "test",
  );
  expect(
    graph.nodes.find((node) => node.id === "resources")?.data.track_clicks,
  ).toBe(true);
  expect(
    graph.nodes.find((node) => node.id === "reminder-delay")?.data,
  ).toEqual({ kind: "delay", seconds: 3600 });
  expect(
    graph.nodes.find((node) => node.id === "reminder")?.data,
  ).toMatchObject({ kind: "send_reminder", source_node: "resources" });
  expect(() =>
    compileGuidedAutomation(
      {
        ...settings(),
        reminder: true,
        reminderDelay: 86400,
        reminderText: "Hello",
      },
      "test",
    ),
  ).toThrow(/23 hours/);
  expect(() =>
    compileGuidedAutomation(
      {
        ...settings(),
        reminder: true,
        opening: false,
        collectEmail: false,
        reminderText: "Hello",
      },
      "test",
    ),
  ).toThrow(/opening reply/);
});

test("media editing supports copy, duplicate, undo and redo without losing account scope", async ({
  page,
}) => {
  await mockApi(page);
  const automationId = "44444444-4444-4444-8444-444444444444";
  const draft = compileGuidedAutomation(
    { ...settings(), connectionId: "c-ig" },
    "test",
  );
  let saved: unknown;
  await page.route(
    `**/api/workspaces/${id}/automations/${automationId}/`,
    (route) => {
      if (route.request().method() === "PATCH")
        saved = route.request().postDataJSON().draft;
      return route.fulfill({
        json: {
          id: automationId,
          name: "Editor checks",
          draft,
          published: {},
          enabled: false,
          revision: 0,
        },
      });
    },
  );
  await page.goto(`/w/${id}/automations/${automationId}`);
  const count = draft.nodes.length;
  await page.getByRole("button", { name: "Send media", exact: true }).click();
  await page.getByLabel("Media type", { exact: true }).selectOption("video");
  await page
    .getByLabel("Media URL", { exact: true })
    .fill("https://example.com/demo.mp4");
  await expect(
    page.getByRole("button", { name: "Undo", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Copy step", exact: true }).click();
  await page
    .getByRole("button", { name: "Duplicate step", exact: true })
    .click();
  await expect(page.locator(".react-flow__node")).toHaveCount(count + 2);
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(count + 1);
  await page.getByRole("button", { name: "Redo", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(count + 2);
  await page.getByRole("button", { name: "Paste step", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(count + 3);
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect.poll(() => saved).toMatchObject({ connection_id: "c-ig" });
  const graph = saved as ReturnType<typeof compileGuidedAutomation>;
  expect(
    graph.nodes.filter((node) => node.data.kind === "send_media"),
  ).toHaveLength(3);
  expect(
    graph.nodes
      .filter((node) => node.data.kind === "send_media")
      .every((node) => node.data.media_url === "https://example.com/demo.mp4"),
  ).toBe(true);
  expect(new Set(graph.nodes.map((node) => node.id)).size).toBe(
    graph.nodes.length,
  );
});

test("specific comment targeting cannot silently widen and public replies compile only for comments", () => {
  expect(() =>
    compileGuidedAutomation(
      { ...settings(), postScope: "specific", postIds: [] },
      "test",
    ),
  ).toThrow(/Choose at least one post/);
  expect(() =>
    compileGuidedAutomation({ ...settings(), publicReplies: [""] }, "test"),
  ).toThrow(/public reply/);
  const graph = compileGuidedAutomation(
    {
      ...settings(),
      trigger: "dm",
      postScope: "specific",
      postIds: ["post"],
      publicReplies: ["Public"],
    },
    "test",
  );
  expect(graph.comment_post_ids).toBeUndefined();
  expect(graph.comment_replies).toBeUndefined();
});

test("AI and webhook settings survive canvas save with response mappings intact", async ({
  page,
}) => {
  await mockApi(page);
  const automationId = "44444444-4444-4444-8444-444444444444";
  const draft = compileGuidedAutomation(
    { ...settings(), connectionId: "c-ig" },
    "test",
  );
  let saved: unknown;
  await page.route(
    `**/api/workspaces/${id}/automations/${automationId}/`,
    (route) => {
      if (route.request().method() === "PATCH")
        saved = route.request().postDataJSON().draft;
      return route.fulfill({
        json: {
          id: automationId,
          name: "AI workflow",
          draft,
          published: {},
          enabled: false,
          revision: 0,
        },
      });
    },
  );
  await page.route(`**/api/workspaces/${id}/agent/models/`, (route) =>
    route.fulfill({
      json: [
        {
          id: "gemini-2.5-flash",
          provider: "gemini",
          label: "Gemini",
          rate_summary: "Test rate",
        },
      ],
    }),
  );
  await page.route(
    new RegExp(`/api/workspaces/${id}/integrations/(?:\\?.*)?$`),
    (route) =>
      route.fulfill({
        json: {
          results: [
            {
              id: "55555555-5555-4555-8555-555555555555",
              provider: "n8n",
              enabled: true,
              status: "active",
              configured: true,
            },
          ],
          count: 1,
          next: null,
        },
      }),
  );
  await page.goto(`/w/${id}/automations/${automationId}`);
  await page
    .getByRole("button", { name: "Extract with AI", exact: true })
    .click();
  await page
    .getByLabel("Workflow AI model", { exact: true })
    .selectOption("gemini:gemini-2.5-flash");
  await page
    .getByLabel("Workflow AI instructions", { exact: true })
    .fill("Extract the customer's details: {{last_text}}");
  await page
    .getByLabel("AI extraction fields", { exact: true })
    .fill("email, budget");
  await page.getByLabel("AI result variable", { exact: true }).fill("details");
  await page
    .getByRole("button", { name: "Run integration", exact: true })
    .click();
  await page.getByLabel("Operation", { exact: true }).selectOption("webhook");
  await page
    .getByLabel("Connected integration", { exact: true })
    .selectOption("55555555-5555-4555-8555-555555555555");
  await page
    .getByLabel("Webhook request body", { exact: true })
    .fill('{"email":"{{email}}"}');
  await page
    .getByLabel("Webhook response fields", { exact: true })
    .fill('{"order_id":"order.id"}');
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect.poll(() => saved).toMatchObject({ connection_id: "c-ig" });
  const graph = saved as ReturnType<typeof compileGuidedAutomation>;
  expect(
    graph.nodes.find((node) => node.data.kind === "ai_extract")?.data,
  ).toMatchObject({
    fields: ["email", "budget"],
    ai_provider: "gemini",
    ai_model: "gemini-2.5-flash",
    variable: "details",
  });
  expect(
    graph.nodes.find((node) => node.data.operation === "webhook")?.data,
  ).toMatchObject({
    request_body: '{"email":"{{email}}"}',
    response_map: '{"order_id":"order.id"}',
  });
});

test("guided comments save selected posts and public reply variations", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/connections/c-ig/posts/`, (route) =>
    route.fulfill({
      json: {
        results: [
          { id: "test-post-1", label: "Our new guide", permalink: "" },
          { id: "test-post-2", label: "Another post", permalink: "" },
        ],
      },
    }),
  );
  let draft: unknown;
  await page.route(
    new RegExp(`/api/workspaces/${id}/automations/(?:\\?.*)?$`),
    async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      const data = route.request().postDataJSON();
      draft = data.draft;
      return route.fulfill({
        status: 201,
        json: {
          id: "55555555-5555-4555-8555-555555555555",
          name: data.name,
          draft,
          published: {},
          enabled: false,
          revision: 0,
        },
      });
    },
  );
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: "Create New", exact: true }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  await page.getByLabel("Comment post scope").selectOption("specific");
  await page.getByRole("checkbox", { name: /Our new guide/ }).check();
  await page.getByLabel("Trigger keywords", { exact: true }).fill("GUIDE");
  await page
    .getByLabel("Link 1 URL", { exact: true })
    .fill("https://example.com/guide");
  await page
    .getByRole("checkbox", { name: /Reply publicly to the comment/ })
    .check();
  await page
    .getByLabel("Public reply 1", { exact: true })
    .fill("Check your messages!");
  await page
    .getByRole("button", { name: "Add reply variation", exact: true })
    .click();
  await page
    .getByLabel("Public reply 2", { exact: true })
    .fill("Sent you the details.");
  await expect(
    page
      .getByRole("complementary", { name: "Conversation preview" })
      .getByText("Check your messages!", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: test.info().outputPath("comment-automation.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Save as Draft", exact: true })
    .click();
  await expect
    .poll(() => draft)
    .toMatchObject({
      connection_id: "c-ig",
      comment_post_ids: ["test-post-1"],
      comment_replies: ["Check your messages!", "Sent you the details."],
    });
});

test("a post loading failure is visible and cannot save an unrestricted flow", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/connections/c-ig/posts/`, (route) =>
    route.fulfill({
      status: 400,
      json: { detail: "Reconnect this account to load posts." },
    }),
  );
  let creates = 0;
  await page.route(
    new RegExp(`/api/workspaces/${id}/automations/(?:\\?.*)?$`),
    (route) => {
      if (route.request().method() === "POST") creates++;
      return route.fallback();
    },
  );
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: "Create New", exact: true }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  await page.getByLabel("Comment post scope").selectOption("specific");
  await expect(
    page.getByText("Reconnect this account to load posts."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save as Draft", exact: true })
    .click();
  await expect(
    page.getByText("Choose at least one post for this comment trigger."),
  ).toBeVisible();
  expect(creates).toBe(0);
});
