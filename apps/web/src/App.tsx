import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./app/app-routes.js";
import type { DashboardApi } from "./services/api/dashboard-api.js";

export interface AppProps {
  readonly dashboardApi: DashboardApi;
}

export const App = ({ dashboardApi }: AppProps) => (
  <BrowserRouter>
    <AppRoutes dashboardApi={dashboardApi} />
  </BrowserRouter>
);
