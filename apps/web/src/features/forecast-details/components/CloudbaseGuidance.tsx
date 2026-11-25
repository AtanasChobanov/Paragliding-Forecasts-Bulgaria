import styles from "./ForecastDetailContent.module.scss";

export const CloudbaseGuidance = () => (
  <div className={styles.metricInformation}>
    <section>
      <h4>Height references</h4>
      <dl className={styles.heightDefinitions}>
        <dt>MSL</dt>
        <dd>Height above mean sea level.</dd>
        <dt>Model AGL</dt>
        <dd>Height above the model terrain.</dd>
        <dt>Site AGL</dt>
        <dd>Height above the launch. Negative values are below the launch.</dd>
      </dl>
    </section>
    <section>
      <h4>Cloud formation</h4>
      <p>
        Blue means no model support for local cumulus formation. It provides no usable thermal top
        or guarantee of clear skies.
      </p>
      <p>Conditional LCL is a conditional condensation level, not an estimated thermal top.</p>
    </section>
  </div>
);
