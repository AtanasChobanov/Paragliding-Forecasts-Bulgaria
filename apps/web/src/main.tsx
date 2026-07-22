import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App.js";
import { AppProviders } from "./app/AppProviders.js";
import { createDashboardQueryClient } from "./app/query-client.js";
import { loadRuntimeConfig } from "./config/runtime-config.js";

loadRuntimeConfig();
const queryClient = createDashboardQueryClient();

const rootElement = document.getElementById("root");

if (!(rootElement instanceof HTMLElement)) {
  throw new Error("The web application root element is missing.");
}

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <App />
    </AppProviders>
  </StrictMode>,
);
