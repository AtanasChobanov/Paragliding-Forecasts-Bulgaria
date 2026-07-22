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
  readonly onRetry: () => void;
  readonly retryLabel: string;
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
        {variant === "error" ? (
          <button type="button" onClick={props.onRetry}>
            {props.retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
};
