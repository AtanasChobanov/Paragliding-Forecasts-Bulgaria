import { expect, test, type Page } from "@playwright/test";
const path = "/forecast?site=sofia-vitosha-kominite&date=2026-11-17";
const openDetail = async (page: Page) => {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
};
const sizes = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 1280, height: 720 },
  { width: 1280, height: 600 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 1280, height: 720, text: true },
  { width: 390, height: 844, text: true },
];
for (const size of sizes)
  test(`fits detail ${String(size.width)}×${String(size.height)}${size.text ? " at 125% text" : ""}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(size);
    await openDetail(page);
    if (size.text) await page.addStyleTag({ content: "html { font-size: 125%; }" });
    await expect(page.getByRole("heading", { name: "Hourly cloudbase" })).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => {
          const elements = [
            document.documentElement,
            document.body,
            ...document.querySelectorAll<HTMLElement>(
              "[data-detail], [data-detail] section, [data-detail] article, [data-detail] nav, [data-detail] [data-page-row]",
            ),
          ];
          return elements
            .filter(
              (el) =>
                el.getBoundingClientRect().height > 0 &&
                (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2),
            )
            .map((el) => ({
              tag: el.tagName,
              cls: el.className,
              height: [el.scrollHeight, el.clientHeight],
              width: [el.scrollWidth, el.clientWidth],
            }));
        }),
      )
      .toEqual([]);
    expect(
      await page.evaluate(() =>
        Array.from(document.querySelectorAll<HTMLElement>("[data-page-row]"))
          .filter((row) => {
            const pagination = row.parentElement?.nextElementSibling;
            return (
              pagination instanceof HTMLElement &&
              row.getBoundingClientRect().bottom > pagination.getBoundingClientRect().top + 1
            );
          })
          .map((row) => row.textContent),
      ),
    ).toEqual([]);
    const controls = page.locator("[data-detail] select, [data-detail] button, [data-detail] a");
    for (const control of await controls.all()) {
      if (!(await control.isVisible())) continue;
      const box = await control.boundingBox();
      expect(box).not.toBeNull();
      if (box) {
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.y).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(size.width + 1);
        expect(box.y + box.height).toBeLessThanOrEqual(size.height + 1);
      }
    }
    await page.screenshot({ path: testInfo.outputPath("detail.png") });
    await expect(page.locator(".leaflet-container")).toHaveCount(0);
    await expect(page.getByText("Compared with previous run")).toHaveCount(0);
  });

test("synchronizes hours with inputs, supports keyboard, touch-style click and metadata pages", async ({
  page,
}) => {
  let tiles = 0;
  page.on("request", (request) => {
    if (request.url().includes("tile.openstreetmap.org")) tiles++;
  });
  await openDetail(page);
  await page.getByLabel("Input category").selectOption("cloud");
  const hour = page.getByRole("button", { name: "14:00 Sofia · Conditional LCL" });
  await hour.focus();
  await hour.press("ArrowRight");
  await expect(page.getByLabel("Input hour")).toHaveValue("2026-11-17T13:00:00Z");
  await expect(page.getByRole("region", { name: "Cloudbase hour information" })).toContainText(
    "15:00",
  );
  await page.keyboard.press("Home");
  await expect(page.getByLabel("Input hour")).toHaveValue("2026-11-17T08:00:00Z");
  await page.keyboard.press("End");
  await expect(page.getByLabel("Input hour")).toHaveValue("2026-11-17T18:00:00Z");
  await page.keyboard.press("Escape");
  await page.getByLabel("Input hour").selectOption("2026-11-17T12:00:00Z");
  await expect(hour).toHaveAttribute("aria-pressed", "true");
  await hour.click();
  await expect(page.getByRole("region", { name: "Cloudbase hour information" })).toContainText(
    "Daily maximum",
  );
  await page.getByRole("button", { name: "Close cloudbase tooltip" }).click();
  await page.getByRole("button", { name: "Forecast information", exact: true }).click();
  const info = page.getByRole("region", { name: /Forecast information for/ });
  await expect(info).toContainText("GFS 16 Nov 2026 06Z");
  await info.getByRole("button", { name: "Next" }).click();
  await expect(info).toContainText("today-model");
  await page.keyboard.press("Escape");
  expect(tiles).toBe(0);
});

test("keeps explicit dates, disabled missing slots and dashboard return selection", async ({
  page,
}) => {
  await openDetail(page);
  await expect(
    page.getByLabel("Forecast date").locator('option[value="2026-11-15"]'),
  ).toBeDisabled();
  await page.getByLabel("Forecast date").selectOption("2026-11-18");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByLabel("Forecast date")).toHaveValue("2026-11-18");
  await page.getByRole("link", { name: "All sites" }).click();
  await expect(page).toHaveURL(/\/\?site=sofia-vitosha-kominite&date=2026-11-18$/u);
  await page.getByRole("link", { name: "View detailed forecast", exact: true }).click();
  await expect(page).toHaveURL(/\/forecast\?site=sofia-vitosha-kominite&date=2026-11-18$/u);
  await page.goto("/forecast?site=sofia-vitosha-kominite&date=2026-10-01");
  await expect(page.getByText("Forecast unavailable", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Forecast date")).toHaveValue("2026-10-01");
});

test("retries a 5xx detail error and never refreshes cached requests on focus or reconnect", async ({
  page,
}) => {
  let details = 0;
  let days = 0;
  let sites = 0;
  let fail = true;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/v1/forecasts/days") days++;
    if (url.pathname === "/api/v1/sites") sites++;
  });
  await page.route("**/api/v1/forecasts?*", async (route) => {
    details++;
    if (fail)
      await route.fulfill({
        status: 503,
        headers: { "access-control-allow-origin": "http://localhost:5374" },
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "urn:test",
          title: "Unavailable",
          status: 503,
          detail: "Fixture unavailable",
        }),
      });
    else await route.continue();
  });
  await page.goto(path);
  const retry = page.getByRole("button", { name: "Retry detailed forecast" });
  await expect(retry).toBeVisible();
  fail = false;
  await retry.click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const counts = { details, days, sites };
  await page.evaluate(() => {
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("offline"));
    window.dispatchEvent(new Event("online"));
  });
  await page.waitForTimeout(350);
  expect({ details, days, sites }).toEqual(counts);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  expect(details).toBeGreaterThan(counts.details);
});

test.describe("detail touch", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });
  test("opens a chart hour by tap and dismisses its paginated tooltip outside", async ({
    page,
  }) => {
    await openDetail(page);
    await page.getByRole("button", { name: "14:00 Sofia · Conditional LCL" }).tap();
    const tooltip = page.getByRole("region", { name: "Cloudbase hour information" });
    await expect(tooltip).toContainText("Daily maximum");
    await tooltip.getByRole("button", { name: "Next" }).tap();
    await expect(tooltip).toContainText("Code: fixture");
    await page.getByRole("heading", { name: "Forecast inputs" }).tap();
    await expect(tooltip).toHaveCount(0);
  });
});

test("draws mixed regimes and distinct segment gradients without bridges", async ({ page }) => {
  await page.goto("/forecast?site=zlatitsa&date=2026-11-17");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator('[data-gradient-segment="estimated"]')).toHaveCount(1);
  await expect(page.locator('[data-gradient-segment="conditional"]')).toHaveCount(1);
  await expect(page.locator('[data-regime="missing"]')).not.toHaveCount(0);
  await expect(page.locator('[data-regime="other_cloud"]')).not.toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("mixed-regimes.png") });
});

for (const scenario of [
  { site: "sofia-vitosha-kominite", date: "2026-11-18", width: 390, height: 844, text: true },
  { site: "shumen", date: "2026-11-17", width: 1280, height: 600, text: false },
])
  test(`fits unavailable metrics for ${scenario.site}`, async ({ page }) => {
    await page.setViewportSize(scenario);
    await page.goto(`/forecast?site=${scenario.site}&date=${scenario.date}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (scenario.text) await page.addStyleTag({ content: "html {font-size:125%;}" });
    await expect
      .poll(() =>
        page.evaluate(() =>
          Array.from(
            document.querySelectorAll<HTMLElement>(
              "[data-detail], [data-detail] section, [data-detail] article, [data-detail] nav",
            ),
          )
            .filter(
              (el) => el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2,
            )
            .map((el) => el.className),
        ),
      )
      .toEqual([]);
    await page.screenshot({ path: test.info().outputPath("missing-metrics.png") });
  });

test("groups probability confidence below right metadata and aligns weather footers", async ({
  page,
}) => {
  await openDetail(page);
  for (const name of ["100+ km", "200+ km", "300+ km"]) {
    const card = page.getByRole("article", { name, exact: true });
    const info = await card
      .getByRole("button", { name: `${name} information`, exact: true })
      .boundingBox();
    const confidence = await card.getByRole("group", { name: /confidence/i }).boundingBox();
    expect(info).not.toBeNull();
    expect(confidence).not.toBeNull();
    if (info && confidence) expect(confidence.y).toBeGreaterThanOrEqual(info.y + info.height - 1);
  }
  const cloud = page.getByRole("article", { name: "Conditional LCL", exact: true });
  const od = page.getByRole("article", { name: "OD risk", exact: true });
  const left = await cloud.getByRole("group", { name: /confidence/i }).boundingBox();
  const right = await od.getByRole("group", { name: /confidence/i }).boundingBox();
  expect(left).not.toBeNull();
  expect(right).not.toBeNull();
  if (left && right) {
    expect(Math.abs(left.y - right.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(left.y + left.height - right.y - right.height)).toBeLessThanOrEqual(1);
  }
});
