import styles from "./ContentState.module.scss";

interface BaseContentStateProps {
  readonly message: string;
  readonly title: string;
}

type InformationalContentStateProps = BaseContentStateProps & {
  readonly variant: "empty" | "info" | "loading";
  readonly onRetry?: never;
  readonly retryLabel?: never;
};

type ErrorContentStateProps = BaseContentStateProps & {
  readonly variant: "error";
  readonly onRetry?: (() => void) | undefined;
  readonly requestId?: string | null | undefined;
  readonly retryLabel?: string | undefined;
};

export type ContentStateProps = InformationalContentStateProps | ErrorContentStateProps;

export const ContentState = (props: ContentStateProps) => {
  const { message, title, variant } = props;
  const role = variant === "error" ? "alert" : variant === "loading" ? "status" : undefined;
  const className = [styles.state, styles[variant]]
    .filter((candidate): candidate is string => candidate !== undefined)
    .join(" ");

  return (
    <div className={className} role={role}>
      <span aria-hidden="true" className={styles.icon} />
      <div>
        <h3>{title}</h3>
        <p>{message}</p>
        {variant === "error" && props.requestId !== null && props.requestId !== undefined ? (
          <p className={styles.reference}>
            Request ID: <code>{props.requestId}</code>
          </p>
        ) : null}
        {variant === "error" && props.onRetry !== undefined && props.retryLabel !== undefined ? (
          <button type="button" onClick={props.onRetry}>
            {props.retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
};
