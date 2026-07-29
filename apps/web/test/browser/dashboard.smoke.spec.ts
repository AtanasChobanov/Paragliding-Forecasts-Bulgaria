import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const apiOrigin = "http://127.0.0.1:3000";

const waitForApi = async (request: APIRequestContext): Promise<void> => {
  await expect
    .poll(
      async () => {
        try {
          return (await request.get(`${apiOrigin}/health`)).ok();
        } catch {
          return false;
        }
      },
      { timeout: 15_000 },
    )
    .toBe(true);
};

const openDashboard = async (page: Page, request: APIRequestContext): Promise<void> => {
  await waitForApi(request);
  await page.route("https://tile.openstreetmap.org/**", async (route) => {
    await route.abort();
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("main", { name: "XC Forecast dashboard" })).toBeVisible();
  await expect(page).toHaveURL(/\/\?site=[a-z0-9-]+&date=\d{4}-\d{2}-\d{2}$/u);
};

const expectDashboardForecast = async (page: Page): Promise<void> => {
  await expect(page.getByLabel("Location", { exact: true })).toHaveValue("sofia-vitosha-kominite");

  const dates = page.getByRole("list", { name: "Five-day forecast dates" });
  await expect(dates.getByRole("button")).toHaveCount(5);

  const metrics = page.getByRole("list", { name: "Forecast metrics" });
  await expect(metrics.getByRole("listitem")).toHaveCount(5);
  await expect(metrics.getByRole("listitem").filter({ hasText: "100+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(metrics.getByRole("listitem").filter({ hasText: "Cloudbase" })).toContainText(
    /\d[\d,]*m MSL/u,
  );
  await expect(metrics.getByRole("listitem").filter({ hasText: "200+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(metrics.getByRole("listitem").filter({ hasText: "300+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(metrics.getByRole("listitem").filter({ hasText: "OD risk" })).toContainText(
    /Low|Medium|High/u,
  );
  await expect(page.getByText("Mock data").first()).toBeVisible();
};

test("loads the dashboard with the required forecast cards", async ({ page, request }) => {
  await openDashboard(page, request);
  await expectDashboardForecast(page);
  await expect(
    page.getByRole("link", { name: "View detailed forecast", exact: true }),
  ).toBeVisible();
});

test("opens the detailed forecast from the dashboard and returns with the selection", async ({
  page,
  request,
}) => {
  await openDashboard(page, request);
  await expectDashboardForecast(page);

  const dashboardUrl = new URL(page.url());
  const selectedSite = dashboardUrl.searchParams.get("site");
  const selectedDate = dashboardUrl.searchParams.get("date");

  if (selectedSite === null || selectedDate === null) {
    throw new Error("The dashboard did not resolve a canonical site and forecast date.");
  }

  await page.getByRole("link", { name: "View detailed forecast", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/forecast\\?site=${selectedSite}&date=${selectedDate}$`, "u"),
  );

  const detail = page.getByRole("main", { name: "Detailed forecast" });
  await expect(detail).toBeVisible();
  await expect(detail.getByRole("heading", { level: 1 })).toBeVisible();

  const outputs = detail.locator('[aria-label="Detailed forecast outputs"]');
  await expect(outputs.getByRole("article")).toHaveCount(5);
  await expect(outputs.getByRole("article").filter({ hasText: "Cloudbase" })).toContainText(
    /m MSL/u,
  );
  await expect(outputs.getByRole("article").filter({ hasText: "100+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(outputs.getByRole("article").filter({ hasText: "200+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(outputs.getByRole("article").filter({ hasText: "300+ km chance" })).toContainText(
    /\d+%/u,
  );
  await expect(outputs.getByRole("article").filter({ hasText: "Overdevelopment" })).toContainText(
    /Low|Medium|High/u,
  );
  await expect(detail.getByText("Mock data").first()).toBeVisible();
  await expect(detail.getByRole("heading", { name: "Forecast inputs" })).toBeVisible();
  await expect(detail.getByRole("region", { name: "Forecast input values" })).toBeVisible();
  await expect(detail.getByText("Surface temperature")).toBeVisible();
  await expect(detail.getByRole("heading", { name: "Why this result" })).toBeVisible();
  await expect(detail.getByRole("heading", { name: "Compared with previous run" })).toBeVisible();

  await detail.getByRole("link", { name: "All sites" }).click();
  await expect(page).toHaveURL(new RegExp(`/\\?site=${selectedSite}&date=${selectedDate}$`, "u"));
  await expect(page.getByRole("main", { name: "XC Forecast dashboard" })).toBeVisible();
});
