import type { MetricSeries, MissingData } from "./types";

export function ErrorNotice({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div className="error" role="alert">
      {message}
    </div>
  );
}

export function JsonDetails({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="json-details">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function MissingDataList({ items }: { items: MissingData[] }) {
  if (items.length === 0) return null;
  return (
    <div className="missing-data">
      <strong>Missing data — not zero</strong>
      <ul>
        {items.map((item) => (
          <li key={`${item.source}:${item.field}`}>
            <code>{item.field}</code>: {item.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function points(series: MetricSeries): string {
  const values = series.samples.map((sample) => sample.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 360;
  const height = 92;
  return series.samples
    .map((sample, index) => {
      const x = series.samples.length === 1 ? width / 2 : (index / (series.samples.length - 1)) * width;
      const y = height - ((sample.value - min) / span) * (height - 8) - 4;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function MetricChart({ series }: { series: MetricSeries }) {
  const first = series.samples.at(0);
  const last = series.samples.at(-1);
  const label = Object.entries(series.labels)
    .filter(([key]) => ["pod", "container", "code", "le"].includes(key))
    .map(([key, value]) => `${key}=${value}`)
    .join(" · ");
  return (
    <article className="metric-card">
      <div className="metric-heading">
        <div>
          <strong>{series.metric_name}</strong>
          <small>{label || "workload aggregate"}</small>
        </div>
        <span>{series.unit}</span>
      </div>
      <svg viewBox="0 0 360 100" role="img" aria-label={`${series.metric_name} trace`}>
        <line x1="0" y1="96" x2="360" y2="96" />
        <polyline points={points(series)} />
      </svg>
      <div className="metric-foot">
        <span>{first ? `${first.value} @ ${new Date(first.timestamp).toLocaleTimeString()}` : "No samples"}</span>
        <span>{last ? `${last.value} @ ${new Date(last.timestamp).toLocaleTimeString()}` : ""}</span>
      </div>
    </article>
  );
}
