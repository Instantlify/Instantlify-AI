import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("community discussions support reactions, replies, edits and source-backed answers", async ({
  page,
}) => {
  await mockApi(page);
  const postId = "77777777-7777-4777-8777-777777777777";
  let post = {
    id: postId,
    author: "Alex",
    body: "How do keyword automations work?",
    pinned: false,
    created_at: new Date().toISOString(),
    likes: 0,
    dislikes: 0,
    reply_count: 0,
    my_vote: 0,
    can_edit: true,
    can_delete: true,
    can_pin: true,
  };
  const replies: {
    id: string;
    author: string;
    body: string;
    created_at: string;
    can_delete: boolean;
  }[] = [];
  let removed = false;
  await page.route("**/api/community/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path.endsWith("/assistant/"))
      return route.fulfill({
        json: {
          answer: "Keyword matching starts a workflow.",
          sources: [
            { post_id: postId, excerpt: "How do keyword automations work?" },
          ],
        },
      });
    if (path.endsWith("/reaction/")) {
      const value = route.request().postDataJSON().value;
      post = {
        ...post,
        my_vote: value,
        likes: value === 1 ? 1 : 0,
        dislikes: value === -1 ? 1 : 0,
      };
      return route.fulfill({ json: post });
    }
    if (path.endsWith("/replies/")) {
      if (method === "POST") {
        const reply = {
          id: "reply-one",
          author: "Alex",
          body: route.request().postDataJSON().body,
          created_at: new Date().toISOString(),
          can_delete: true,
        };
        replies.push(reply);
        post = { ...post, reply_count: replies.length };
        return route.fulfill({ status: 201, json: reply });
      }
      return route.fulfill({
        json: { results: replies, count: replies.length },
      });
    }
    if (path === `/api/community/${postId}/`) {
      if (method === "DELETE") {
        removed = true;
        return route.fulfill({ status: 204 });
      }
      if (method === "PATCH")
        post = { ...post, ...route.request().postDataJSON() };
      return route.fulfill({ json: post });
    }
    if (path === "/api/community/") {
      if (method === "POST") {
        post = { ...post, body: route.request().postDataJSON().body };
        removed = false;
        return route.fulfill({ status: 201, json: post });
      }
      return route.fulfill({
        json: { results: removed ? [] : [post], count: removed ? 0 : 1 },
      });
    }
    return route.fulfill({ json: {} });
  });
  await page.goto(`/w/${id}/forum/`);
  await expect(
    page.getByText("Posts and replies are shared", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Like (0)", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Like (1)", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Replies (0)", exact: true }).click();
  const dialog = page.getByRole("region", { name: "Discussion replies" });
  await expect(
    page.getByRole("dialog", { name: "Discussion replies" }),
  ).toHaveCount(0);
  await dialog
    .getByLabel("Your reply")
    .fill("Match the incoming comment against the published trigger.");
  await dialog.getByRole("button", { name: "Post reply", exact: true }).click();
  await expect(
    dialog.getByText("Match the incoming comment", { exact: false }),
  ).toBeVisible();
  const deleteReply = dialog.getByRole("button", {
    name: "Delete reply",
    exact: true,
  });
  await deleteReply.click();
  const confirmation = page.getByRole("alertdialog");
  await expect(confirmation).toContainText("Delete this reply?");
  await confirmation
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(confirmation).toHaveCount(0);
  await expect(dialog).toBeVisible();
  await expect(deleteReply).toBeFocused();
  await dialog.getByRole("button", { name: "Hide replies" }).click();
  await page.getByLabel("Discussion actions by Alex", { exact: true }).click();
  await page.getByRole("button", { name: "Edit post", exact: true }).click();
  const edit = page.getByRole("dialog", { name: "Edit discussion" });
  await edit.getByLabel("Post text").fill("Updated workflow question");
  await edit.getByRole("button", { name: "Save discussion" }).click();
  await expect(
    page.getByText("Updated workflow question", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Discussion actions by Alex", { exact: true }).click();
  await page.getByRole("button", { name: "Pin", exact: true }).click();
  await expect(
    page.getByText("Pinned discussion", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Ask the community assistant").fill("keyword workflow");
  await page.getByRole("button", { name: "Search discussions" }).click();
  await expect(
    page.getByText("Keyword matching starts a workflow.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Discussion actions by Alex", { exact: true }).click();
  await page.getByRole("button", { name: "Delete post", exact: true }).click();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByText("No discussions to show.")).toBeVisible();
});

test("community text is rendered as text and normal members have no moderation controls", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/community/**", (route) =>
    route.fulfill({
      json: {
        count: 1,
        results: [
          {
            id: "one",
            author: "Member",
            body: '<img src=x onerror="alert(1)">',
            pinned: false,
            created_at: new Date().toISOString(),
            likes: 0,
            dislikes: 0,
            reply_count: 0,
            my_vote: 0,
            can_edit: false,
            can_delete: false,
            can_pin: false,
          },
        ],
      },
    }),
  );
  await page.goto(`/w/${id}/forum/`);
  await expect(
    page.getByText('<img src=x onerror="alert(1)">', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Pin", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Delete post", exact: true }),
  ).toHaveCount(0);
});
