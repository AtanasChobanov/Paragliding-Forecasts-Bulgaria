import type { Site, SiteSlug } from "@paragliding-forecasts/contracts";
import { divIcon, latLngBounds, type LeafletEventHandlerFnMap, type LatLngBounds } from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";

import { getSiteLabelPresentation, openStreetMapStandardProvider } from "../map-provider.js";
import styles from "./SiteMap.module.scss";

export interface SiteMapProps {
  readonly onSelectSite: (siteSlug: SiteSlug) => void;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

export const createSiteBounds = (sites: readonly Site[]): LatLngBounds =>
  latLngBounds(sites.map((site) => [site.latitude, site.longitude]));

const usePrefersReducedMotion = (): boolean => {
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");

    const updatePreference = () => {
      setReducedMotion(query.matches);
    };

    query.addEventListener("change", updatePreference);
    return () => {
      query.removeEventListener("change", updatePreference);
    };
  }, []);

  return reducedMotion;
};

interface MapViewportControllerProps {
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

const MapViewportController = ({ selectedSite, sites }: MapViewportControllerProps) => {
  const map = useMap();
  const reducedMotion = usePrefersReducedMotion();
  const siteSignature = sites
    .map((site) => `${String(site.id)}:${String(site.latitude)}:${String(site.longitude)}`)
    .join("|");

  useEffect(() => {
    map.fitBounds(createSiteBounds(sites), {
      animate: false,
      maxZoom: 8,
      padding: [28, 28],
    });
    map.invalidateSize();
  }, [map, siteSignature, sites]);

  useEffect(() => {
    map.panInside([selectedSite.latitude, selectedSite.longitude], {
      animate: !reducedMotion,
      duration: reducedMotion ? 0 : 0.25,
      padding: [44, 44],
    });
  }, [map, reducedMotion, selectedSite.latitude, selectedSite.longitude]);

  return null;
};

interface SiteMarkerProps {
  readonly onSelectSite: (siteSlug: SiteSlug) => void;
  readonly selected: boolean;
  readonly site: Site;
}

const SiteMarker = ({ onSelectSite, selected, site }: SiteMarkerProps) => {
  const icon = useMemo(
    () =>
      divIcon({
        className: [styles.marker, selected ? styles.selectedMarker : undefined]
          .filter((candidate): candidate is string => candidate !== undefined)
          .join(" "),
        html: '<span aria-hidden="true"></span>',
        iconAnchor: selected ? [15, 32] : [12, 27],
        iconSize: selected ? [30, 34] : [24, 29],
        tooltipAnchor: [0, -18],
      }),
    [selected],
  );
  const label = getSiteLabelPresentation(site.slug);
  const eventHandlers = useMemo<LeafletEventHandlerFnMap>(
    () => ({
      click: () => {
        onSelectSite(site.slug);
      },
    }),
    [onSelectSite, site.slug],
  );

  return (
    <Marker
      eventHandlers={eventHandlers}
      icon={icon}
      keyboard={false}
      position={[site.latitude, site.longitude]}
      title={`${site.name}${selected ? " (selected)" : ""}`}
    >
      <Tooltip
        className={selected ? styles.selectedTooltip : styles.tooltip}
        direction={label.direction}
        interactive={false}
        offset={label.offset}
        opacity={1}
        permanent
      >
        {site.name}
      </Tooltip>
    </Marker>
  );
};

type TileState = "error" | "loading" | "ready";

export const SiteMap = ({ onSelectSite, selectedSite, sites }: SiteMapProps) => {
  const [tileState, setTileState] = useState<TileState>("loading");
  const bounds = useMemo(() => createSiteBounds(sites), [sites]);
  const tileEventHandlers = useMemo<LeafletEventHandlerFnMap>(
    () => ({
      load: () => {
        setTileState((current) => (current === "error" ? current : "ready"));
      },
      loading: () => {
        setTileState((current) => (current === "error" ? current : "loading"));
      },
      tileerror: () => {
        setTileState("error");
      },
    }),
    [],
  );

  return (
    <div className={styles.region} role="region" aria-label="Interactive forecast location map">
      <div className={styles.mapFrame}>
        <MapContainer
          attributionControl
          bounds={bounds}
          boundsOptions={{ maxZoom: 8, padding: [28, 28] }}
          className={styles.map ?? ""}
          keyboard={false}
          maxZoom={12}
          minZoom={6}
          scrollWheelZoom={false}
          zoomControl
        >
          <TileLayer
            attribution={openStreetMapStandardProvider.attribution}
            eventHandlers={tileEventHandlers}
            maxZoom={openStreetMapStandardProvider.maximumZoom}
            url={openStreetMapStandardProvider.url}
          />
          <MapViewportController selectedSite={selectedSite} sites={sites} />
          {sites.map((site) => (
            <SiteMarker
              key={site.id}
              onSelectSite={onSelectSite}
              selected={site.slug === selectedSite.slug}
              site={site}
            />
          ))}
        </MapContainer>
        {tileState === "loading" ? (
          <p aria-live="polite" className={styles.mapState}>
            Loading basemap…
          </p>
        ) : null}
        {tileState === "error" ? (
          <p className={styles.mapState} role="status">
            The basemap could not be loaded. Location labels and the selector remain available.
          </p>
        ) : null}
      </div>
      <p className={styles.instructions}>
        Select a pin to update the dashboard. For keyboard operation, use the location selector
        above. Scroll-wheel zoom is disabled; use the visible map controls.
      </p>
    </div>
  );
};
