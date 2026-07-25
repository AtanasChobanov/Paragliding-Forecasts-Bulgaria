import type { LeafletEventHandlerFnMap, LatLngExpression } from "leaflet";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createSitesResponse } from "../support/dashboard-fixtures.js";

const leafletMocks = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  invalidateSize: vi.fn(),
  panInside: vi.fn(),
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({
    children,
    keyboard,
    scrollWheelZoom,
  }: {
    readonly children: ReactNode;
    readonly keyboard: boolean;
    readonly scrollWheelZoom: boolean;
  }) => (
    <div
      data-keyboard={String(keyboard)}
      data-scroll-wheel-zoom={String(scrollWheelZoom)}
      data-testid="leaflet-map"
    >
      {children}
    </div>
  ),
  Marker: ({
    children,
    eventHandlers,
    keyboard,
    position,
    title,
  }: {
    readonly children: ReactNode;
    readonly eventHandlers: LeafletEventHandlerFnMap;
    readonly keyboard: boolean;
    readonly position: LatLngExpression;
    readonly title: string;
  }) => (
    <button
      aria-label={title}
      data-keyboard={String(keyboard)}
      data-position={JSON.stringify(position)}
      tabIndex={-1}
      type="button"
      onClick={() => eventHandlers.click?.({} as never)}
    >
      {children}
    </button>
  ),
  TileLayer: ({
    attribution,
    eventHandlers,
    url,
  }: {
    readonly attribution: string;
    readonly eventHandlers: LeafletEventHandlerFnMap;
    readonly url: string;
  }) => (
    <div data-testid="tile-layer" data-url={url}>
      <span dangerouslySetInnerHTML={{ __html: attribution }} />
      <button type="button" onClick={() => eventHandlers.load?.({} as never)}>
        Finish tiles
      </button>
      <button type="button" onClick={() => eventHandlers.tileerror?.({} as never)}>
        Fail tiles
      </button>
    </div>
  ),
  Tooltip: ({ children }: { readonly children: ReactNode }) => <span>{children}</span>,
  useMap: () => leafletMocks,
}));

import { SiteMap, createSiteBounds } from "../../src/features/dashboard/components/SiteMap.js";

describe("SiteMap", () => {
  beforeEach(() => {
    leafletMocks.fitBounds.mockReset();
    leafletMocks.invalidateSize.mockReset();
    leafletMocks.panInside.mockReset();
  });

  it("fits API coordinates, renders permanent labels and OSM attribution, and selects a pin", async () => {
    const sites = createSitesResponse().sites;
    const selectedSite = sites.find((site) => site.slug === "sopot");
    const onSelectSite = vi.fn();

    if (selectedSite === undefined) {
      throw new Error("Expected the Sopot fixture.");
    }

    render(<SiteMap onSelectSite={onSelectSite} selectedSite={selectedSite} sites={sites} />);

    const map = screen.getByTestId("leaflet-map");
    expect(map).toHaveAttribute("data-scroll-wheel-zoom", "false");
    expect(map).toHaveAttribute("data-keyboard", "false");
    expect(screen.getByRole("link", { name: "OpenStreetMap" })).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );
    expect(screen.getByTestId("tile-layer")).toHaveAttribute(
      "data-url",
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    );
    expect(
      screen.getAllByRole("button", {
        name: /selected|Vitosha|Zlatitsa|Nevsha|Shumen|Pastrina|Dobrich/i,
      }),
    ).toHaveLength(7);
    expect(screen.getByRole("button", { name: "Sopot (selected)" })).toHaveAttribute(
      "tabindex",
      "-1",
    );
    expect(screen.getAllByText("Sopot").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("img", { name: "Map orientation: north is at the top" })).toBeVisible();
    expect(screen.getByText("N")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Zlatitsa" }));
    expect(onSelectSite).toHaveBeenCalledWith("zlatitsa");
    await waitFor(() => {
      expect(leafletMocks.fitBounds).toHaveBeenCalled();
    });
    expect(leafletMocks.panInside).toHaveBeenCalledWith(
      [selectedSite.latitude, selectedSite.longitude],
      expect.objectContaining({ animate: true }),
    );
    expect(createSiteBounds(sites).isValid()).toBe(true);
  });

  it("explains tile failure while labels and selection remain usable", async () => {
    const sites = createSitesResponse().sites;
    const selectedSite = sites[0];

    if (selectedSite === undefined) {
      throw new Error("Expected a site fixture.");
    }

    render(<SiteMap onSelectSite={vi.fn()} selectedSite={selectedSite} sites={sites} />);
    expect(screen.getByText("Loading basemap…")).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Finish tiles" }));
    expect(screen.queryByText("Loading basemap…")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Fail tiles" }));
    expect(
      screen.getByText(
        "The basemap could not be loaded. Location labels and the selector remain available.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: /selected/ })).toBeVisible();
  });

  it("disables viewport animation when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", () => ({
      addEventListener: vi.fn(),
      matches: true,
      removeEventListener: vi.fn(),
    }));
    const sites = createSitesResponse().sites;
    const selectedSite = sites[0];

    if (selectedSite === undefined) {
      throw new Error("Expected a site fixture.");
    }

    render(<SiteMap onSelectSite={vi.fn()} selectedSite={selectedSite} sites={sites} />);

    await waitFor(() => {
      expect(leafletMocks.panInside).toHaveBeenCalledWith(
        [selectedSite.latitude, selectedSite.longitude],
        expect.objectContaining({ animate: false, duration: 0 }),
      );
    });
  });
});
