import {
  forecastDateSchema,
  forecastDaysResponseSchema,
  forecastSummariesResponseSchema,
  sitesResponseSchema,
  type ForecastDate,
  type ForecastDaysResponse,
  type ForecastSummariesResponse,
  type Site,
  type SiteSlug,
} from "@paragliding-forecasts/contracts";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useLocation, useNavigate, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "../../src/App.js";
import { AppRoutes } from "../../src/app/app-routes.js";
import { createApiClient } from "../../src/services/api/api-client.js";
import { createDashboardApi } from "../../src/services/api/dashboard-api.js";
import { createForecastOutputs, createSitesResponse } from "../support/dashboard-fixtures.js";
import { renderWithQueryClient } from "../support/render.js";
import { server } from "../support/server.js";

const API_BASE_URL = "https://dashboard-route.example.test/local";
const SITES_URL = `${API_BASE_URL}/api/v1/sites`;
const SUMMARIES_URL = `${API_BASE_URL}/api/v1/forecasts/summaries`;
const DAYS_URL = `${API_BASE_URL}/api/v1/forecasts/days`;
const DEFAULT_TODAY = "2026-07-18" satisfies ForecastDate;

const createTestDashboardApi = () => createDashboardApi(createApiClient({ baseUrl: API_BASE_URL }));
const fullCatalog = createSitesResponse().sites;

const requireSearchParameter = (searchParameters: URLSearchParams, name: string): string => {
  const value = searchParameters.get(name);

  if (value === null) {
    throw new Error(`Expected the ${name} request parameter.`);
  }

  return value;
};

const requireElement = <ElementType extends Element>(element: ElementType | null): ElementType => {
  if (element === null) {
    throw new Error("Expected the dashboard section to be rendered.");
  }

  return element;
};

interface Deferred {
  readonly promise: Promise<void>;
  readonly resolve: () => void;
}

const createDeferred = (): Deferred => {
  let resolvePromise: () => void = () => {
    // Replaced synchronously by the Promise constructor.
  };
  const promise = new Promise<void>((resolve) => {
    resolvePromise = resolve;
  });

  return { promise, resolve: resolvePromise };
};

const addUtcDays = (date: ForecastDate, offset: number): ForecastDate => {
  const [year, month, day] = date.split("-").map(Number) as [number, number, number];
  return new Date(Date.UTC(year, month - 1, day + offset)).toISOString().slice(0, 10);
};

const createDays = (site: Site, todayDate: ForecastDate = DEFAULT_TODAY): ForecastDaysResponse =>
  forecastDaysResponseSchema.parse({
    siteId: site.id,
    siteSlug: site.slug,
    timeZone: "Europe/Sofia",
    todayDate,
    days: [-2, -1, 0, 1, 2].map((offset) => ({
      forecastDate: addUtcDays(todayDate, offset),
      chance100KmPct: {
        value: 65 + offset,
        dataStatus: "mock",
        confidence: { level: "low", note: "Synthetic route-test value." },
      },
    })),
  });

const createSummaries = (
  forecastDate: ForecastDate,
  sites: readonly Site[],
): ForecastSummariesResponse =>
  forecastSummariesResponseSchema.parse({
    forecastDate,
    summaries: sites
      .slice()
      .sort((left, right) => left.id - right.id)
      .map((site) => ({
        availability: "available",
        siteId: site.id,
        siteSlug: site.slug,
        forecastDate,
        generatedAt: "2026-07-17T20:00:00.000Z",
        provenance: { source: `source-${site.slug}`, version: "route-test-v1" },
        outputs: createForecastOutputs(),
      })),
  });

interface DashboardHandlerOptions {
  readonly catalog?: readonly Site[];
  readonly daysGate?: Promise<void>;
  readonly summaryGate?: (requestedSlugs: readonly SiteSlug[]) => Promise<void> | undefined;
  readonly todayBySite?: Readonly<Partial<Record<SiteSlug, ForecastDate>>>;
  readonly transformDays?: (response: ForecastDaysResponse) => ForecastDaysResponse;
  readonly transformSummaries?: (response: ForecastSummariesResponse) => ForecastSummariesResponse;
}

interface RecordedRequests {
  readonly days: SiteSlug[];
  readonly summaries: {
    readonly date: ForecastDate;
    readonly siteSlugs: readonly SiteSlug[];
  }[];
}

const installDashboardHandlers = ({
  catalog = fullCatalog,
  daysGate,
  summaryGate,
  todayBySite = {},
  transformDays = (response) => response,
  transformSummaries = (response) => response,
}: DashboardHandlerOptions = {}): RecordedRequests => {
  const requests: RecordedRequests = { days: [], summaries: [] };

  server.use(
    http.get(SITES_URL, () => HttpResponse.json(sitesResponseSchema.parse({ sites: catalog }))),
    http.get(DAYS_URL, async ({ request }) => {
      const siteSlug = requireSearchParameter(new URL(request.url).searchParams, "siteSlug");
      requests.days.push(siteSlug);
      await daysGate;
      const site = catalog.find((candidate) => candidate.slug === siteSlug);

      if (site === undefined) {
        return HttpResponse.json({ title: "Unknown site", status: 400 }, { status: 400 });
      }

      return HttpResponse.json(
        transformDays(createDays(site, todayBySite[siteSlug] ?? DEFAULT_TODAY)),
      );
    }),
    http.get(SUMMARIES_URL, async ({ request }) => {
      const searchParameters = new URL(request.url).searchParams;
      const date = requireSearchParameter(searchParameters, "date");
      const siteSlugs = (searchParameters.get("siteSlugs") ?? "").split(",");
      requests.summaries.push({ date, siteSlugs });
      await summaryGate?.(siteSlugs);
      const requestedSites = siteSlugs.flatMap((slug) => {
        const site = catalog.find((candidate) => candidate.slug === slug);
        return site === undefined ? [] : [site];
      });

      return HttpResponse.json(transformSummaries(createSummaries(date, requestedSites)));
    }),
  );

  return requests;
};

const LocationProbe = () => {
  const location = useLocation();
  return (
    <>
      <output data-testid="location-search">{location.search}</output>
      <output data-testid="location-key">{location.key}</output>
    </>
  );
};

const HistoryControls = () => {
  const navigate = useNavigate();
  return (
    <aside>
      <button
        type="button"
        onClick={() => {
          void navigate(-1);
        }}
      >
        Test back
      </button>
      <button
        type="button"
        onClick={() => {
          void navigate(1);
        }}
      >
        Test forward
      </button>
    </aside>
  );
};

const renderDashboardRoute = (initialEntry: string) =>
  renderWithQueryClient(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AppRoutes dashboardApi={createTestDashboardApi()} />
      <LocationProbe />
      <HistoryControls />
    </MemoryRouter>,
  );

const expectCanonicalLocation = async (expected: string) => {
  await waitFor(() => {
    expect(screen.getByTestId("location-search")).toHaveTextContent(expected);
  });
};

afterEach(() => {
  window.history.replaceState({}, "", "/");
});

describe("dashboard route URL orchestration", () => {
  it("defaults an unordered catalog to its minimum numeric ID and today's date", async () => {
    const catalog = [fullCatalog[2], fullCatalog[6], fullCatalog[0], fullCatalog[1]].filter(
      (site): site is Site => site !== undefined,
    );
    const requests = installDashboardHandlers({ catalog });

    renderDashboardRoute("/?unowned=discarded");

    await expectCanonicalLocation("?site=sofia-vitosha-kominite&date=2026-07-18");
    expect(screen.getByLabelText("Location")).toHaveValue("sofia-vitosha-kominite");
    expect(requests.days).toEqual(["sofia-vitosha-kominite"]);
    await waitFor(() => {
      expect(requests.summaries).toEqual([
        {
          date: "2026-07-18",
          siteSlugs: ["sofia-vitosha-kominite", "zlatitsa", "sopot", "dobrich-region"],
        },
      ]);
    });
  });

  it.each([
    ["an unknown site", "/?site=unknown&date=2026-07-18"],
    ["a repeated site", "/?site=sopot&site=zlatitsa&date=2026-07-18"],
    ["a missing site", "/?date=2026-07-18"],
  ])("replaces %s with the explicit minimum-ID site", async (_description, entry) => {
    installDashboardHandlers();
    renderDashboardRoute(entry);

    await expectCanonicalLocation("?site=sofia-vitosha-kominite&date=2026-07-18");
  });

  it.each([
    ["a malformed date", "/?site=sopot&date=not-a-date"],
    ["a repeated date", "/?site=sopot&date=2026-07-17&date=2026-07-18"],
    ["a missing date", "/?site=sopot"],
  ])("waits for days and replaces %s with today", async (_description, entry) => {
    installDashboardHandlers();
    renderDashboardRoute(entry);

    await expectCanonicalLocation("?site=sopot&date=2026-07-18");
    expect(screen.getByRole("button", { name: "2026-07-18" })).toHaveAttribute(
      "aria-current",
      "date",
    );
  });

  it("queries a valid deep-link date before days resolves and canonicalizes owned parameters", async () => {
    const days = createDeferred();
    const requests = installDashboardHandlers({ daysGate: days.promise });

    renderDashboardRoute("/?date=2026-07-17&extra=discarded&site=sopot");

    await screen.findByText("source source-sopot");
    expect(requests.days).toEqual(["sopot"]);
    expect(requests.summaries[0]).toMatchObject({ date: "2026-07-17" });
    await expectCanonicalLocation("?site=sopot&date=2026-07-17");
    days.resolve();
    await screen.findByRole("button", { name: "2026-07-17" });
  });

  it("does not query summaries for a missing date until days supplies today", async () => {
    const days = createDeferred();
    const requests = installDashboardHandlers({ daysGate: days.promise });

    renderDashboardRoute("/?site=sopot");
    await waitFor(() => {
      expect(requests.days).toEqual(["sopot"]);
    });
    expect(requests.summaries).toHaveLength(0);
    expect(screen.getByText("Waiting for the selected location's forecast dates.")).toBeVisible();

    days.resolve();
    await waitFor(() => {
      expect(requests.summaries).toHaveLength(1);
    });
    expect(requests.summaries[0]?.date).toBe(DEFAULT_TODAY);
  });

  it("replaces a valid but out-of-strip date with today after days resolves", async () => {
    installDashboardHandlers();
    renderDashboardRoute("/?site=sopot&date=2026-08-01");

    await expectCanonicalLocation("?site=sopot&date=2026-07-18");
    expect(await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" })).toBeVisible();
  });

  it("pushes deliberate site/date changes and restores them with Back and Forward", async () => {
    installDashboardHandlers();
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sofia-vitosha-kominite&date=2026-07-18");

    await screen.findByRole("heading", {
      name: "Sofia - Vitosha (Kominite) · Saturday, 18 Jul",
    });
    await user.selectOptions(screen.getByLabelText("Location"), "sopot");
    await expectCanonicalLocation("?site=sopot&date=2026-07-18");
    await user.click(screen.getByRole("button", { name: "2026-07-19" }));
    await expectCanonicalLocation("?site=sopot&date=2026-07-19");
    expect(screen.getByText("Selected Sopot for 2026-07-19.")).toHaveAttribute(
      "aria-live",
      "polite",
    );

    await user.click(screen.getByRole("button", { name: "Test back" }));
    await expectCanonicalLocation("?site=sopot&date=2026-07-18");
    await user.click(screen.getByRole("button", { name: "Test back" }));
    await expectCanonicalLocation("?site=sofia-vitosha-kominite&date=2026-07-18");
    await user.click(screen.getByRole("button", { name: "Test forward" }));
    await expectCanonicalLocation("?site=sopot&date=2026-07-18");
  });

  it("preserves a site's current date only when it remains in the new site's strip", async () => {
    installDashboardHandlers({ todayBySite: { sopot: "2026-07-21" } });
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sofia-vitosha-kominite&date=2026-07-18");

    await screen.findByRole("heading", {
      name: "Sofia - Vitosha (Kominite) · Saturday, 18 Jul",
    });
    await user.selectOptions(screen.getByLabelText("Location"), "sopot");

    await expectCanonicalLocation("?site=sopot&date=2026-07-21");
    expect(screen.getByRole("button", { name: "2026-07-21" })).toHaveAttribute(
      "aria-current",
      "date",
    );
  });

  it("reconstructs a pasted deep link through the production BrowserRouter", async () => {
    installDashboardHandlers();
    window.history.replaceState({}, "", "/?site=sopot&date=2026-07-17");

    renderWithQueryClient(<App dashboardApi={createTestDashboardApi()} />);

    expect(await screen.findByRole("heading", { name: "Sopot · Friday, 17 Jul" })).toBeVisible();
    expect(window.location.search).toBe("?site=sopot&date=2026-07-17");
  });

  it("does not create history entries for same-site or same-date selections", async () => {
    installDashboardHandlers();
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sopot&date=2026-07-18");
    const selectedDateButton = await screen.findByRole("button", { name: "2026-07-18" });
    const initialKey = screen.getByTestId("location-key").textContent;

    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "sopot" } });
    await user.click(selectedDateButton);

    expect(screen.getByTestId("location-key")).toHaveTextContent(initialKey);
    expect(screen.getByTestId("location-search")).toHaveTextContent("?site=sopot&date=2026-07-18");
  });
});

describe("dashboard request and presentation selection", () => {
  it("derives Other Locations from the three catalog entries after the minimum ID", async () => {
    const requests = installDashboardHandlers();
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    await screen.findByText("Zlatitsa");
    const otherSection = screen
      .getByRole("heading", {
        name: "Other locations for this date",
      })
      .closest("section");
    expect(otherSection).not.toBeNull();
    const items = await within(requireElement(otherSection)).findAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("data-site-slug"))).toEqual([
      "zlatitsa",
      "sopot",
      "nevsha",
    ]);
    expect(requests.summaries[0]?.siteSlugs).toEqual(["zlatitsa", "sopot", "nevsha"]);
  });

  it("deduplicates a selected comparison site in the request without removing its Other card", async () => {
    const requests = installDashboardHandlers();
    renderDashboardRoute("/?site=zlatitsa&date=2026-07-18");

    await screen.findByRole("heading", { name: "Zlatitsa · Saturday, 18 Jul" });
    expect(requests.summaries[0]?.siteSlugs).toEqual(["zlatitsa", "sopot", "nevsha"]);
    const otherSection = screen
      .getByRole("heading", {
        name: "Other locations for this date",
      })
      .closest("section");
    expect(await within(requireElement(otherSection)).findByText("Zlatitsa")).toBeVisible();
  });

  it("requests and presents only ID-derived sites that exist in a partial catalog", async () => {
    const catalog = fullCatalog.filter((site) => site.slug === "zlatitsa" || site.slug === "sopot");
    const requests = installDashboardHandlers({ catalog });
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" });
    expect(requests.summaries[0]?.siteSlugs).toEqual(["sopot"]);
    const otherSection = screen
      .getByRole("heading", {
        name: "Other locations for this date",
      })
      .closest("section");
    expect(await within(requireElement(otherSection)).findAllByRole("listitem")).toHaveLength(1);
    expect(within(requireElement(otherSection)).getByText("Sopot")).toBeVisible();
  });

  it("handles an empty catalog without issuing dependent requests", async () => {
    const requests = installDashboardHandlers({ catalog: [] });
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByText("No forecast locations are configured.")).toBeVisible();
    expect(requests.days).toHaveLength(0);
    expect(requests.summaries).toHaveLength(0);
  });

  it("treats an omitted selected summary as partial content instead of a request error", async () => {
    installDashboardHandlers({
      transformSummaries: (response) => ({
        ...response,
        summaries: response.summaries.filter((summary) => summary.siteSlug !== "sopot"),
      }),
    });
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(
      await screen.findByText("No summary was returned for the selected location."),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Retry selected forecast" }),
    ).not.toBeInTheDocument();
  });

  it("does not retain a previous site's summary while a new selection loads", async () => {
    const sopotSummary = createDeferred();
    installDashboardHandlers({
      summaryGate: (slugs) =>
        slugs.includes("sopot") && !slugs.includes("sofia-vitosha-kominite")
          ? sopotSummary.promise
          : undefined,
    });
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sofia-vitosha-kominite&date=2026-07-18");

    await screen.findByText("source source-sofia-vitosha-kominite");
    await user.selectOptions(screen.getByLabelText("Location"), "sopot");
    expect(await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" })).toBeVisible();
    expect(screen.getByText("Loading the selected forecast…")).toBeVisible();
    expect(screen.queryByText("source source-sofia-vitosha-kominite")).not.toBeInTheDocument();

    sopotSummary.resolve();
    expect(await screen.findByText("source source-sopot")).toBeVisible();
  });
});

describe("dashboard independent failures", () => {
  it("renders a scoped sites failure without dependent regions", async () => {
    server.use(
      http.get(SITES_URL, () =>
        HttpResponse.json(
          {
            type: "urn:paragliding-forecasts:problem:internal-server-error",
            title: "Internal server error",
            status: 500,
            detail: "Sites are temporarily unavailable.",
            code: "INTERNAL_SERVER_ERROR",
            requestId: "sites-request-id",
          },
          { status: 500 },
        ),
      ),
    );
    renderDashboardRoute("/");

    expect(await screen.findByRole("button", { name: "Retry locations" })).toBeVisible();
    expect(screen.getByText(/sites-request-id/)).toBeVisible();
    expect(screen.queryByLabelText("Location")).not.toBeInTheDocument();
  });

  it("retries the sites request in place and restores dependent regions", async () => {
    installDashboardHandlers();
    let attempts = 0;
    server.use(
      http.get(SITES_URL, () => {
        attempts += 1;

        return attempts === 1
          ? HttpResponse.json(
              {
                type: "urn:paragliding-forecasts:problem:internal-server-error",
                title: "Internal server error",
                status: 500,
                detail: "Sites are temporarily unavailable.",
                code: "INTERNAL_SERVER_ERROR",
                requestId: "sites-retry-id",
              },
              { status: 500 },
            )
          : HttpResponse.json(sitesResponseSchema.parse({ sites: fullCatalog }));
      }),
    );
    const user = userEvent.setup();
    renderDashboardRoute("/");

    expect(await screen.findByText(/sites-retry-id/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry locations" }));
    expect(await screen.findByLabelText("Location")).toBeVisible();
    expect(attempts).toBe(2);
  });

  it("keeps a valid selected summary when the days request fails", async () => {
    installDashboardHandlers();
    server.use(http.get(DAYS_URL, () => HttpResponse.json({ error: true }, { status: 500 })));
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByText("source source-sopot")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry forecast dates" })).toBeVisible();
  });

  it("retries only the days region while keeping the overview usable", async () => {
    installDashboardHandlers();
    let attempts = 0;
    server.use(
      http.get(DAYS_URL, ({ request }) => {
        attempts += 1;
        const siteSlug = requireSearchParameter(new URL(request.url).searchParams, "siteSlug");
        const site = fullCatalog.find((candidate) => candidate.slug === siteSlug);

        if (attempts === 1) {
          return HttpResponse.json(
            {
              type: "urn:paragliding-forecasts:problem:internal-server-error",
              title: "Internal server error",
              status: 500,
              detail: "Forecast dates are temporarily unavailable.",
              code: "INTERNAL_SERVER_ERROR",
              requestId: "days-retry-id",
            },
            { status: 500 },
          );
        }

        return site === undefined
          ? HttpResponse.json({ error: true }, { status: 404 })
          : HttpResponse.json(createDays(site));
      }),
    );
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByText("source source-sopot")).toBeVisible();
    expect(screen.getByText(/days-retry-id/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry forecast dates" }));
    expect(await screen.findByRole("button", { name: "2026-07-18" })).toBeVisible();
    expect(attempts).toBe(2);
  });

  it("keeps the date strip when the summaries request fails", async () => {
    installDashboardHandlers();
    server.use(http.get(SUMMARIES_URL, () => HttpResponse.json({ error: true }, { status: 500 })));
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByRole("button", { name: "Retry selected forecast" })).toBeVisible();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "2026-07-18" })).toHaveAttribute(
      "aria-current",
      "date",
    );
  });

  it("retries the shared summaries request without disabling map or dates", async () => {
    installDashboardHandlers();
    let attempts = 0;
    server.use(
      http.get(SUMMARIES_URL, ({ request }) => {
        attempts += 1;
        const searchParameters = new URL(request.url).searchParams;
        const date = forecastDateSchema.parse(requireSearchParameter(searchParameters, "date"));
        const siteSlugs = requireSearchParameter(searchParameters, "siteSlugs").split(",");
        const sites = siteSlugs.flatMap((slug) => {
          const site = fullCatalog.find((candidate) => candidate.slug === slug);
          return site === undefined ? [] : [site];
        });

        return attempts === 1
          ? HttpResponse.json(
              {
                type: "urn:paragliding-forecasts:problem:internal-server-error",
                title: "Internal server error",
                status: 500,
                detail: "Summaries are temporarily unavailable.",
                code: "INTERNAL_SERVER_ERROR",
                requestId: "summaries-retry-id",
              },
              { status: 500 },
            )
          : HttpResponse.json(createSummaries(date, sites));
      }),
    );
    const user = userEvent.setup();
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByText(/summaries-retry-id/)).toBeVisible();
    expect(screen.getByLabelText("Location")).toBeVisible();
    expect(screen.getByRole("button", { name: "2026-07-18" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry selected forecast" }));
    expect(await screen.findByText("source source-sopot")).toBeVisible();
    expect(attempts).toBe(2);
  });

  it("surfaces a days correlation mismatch as an API compatibility error", async () => {
    const zlatitsa = fullCatalog.find((site) => site.slug === "zlatitsa") as Site;
    installDashboardHandlers({ transformDays: () => createDays(zlatitsa) });
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(await screen.findByText("source source-sopot")).toBeVisible();
    expect(
      screen.getByText("The forecast service returned days for a different location."),
    ).toBeVisible();
    expect(screen.getByText("Forecast dates response is incompatible")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry forecast dates" })).not.toBeInTheDocument();
  });

  it("surfaces a summary correlation mismatch without hiding the date strip", async () => {
    installDashboardHandlers({
      transformSummaries: () => {
        const unrequestedSite = fullCatalog.find((site) => site.slug === "shumen") as Site;
        return createSummaries(DEFAULT_TODAY, [unrequestedSite]);
      },
    });
    renderDashboardRoute("/?site=sopot&date=2026-07-18");

    expect(
      await screen.findByText(
        "The forecast service returned a summary for an unrequested location.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "2026-07-18" })).toBeVisible();
    expect(screen.getByText("Forecast response is incompatible")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Retry selected forecast" }),
    ).not.toBeInTheDocument();
  });
});
