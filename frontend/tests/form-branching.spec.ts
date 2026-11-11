import { test, expect } from "@playwright/test";
import { visibleFormFields } from "../lib/form-path";
import type { LeadForm } from "../lib/portal-tools";

const form: LeadForm = {
  id: "one",
  title: "Qualification",
  slug: "qualification",
  description: "Help us prepare",
  published: true,
  consent_text: "You may contact me",
  success_text: "Received",
  fields: [
    { id: "email", label: "Your email", type: "email", required: true },
    {
      id: "book",
      label: "Interested in booking?",
      type: "yes_no",
      required: true,
    },
    {
      id: "details",
      label: "Booking details",
      type: "textarea",
      required: true,
    },
    {
      id: "topics",
      label: "Topics",
      type: "checkboxes",
      options: ["Sales", "Support"],
      required: true,
    },
    { id: "rating", label: "Rating", type: "rating", required: true },
  ],
  branching: [{ field_id: "book", answer: "no", next_id: "topics" }],
};

test("form path follows exact forward branches", () => {
  expect(
    visibleFormFields(form, { book: "no" }).map((field) => field.id),
  ).toEqual(["email", "book", "topics", "rating"]);
  expect(
    visibleFormFields(form, { book: "yes" }).map((field) => field.id),
  ).toContain("details");
});

test("public form branches and submits multiple choices without hidden answers", async ({
  page,
}) => {
  let body: { answers: Record<string, unknown> } | undefined;
  await page.route("**/api/auth/csrf/", (route) =>
    route.fulfill({ json: { csrfToken: "test-token" } }),
  );
  await page.route("**/api/public/forms/qualification/", (route) => {
    if (route.request().method() === "POST") {
      body = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: { message: "Received" } });
    }
    return route.fulfill({ json: form });
  });
  await page.goto("/f/qualification/");
  const publicForm = page.locator("main");
  await publicForm
    .getByLabel("Your email", { exact: false })
    .fill("person@example.com");
  await publicForm
    .getByLabel("Interested in booking?", { exact: false })
    .selectOption("yes");
  await publicForm
    .getByLabel("Booking details", { exact: false })
    .fill("Old hidden answer");
  await publicForm
    .getByLabel("Interested in booking?", { exact: false })
    .selectOption("no");
  await expect(
    publicForm.getByLabel("Booking details", { exact: false }),
  ).toHaveCount(0);
  await publicForm.getByLabel("Sales", { exact: true }).check();
  await publicForm.getByLabel("Support", { exact: true }).check();
  await publicForm.getByLabel("Rating", { exact: false }).selectOption("5");
  await publicForm.getByLabel("You may contact me", { exact: true }).check();
  await page.getByRole("button", { name: "Send response" }).click();
  await expect(page.getByRole("status")).toHaveText("Received");
  expect(body?.answers).toEqual({
    email: "person@example.com",
    book: "no",
    topics: ["Sales", "Support"],
    rating: "5",
  });
});

test("only public forms permit embedding", async ({ request }) => {
  const formResponse = await request.get("/f/qualification/");
  expect(formResponse.headers()["content-security-policy"]).toBe(
    "frame-ancestors *",
  );
  const privateResponse = await request.get("/auth/");
  expect(privateResponse.headers()["content-security-policy"]).toBe(
    "frame-ancestors 'none'",
  );
});

test("file uploads and drawn signatures are sent with a consented response", async ({
  page,
}) => {
  const uploadForm = {
    ...form,
    fields: [
      form.fields[0],
      { id: "file", label: "Proposal", type: "file_upload", required: true },
      { id: "signature", label: "Approval", type: "signature", required: true },
    ],
    branching: [],
  };
  let submitted:
    { answers: Record<string, { name: string; data: string }> } | undefined;
  await page.route("**/api/auth/csrf/", (route) =>
    route.fulfill({ json: { csrfToken: "test-token" } }),
  );
  await page.route("**/api/public/forms/qualification/", (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { message: "Files received" },
      });
    }
    return route.fulfill({ json: uploadForm });
  });
  await page.goto("/f/qualification/");
  const main = page.locator("main");
  await main.getByLabel("Your email", { exact: false }).fill("p@example.com");
  await main.getByLabel("Choose file", { exact: false }).setInputFiles({
    name: "proposal.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("A private proposal"),
  });
  await expect(main.getByText("proposal.txt ready to submit.")).toBeVisible();
  const pad = main.getByLabel("Approval signature pad");
  const box = await pad.boundingBox();
  if (!box) throw new Error("Signature pad is not visible");
  await page.mouse.move(box.x + 30, box.y + 50);
  await page.mouse.down();
  await page.mouse.move(box.x + 100, box.y + 70, { steps: 5 });
  await page.mouse.up();
  await expect(main.getByText("signature.png ready to submit.")).toBeVisible();
  await main.getByLabel("You may contact me", { exact: true }).check();
  await main.getByRole("button", { name: "Send response" }).click();
  await expect(
    main.getByRole("status").filter({ hasText: "Files received" }),
  ).toBeVisible();
  expect(Buffer.from(submitted!.answers.file.data, "base64").toString()).toBe(
    "A private proposal",
  );
  expect(submitted!.answers.signature.data).toMatch(/^iVBOR/);
});

test("grouped contact questions collect named CRM details", async ({
  page,
}) => {
  let submitted: { answers: Record<string, unknown> } | undefined;
  await page.route("**/api/auth/csrf/", (route) =>
    route.fulfill({ json: { csrfToken: "test-token" } }),
  );
  await page.route("**/api/public/forms/qualification/", (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: { message: "Received" } });
    }
    return route.fulfill({
      json: {
        ...form,
        branching: [],
        fields: [
          {
            id: "contact",
            label: "Your details",
            type: "contact_block",
            required: true,
            include_phone: true,
          },
        ],
      },
    });
  });
  await page.goto("/f/qualification/");
  const main = page.locator("main");
  await main.getByLabel("First name").fill("Ada");
  await main.getByLabel("Last name").fill("Lovelace");
  await main.getByLabel("Email address").fill("ada@example.com");
  await main.getByLabel("Phone number").fill("12345");
  await main.getByLabel("You may contact me").check();
  await main.getByRole("button", { name: "Send response" }).click();
  await expect(main.getByRole("status")).toHaveText("Received");
  expect(submitted?.answers.contact).toEqual({
    first_name: "Ada",
    last_name: "Lovelace",
    email: "ada@example.com",
    phone: "12345",
  });
});

test("welcome and booking cards do not submit pretend booking answers", async ({
  page,
}) => {
  let submitted: { answers: Record<string, unknown> } | undefined;
  await page.route("https://calendly.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<p>Choose a time</p>" }),
  );
  await page.route("**/api/auth/csrf/", (route) =>
    route.fulfill({ json: { csrfToken: "test-token" } }),
  );
  await page.route("**/api/public/forms/qualification/", (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: { message: "Received" } });
    }
    return route.fulfill({
      json: {
        ...form,
        branching: [],
        capture_contacts: false,
        fields: [
          {
            id: "welcome",
            label: "Welcome",
            description: "Find a time that suits you",
            type: "cover_card",
            required: false,
          },
          {
            id: "booking",
            label: "Pick a time",
            type: "calendly",
            booking_url: "https://calendly.com/team/chat",
            required: false,
          },
        ],
      },
    });
  });
  await page.goto("/f/qualification/");
  const main = page.locator("main");
  await expect(
    main.getByRole("heading", { name: "Welcome", exact: true }),
  ).toBeVisible();
  await expect(
    page.frameLocator('iframe[title="Pick a time"]').getByText("Choose a time"),
  ).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  await main.getByLabel("You may contact me").scrollIntoViewIfNeeded();
  await expect(main.getByLabel("You may contact me")).toBeInViewport();
  await main.getByLabel("You may contact me").check();
  await main.getByRole("button", { name: "Send response" }).click();
  await expect(main.getByRole("status")).toHaveText("Received");
  expect(submitted?.answers).toEqual({});
});
