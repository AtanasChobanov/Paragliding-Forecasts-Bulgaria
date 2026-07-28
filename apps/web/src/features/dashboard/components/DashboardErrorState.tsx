import { ContentState } from "../../../components/content-state/ContentState.js";
import { presentDashboardError } from "../dashboard-error-presentation.js";

export interface DashboardErrorStateProps {
  readonly compatibilityTitle: string;
  readonly error: unknown;
  readonly onRetry: () => void;
  readonly requestTitle: string;
  readonly retryLabel: string;
}

export const DashboardErrorState = ({
  compatibilityTitle,
  error,
  onRetry,
  requestTitle,
  retryLabel,
}: DashboardErrorStateProps) => {
  const presentation = presentDashboardError(error);
  const title = presentation.category === "api-compatibility" ? compatibilityTitle : requestTitle;

  return (
    <ContentState
      message={presentation.message}
      onRetry={presentation.retryable ? onRetry : undefined}
      requestId={presentation.requestId}
      retryLabel={presentation.retryable ? retryLabel : undefined}
      title={title}
      variant="error"
    />
  );
};
