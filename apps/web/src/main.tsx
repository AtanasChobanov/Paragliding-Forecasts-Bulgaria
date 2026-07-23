import "@fontsource-variable/inter";
import "leaflet/dist/leaflet.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js";
import { AppProviders } from "./app/AppProviders.js";
import { createDashboardQueryClient } from "./app/query-client.js";
import { loadRuntimeConfig } from "./config/runtime-config.js";
import { createApiClient } from "./services/api/api-client.js";
import { createDashboardApi } from "./services/api/dashboard-api.js";
import "./styles/globals.scss";

const runtimeConfig = loadRuntimeConfig();
const queryClient = createDashboardQueryClient();
const dashboardApi = createDashboardApi(createApiClient({ baseUrl: runtimeConfig.apiBaseUrl }));

const rootElement = document.getElementById("root");

if (!(rootElement instanceof HTMLElement)) {
  throw new Error("The web application root element is missing.");
}

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <App dashboardApi={dashboardApi} />
    </AppProviders>
  </StrictMode>,
);
