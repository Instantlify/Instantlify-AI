import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";
import type { CreatorKit } from "../lib/portal-tools";

test("creator kits select connected statistics and label their source separately", async ({
  page,
}) => {
  await mockApi(page);
  let selected: string[] | undefined;
  let kit: CreatorKit = {
    slug: "connected-creator",
    name: "Connected Creator",
    headline: "",
    bio: "",
    contact_email: "",
    links: [],
    services: [],
    statistics: [{ label: "Entered reach", value: "999" }],
    published: true,
    live_connection_ids: [],
    live_statistics: [],
  };
  await page.route(`**/api/workspaces/${id}/creator-kit/`, (route) => {
    if (route.request().method() === "PUT") {
      const data = route.request().postDataJSON();
      selected = data.live_connection_ids;
      kit = {
        ...data,
        live_statistics: [
          {
            label: "Instagram followers",
            value: "1234",
            account: "studio.north",
            as_of: new Date().toISOString(),
          },
        ],
      };
    }
    return route.fulfill({ json: kit });
  });
  await page.route("**/api/public/creator/connected-creator/", (route) =>
    route.fulfill({ json: kit }),
  );
  await page.goto(`/w/${id}/creator-kit/`);
  await page
    .getByRole("checkbox", { name: "studio.north", exact: true })
    .check();
  await page
    .getByRole("button", { name: "Save creator kit", exact: true })
    .click();
  await expect.poll(() => selected).toEqual(["c-ig"]);
  await expect(
    page.getByText("Creator kit saved.", { exact: true }),
  ).toBeVisible();
  await page.goto("/c/connected-creator/");
  const connected = page.getByRole("region", {
    name: "Connected account statistics",
    exact: true,
  });
  await expect(connected.getByText("1234", { exact: true })).toBeVisible();
  await expect(connected).toContainText("From Instagram");
  await expect(page.getByText("999", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Audience figures provided by the creator.", {
      exact: true,
    }),
  ).toBeVisible();
});
