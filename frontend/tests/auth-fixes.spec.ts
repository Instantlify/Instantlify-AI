import { test, expect } from "@playwright/test";

const confirmation =
  "If an account exists for this email address, you'll receive a sign-in link shortly. Please check your inbox and spam folder.";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me/")
      return route.fulfill({
        status: 401,
        json: { detail: "Sign in required" },
      });
    if (path === "/api/public/branding/")
      return route.fulfill({
        json: { brand_name: "Instantlify", logo_url: "" },
      });
    if (path === "/api/growth/support-chat/")
      return route.fulfill({ json: { sentinel: "[[REQUEST_NAME_CARD]]" } });
    return route.fulfill({ json: {} });
  });
});

for (const width of [1440, 768, 375]) {
  test(`support name and email forms stay usable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/auth/");
    await page.getByRole("button", { name: "Chat with us" }).click();
    const widget = page.getByRole("dialog", {
      name: "Instantlify help and support",
    });
    await widget
      .getByRole("textbox", { name: "Message", exact: true })
      .fill("I need support");
    await widget.getByRole("button", { name: "Send message" }).click();
    await widget.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(widget.locator(".field-error")).toHaveText("Enter your name.");
    const input = widget.getByRole("textbox", {
      name: "Your name",
      exact: true,
    });
    const field = await input.boundingBox();
    const form = await widget.locator(".chat-card").boundingBox();
    expect(field!.width).toBeGreaterThan(form!.width - 45);
    const button = await widget
      .getByRole("button", { name: "Continue", exact: true })
      .boundingBox();
    const error = await widget.locator(".field-error").boundingBox();
    expect(button!.y).toBeGreaterThan(error!.y + error!.height);
    await input.fill("Alex");
    await widget.getByRole("button", { name: "Continue", exact: true }).click();
    const email = widget.getByRole("textbox", {
      name: "Your email",
      exact: true,
    });
    await email.fill("invalid");
    await widget.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await expect(widget.locator(".field-error")).toContainText(
      "Enter a valid email address",
    );
    const emailBounds = await email.boundingBox();
    expect(emailBounds!.width).toBeGreaterThan(form!.width - 45);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/support-${width}.png`,
      fullPage: true,
    });
  });
}

test("magic link gives generic guidance and a visible resend cooldown", async ({
  page,
}) => {
  await page.clock.install();
  let requests = 0;
  await page.route("**/api/auth/magic-link/", (route) => {
    requests++;
    return route.fulfill({ json: { detail: confirmation, resend_after: 60 } });
  });
  await page.goto("/auth/magic/");
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill("alex@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByRole("status")).toHaveText(confirmation);
  await expect(page.getByRole("button", { name: /Resend in/ })).toBeDisabled();
  expect(requests).toBe(1);
  await page.clock.fastForward(61_000);
  await expect(
    page.getByRole("button", { name: "Resend sign-in link", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Resend sign-in link", exact: true })
    .click();
  await expect.poll(() => requests).toBe(2);
});

test("magic-link delivery service failure provides password fallback", async ({
  page,
}) => {
  await page.route("**/api/auth/magic-link/", (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail:
          "Sign-in links are temporarily unavailable. Please sign in with your password.",
      },
    }),
  );
  await page.goto("/auth/magic/");
  await page
    .getByRole("textbox", { name: "Email", exact: true })
    .fill("alex@example.com");
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.locator(".error-notice")).toContainText(
    "temporarily unavailable",
  );
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Sign in with a password instead" }),
  ).toBeVisible();
});

test("auth validation uses coordinated form and field errors without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/auth/?mode=signup");
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("Alex");
  await page.getByLabel("Email address").fill("alex@example.com");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.locator(".form-validation-summary")).toBeVisible();
  await expect(page.locator(".field-error")).toHaveText(
    "Use at least 12 characters for password.",
  );
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/auth-validation-mobile.png",
    fullPage: true,
  });
});

test("completed accounts return to the dashboard after password sign-in", async ({
  page,
}) => {
  const user = { id: 1, name: "Alex", email: "alex@example.com" };
  const id = "11111111-1111-4111-8111-111111111111";
  const workspace = {
    id,
    name: "Studio",
    role: "owner",
    checkout_pending: false,
    branding: { brand_name: "Instantlify" },
  };
  let signedIn = false;
  await page.route("**/api/auth/me/", (route) =>
    signedIn
      ? route.fulfill({ json: user })
      : route.fulfill({ status: 401, json: { detail: "Sign in required" } }),
  );
  await page.route("**/api/auth/login/", (route) => {
    signedIn = true;
    return route.fulfill({ json: user });
  });
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: [workspace] } }),
  );
  await page.route(`**/api/workspaces/${id}/`, (route) =>
    route.fulfill({ json: workspace }),
  );
  await page.goto("/auth/");
  await page.getByLabel("Email address").fill(user.email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Testing-password-2026");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${id}/overview/?$`));
});

test("password reset highlights mismatched confirmation using the shared validation styles", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/auth/reset/#uid=test&token=test");
  await page
    .getByLabel("New password", { exact: true })
    .fill("Testing-password-2026");
  const confirm = page.getByLabel("Confirm password", { exact: true });
  await confirm.fill("Different-password-2026");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(confirm).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator(".field-error")).toHaveText(
    "Passwords do not match.",
  );
  await expect(page.locator(".form-validation-summary")).toBeVisible();
});
