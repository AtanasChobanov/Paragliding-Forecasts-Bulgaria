import { Route, Routes } from "react-router-dom";

import { DashboardRoute } from "../routes/dashboard/dashboard-route.js";
import { ForecastDetailsRoute } from "../routes/forecast-details/forecast-details-route.js";
import type { DashboardApi } from "../services/api/dashboard-api.js";

export interface AppRoutesProps {
  readonly dashboardApi: DashboardApi;
}

export const AppRoutes = ({ dashboardApi }: AppRoutesProps) => (
  <Routes>
    <Route path="/" element={<DashboardRoute dashboardApi={dashboardApi} />} />
    <Route path="/forecast" element={<ForecastDetailsRoute dashboardApi={dashboardApi} />} />
  </Routes>
);
