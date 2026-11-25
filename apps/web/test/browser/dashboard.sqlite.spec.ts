import { expect, test, type Locator, type Page } from "@playwright/test";

const dashboard = (page: Page) => page.getByRole("main", { name: "XC Forecast dashboard" });
const overview = (page: Page) => page.getByRole("region", { name: "Forecast overview" });
const dates = (page: Page) => page.getByRole("list", { name: "Five-day forecast dates" });

const openDashboard = async (page: Page, path = "/") => {
  await page.route("https://tile.openstreetmap.org/**", async (route) => {
    await route.abort();
  });
  await page.goto(path);
  await expect(overview(page).getByRole("link", { name: "View detailed forecast" })).toBeVisible();
  await expect(page.locator(".leaflet-container")).toBeVisible();
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
};

const seeFullyWithinViewport = async (locator: Locator) => {
  await expect(locator).toBeVisible();
  await expect(locator).toBeInViewport({ ratio: 1 });
};

const layouts = [
  { width: 1440, height: 900, text: 100 },
  { width: 1366, height: 768, text: 100 },
  { width: 1280, height: 720, text: 100 },
  { width: 1280, height: 600, text: 100 },
  { width: 1024, height: 768, text: 100 },
  { width: 390, height: 844, text: 100 },
  { width: 1280, height: 720, text: 125 },
  { width: 390, height: 844, text: 125 },
];

for (const { width, height, text } of layouts) {
  test(`fits the dashboard at ${String(width)}×${String(height)} with ${String(text)}% text`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height });
    await openDashboard(page);
    if (text !== 100) {
      await page.addStyleTag({ content: `html { font-size: ${String(text)}%; }` });
    }
    await seeFullyWithinViewport(page.getByRole("banner"));
    await seeFullyWithinViewport(overview(page).getByRole("heading", { level: 1 }));
    await seeFullyWithinViewport(
      overview(page).getByRole("link", { name: "View detailed forecast" }),
    );
    await seeFullyWithinViewport(overview(page).locator("[data-forecast-footer]"));
    await seeFullyWithinViewport(page.getByLabel("Location", { exact: true }));
    await seeFullyWithinViewport(page.locator(".leaflet-container"));
    for (const card of await dates(page).getByRole("button").all()) {
      await seeFullyWithinViewport(card);
    }
    const comparison = page.getByRole("region", { name: "Other locations for this date" });
    const comparisonBox = await comparison.boundingBox();
    const overviewBox = await overview(page).boundingBox();
    expect(comparisonBox?.height).toBeLessThanOrEqual(overviewBox?.height ?? 0);
    const cardSpacing = await comparison.getByRole("article").evaluateAll((cards) =>
      cards.map((card) => {
        const [header, primary, secondary, confidence] = Array.from(card.children);
        if (!header || !primary || !secondary || !confidence) {
          throw new Error("Expected the four comparison card rows.");
        }
        return {
          aboveChance: primary.getBoundingClientRect().top - header.getBoundingClientRect().bottom,
          aboveConfidence:
            confidence.getBoundingClientRect().top - secondary.getBoundingClientRect().bottom,
        };
      }),
    );
    for (const spacing of cardSpacing) {
      expect(spacing.aboveChance).toBeGreaterThanOrEqual(-1);
      expect(Math.abs(spacing.aboveConfidence)).toBeLessThanOrEqual(1);
    }

    const map = page.locator(".leaflet-container");
    await expect(map.locator(".leaflet-marker-icon")).toHaveCount(7);
    await expect(map.locator(".leaflet-tooltip")).toHaveCount(7);
    await expect
      .poll(() =>
        map.evaluate((element) => {
          const frame = element.getBoundingClientRect();
          return Array.from(
            element.querySelectorAll(
              innerWidth >= 1120
                ? ".leaflet-marker-icon > span, .leaflet-tooltip"
                : ".leaflet-marker-icon > span",
            ),
          ).flatMap((feature) => {
            const rect = feature.getBoundingClientRect();
            return rect.left >= frame.left - 1 &&
              rect.right <= frame.right + 1 &&
              rect.top >= frame.top - 1 &&
              rect.bottom <= frame.bottom + 1
              ? []
              : [feature.textContent || feature.parentElement?.getAttribute("title")];
          });
        }),
      )
      .toEqual([]);

    if (width >= 1120) {
      const span = await map.locator(".leaflet-marker-icon").evaluateAll((pins) => {
        const positions = pins.map((pin) => pin.getBoundingClientRect().left);
        return Math.max(...positions) - Math.min(...positions);
      });
      expect(span).toBeGreaterThan(width * 0.25);
    }

    const layout = await dashboard(page).evaluate((main) => {
      const targets = [
        document.documentElement,
        document.body,
        document.querySelector("#root"),
        main.parentElement?.parentElement,
        main.parentElement,
        main,
        ...main.querySelectorAll(
          ':scope > section, :scope > section > div, article, [aria-label="Five-day forecast dates"], [aria-label="Five-day forecast dates"] button, [aria-label="Forecast metrics"] li',
        ),
      ];
      return {
        scrollTop: document.scrollingElement?.scrollTop,
        appHeight: main.parentElement?.parentElement?.getBoundingClientRect().height,
        overflowing: targets.flatMap((element) => {
          if (element === null || element === undefined) {
            return [];
          }
          const { clientWidth, clientHeight, scrollWidth, scrollHeight, scrollTop } = element;
          if (scrollWidth > clientWidth + 1 || scrollHeight > clientHeight + 1 || scrollTop !== 0) {
            return [
              {
                element: element.tagName,
                className: element.getAttribute("class"),
                clientWidth,
                clientHeight,
                scrollWidth,
                scrollHeight,
                scrollTop,
              },
            ];
          }
          return [];
        }),
      };
    });
    expect(layout.scrollTop).toBe(0);
    expect(layout.appHeight).toBe(height);
    expect(layout.overflowing).toEqual([]);

    if (width >= 1120) {
      const lines = await overview(page)
        .getByRole("heading", { level: 1 })
        .evaluate((heading) => {
          const range = document.createRange();
          range.selectNodeContents(heading);
          return new Set(Array.from(range.getClientRects(), (rect) => rect.top)).size;
        });
      expect(lines).toBe(1);
    }
  });
}

test("shows SQLite values and keeps unavailable dates out of selection", async ({ page }) => {
  await openDashboard(page, "/?site=sofia-vitosha-kominite&date=2026-11-16");
  await expect(page).toHaveURL(/date=2026-11-17$/u);
  await expect(dates(page).getByRole("button", { name: "2026-11-15" })).toBeDisabled();
  await expect(dates(page).getByRole("button", { name: "2026-11-16" })).toBeDisabled();
  await expect(overview(page)).toContainText("1.57%");
  await expect(overview(page)).toContainText("Conditional LCL");
  await expect(overview(page)).toContainText("2,062");
  await expect(
    overview(page).getByRole("group", { name: "100+ km confidence. Low confidence" }),
  ).toBeVisible();
  const zlatitsaP100 = page
    .getByRole("article", { name: "Zlatitsa" })
    .getByRole("group", { name: "100+ km chance" });
  await expect(zlatitsaP100).toContainText("0%");
  await expect(zlatitsaP100).toContainText("Baseline");
  await expect(page.getByRole("article", { name: "Sopot" })).toContainText("<0.01%");

  const tomorrow = dates(page).getByRole("button", { name: "2026-11-18" });
  await expect(tomorrow).toBeEnabled();
  await expect(tomorrow).toContainText("Unavailable");
  await tomorrow.click();
  await expect(page).toHaveURL(/date=2026-11-18$/u);
  const previousIssue = page.getByRole("article", { name: "Zlatitsa" });
  await expect(previousIssue).toContainText("20%");
  await expect(previousIssue.getByRole("link")).toHaveCount(1);
  await previousIssue.getByRole("button", { name: "Forecast information" }).hover();
  const panel = page.getByRole("region", { name: "Forecast information for Zlatitsa" });
  await expect(panel).toContainText("From previous issue");
  await expect(panel).toContainText("late-import");
  await expect(panel).not.toContainText("High confidence");
  for (const label of [
    "100+ km chance",
    "200+ km chance",
    "300+ km chance",
    "Cloudbase",
    "OD risk",
  ]) {
    await expect(panel.getByText(label, { exact: true })).toHaveCount(0);
  }
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();

  await dates(page).getByRole("button", { name: "2026-11-19" }).click();
  await expect(page).toHaveURL(/date=2026-11-19$/u);
  await expect(overview(page)).toContainText("5%");
  await page.getByLabel("Location", { exact: true }).selectOption("pastrina");
  await expect(page).toHaveURL(/site=pastrina&date=2026-11-19$/u);
  await expect(overview(page)).toContainText("Blue");
});

const expectSelectedTriangle = async (page: Page, direction: string, label: string) => {
  const tooltip = page.locator(`.leaflet-tooltip-${direction}`).filter({ hasText: label });
  await expect(tooltip).toBeVisible();
  const colors = await tooltip.evaluate(
    (element, side) => ({
      background: getComputedStyle(element).backgroundColor,
      triangle: getComputedStyle(element, "::before").getPropertyValue(`border-${side}-color`),
    }),
    direction,
  );
  expect(colors.background).toBe("rgb(39, 130, 124)");
  expect(colors.triangle).toBe(colors.background);
};

test("colors the existing Leaflet triangle for bottom and top labels", async ({ page }) => {
  await openDashboard(page);
  await expectSelectedTriangle(page, "bottom", "Vitosha");
  await page.getByLabel("Location", { exact: true }).selectOption("zlatitsa");
  await expectSelectedTriangle(page, "top", "Zlatitsa");
});

test.describe("touch information panel", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

  test("pins the tapped card's metadata until an outside tap", async ({ page }) => {
    await openDashboard(page);
    const sopotCard = page.getByRole("article", { name: "Sopot" });
    const information = sopotCard.getByRole("button", { name: "Forecast information" });
    const panel = page.getByRole("region", { name: "Forecast information for Sopot" });
    await information.tap();
    await expect(information).toHaveAttribute("aria-expanded", "true");
    await expect(panel).toContainText("NOAA GFS");
    await expect(panel).toContainText("today-model");
    expect(
      await panel.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        return (
          bounds.left >= 0 &&
          bounds.top >= 0 &&
          bounds.right <= innerWidth &&
          bounds.bottom <= innerHeight
        );
      }),
    ).toBe(true);
    await page.getByRole("heading", { name: "Select forecast date" }).tap();
    await expect(panel).toBeHidden();
    await expect(information).toHaveAttribute("aria-expanded", "false");
  });
});
