import { Route, Routes } from "react-router-dom";

import { DashboardRoute } from "../routes/dashboard/dashboard-route.js";
import type { DashboardApi } from "../services/api/dashboard-api.js";

export interface AppRoutesProps {
  readonly dashboardApi: DashboardApi;
}

export const AppRoutes = ({ dashboardApi }: AppRoutesProps) => (
  <Routes>
    <Route path="/" element={<DashboardRoute dashboardApi={dashboardApi} />} />
  </Routes>
);
