import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { AppProviders } from "../../src/app/AppProviders.js";

export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: Infinity,
        retry: false,
      },
    },
  });

export const renderWithQueryClient = (
  ui: ReactElement,
  queryClient: QueryClient = createTestQueryClient(),
) => ({
  queryClient,
  ...render(<AppProviders queryClient={queryClient}>{ui}</AppProviders>),
});
