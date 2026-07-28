import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./app/app-routes.js";
import { AppHeader } from "./components/app-header/AppHeader.js";
import type { DashboardApi } from "./services/api/dashboard-api.js";
import styles from "./App.module.scss";

export interface AppProps {
  readonly dashboardApi: DashboardApi;
}

export const App = ({ dashboardApi }: AppProps) => (
  <div className={styles.app}>
    <AppHeader />
    <div className={styles.frame}>
      <BrowserRouter>
        <AppRoutes dashboardApi={dashboardApi} />
      </BrowserRouter>
    </div>
  </div>
);
