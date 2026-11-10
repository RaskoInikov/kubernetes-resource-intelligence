import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type MetricsRange, type PipelineApi } from "./api";
import { ErrorNotice, JsonDetails, MetricChart, MissingDataList } from "./components";
import type {
  AnalysisReport,
  ExperimentRecord,
  LLMInputPackage,
  LLMInputSummary,
  LoadConfiguration,
  ObservationSnapshot,
  ObservationSummary,
  OperationalEvidencePackage,
  RawMetricsSnapshot,
  MetricSeries,
  WorkloadConfiguration,
  WorkloadSnapshot,
} from "./types";

function localDateTime(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function initialInterval() {
  const end = new Date();
  return {
    start: localDateTime(new Date(end.getTime() - 5 * 60_000)),
    end: localDateTime(end),
  };
}

function timestampId(prefix: string): string {
  return `${prefix}-${new Date().toISOString().replace(/\D/g, "").slice(0, 14)}`;
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    const status = error.status ? `HTTP ${error.status} · ` : "";
    const details = error.details.length ? ` — ${error.details.join("; ")}` : "";
    return `${error.operation}: ${status}${error.code}: ${error.message}${details}`;
  }
  return error instanceof Error ? error.message : "Unknown operation failure";
}

function toRange(start: string, end: string, step: number): MetricsRange {
  return {
    interval_start: new Date(start).toISOString(),
    interval_end: new Date(end).toISOString(),
    step_seconds: step,
  };
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function StageHeader({ number, title, state }: { number: number; title: string; state: string }) {
  return (
    <div className="stage-header">
      <span className="stage-number">{number}</span>
      <h3>{title}</h3>
      <span className="stage-state">{state}</span>
    </div>
  );
}

export function App({ client = api }: { client?: PipelineApi }) {
  const interval = useMemo(initialInterval, []);
  const [workload, setWorkload] = useState<WorkloadConfiguration>({
    schema_version: "1.0",
    cpu_request: "50m",
    cpu_limit: "100m",
    memory_request: "64Mi",
    memory_limit: "128Mi",
    replicas: 2,
  });
  const [load, setLoad] = useState<LoadConfiguration>({
    schema_version: "1.0",
    workload_mode: "mixed",
    concurrency: 4,
    request_rate: 10,
    duration_seconds: 60,
  });
  const [experimentId, setExperimentId] = useState("");
  const [workloadSnapshot, setWorkloadSnapshot] = useState<WorkloadSnapshot>();
  const [experiment, setExperiment] = useState<ExperimentRecord>();
  const [metricsStart, setMetricsStart] = useState(interval.start);
  const [metricsEnd, setMetricsEnd] = useState(interval.end);
  const [stepSeconds, setStepSeconds] = useState(5);
  const [metrics, setMetrics] = useState<RawMetricsSnapshot>();
  const [observationId, setObservationId] = useState(timestampId("obs-ui"));
  const [observation, setObservation] = useState<ObservationSnapshot>();
  const [observationSummary, setObservationSummary] = useState<ObservationSummary>();
  const [analysisId, setAnalysisId] = useState(timestampId("analysis-ui"));
  const [analysis, setAnalysis] = useState<AnalysisReport>();
  const [ragEnabled, setRagEnabled] = useState(true);
  const [evidence, setEvidence] = useState<OperationalEvidencePackage>();
  const [packageId, setPackageId] = useState(timestampId("llm-input-ui"));
  const [llmInput, setLlmInput] = useState<LLMInputPackage>();
  const [llmSummary, setLlmSummary] = useState<LLMInputSummary>();
  const [busy, setBusy] = useState<string>();
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [apiConnection, setApiConnection] = useState("Checking FastAPI…");
  const [apiConnectionFailed, setApiConnectionFailed] = useState(false);

  useEffect(() => {
    if (!experiment || experiment.lifecycle_state !== "running") return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      void client.getLoad(experiment.experiment_id).then(
        (record) => {
          if (!cancelled) {
            setExperiment(record);
            setErrors((current) => ({ ...current, load: undefined }));
          }
        },
        (error: unknown) => {
          if (!cancelled) {
            setErrors((current) => ({ ...current, load: messageFor(error) }));
          }
        },
      );
    }, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [client, experiment]);

  useEffect(() => {
    let active = true;
    client.health().then(
      () => {
        if (active) {
          setApiConnection("FastAPI connected");
          setApiConnectionFailed(false);
        }
      },
      (error: unknown) => {
        if (active) {
          setApiConnection(`FastAPI unavailable — ${messageFor(error)}`);
          setApiConnectionFailed(true);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [client]);

  async function run<T>(
    key: string,
    action: () => Promise<T>,
    complete: (value: T) => void,
  ) {
    if (busy) return;
    setBusy(key);
    setErrors((current) => ({ ...current, [key]: undefined }));
    try {
      complete(await action());
    } catch (error) {
      setErrors((current) => ({ ...current, [key]: messageFor(error) }));
    } finally {
      setBusy(undefined);
    }
  }

  const currentExperimentId = experiment?.experiment_id || experimentId;
  const metricGroups = metrics
    ? Object.entries(
        metrics.series.reduce<Record<string, MetricSeries[]>>((groups, series) => {
          (groups[series.metric_name] ??= []).push(series);
          return groups;
        }, {}),
      )
    : [];

  return (
    <main>
      <header className="topbar">
        <div>
          <p className="eyebrow">Local pipeline debugger</p>
          <h1>Kubernetes Resource Intelligence</h1>
        </div>
        <div className="scope-note">
          <strong>M11 test interface</strong>
          <span>No LLM calls or automatic remediation</span>
          <span className={apiConnectionFailed ? "api-state failed" : "api-state"} role={apiConnectionFailed ? "alert" : "status"}>{apiConnection}</span>
        </div>
      </header>

      <div className="columns">
        <section className="panel" aria-labelledby="workload-title">
          <div className="panel-title">
            <div>
              <p className="eyebrow">Control plane</p>
              <h2 id="workload-title">Workload & live metrics</h2>
            </div>
            <span className="panel-mark">01</span>
          </div>

          <article className="card">
            <h3>Application resources</h3>
            <div className="form-grid">
              <Field label="CPU request">
                <input aria-label="CPU request" value={workload.cpu_request} onChange={(event) => setWorkload({ ...workload, cpu_request: event.target.value })} />
              </Field>
              <Field label="CPU limit">
                <input aria-label="CPU limit" value={workload.cpu_limit} onChange={(event) => setWorkload({ ...workload, cpu_limit: event.target.value })} />
              </Field>
              <Field label="Memory request">
                <input aria-label="Memory request" value={workload.memory_request} onChange={(event) => setWorkload({ ...workload, memory_request: event.target.value })} />
              </Field>
              <Field label="Memory limit">
                <input aria-label="Memory limit" value={workload.memory_limit} onChange={(event) => setWorkload({ ...workload, memory_limit: event.target.value })} />
              </Field>
              <Field label="Replicas">
                <input aria-label="Replicas" type="number" min="1" max="20" value={workload.replicas} onChange={(event) => setWorkload({ ...workload, replicas: Number(event.target.value) })} />
              </Field>
            </div>
            <div className="actions">
              <button disabled={Boolean(busy)} onClick={() => run("workload", () => client.deployWorkload(workload), () => undefined)}>Deploy / update</button>
              <button className="secondary" disabled={Boolean(busy)} onClick={() => run("workload", () => client.getWorkload(), setWorkloadSnapshot)}>Refresh state</button>
              <button className="danger" disabled={Boolean(busy)} onClick={() => run("workload", () => client.deleteWorkload(), () => setWorkloadSnapshot(undefined))}>Delete application</button>
            </div>
            <ErrorNotice message={errors.workload} />
            {workloadSnapshot && (
              <div className="status-line" data-testid="workload-status">
                <strong>{workloadSnapshot.identity.namespace}/{workloadSnapshot.identity.deployment_name}</strong>
                <span>{workloadSnapshot.pods.filter((pod) => pod.ready).length}/{workloadSnapshot.pods.length} ready</span>
                <span>rv {workloadSnapshot.deployment_resource_version}</span>
              </div>
            )}
            {workloadSnapshot && <MissingDataList items={workloadSnapshot.missing_data} />}
            {workloadSnapshot && <JsonDetails label="Raw workload response" value={workloadSnapshot} />}
          </article>

          <article className="card">
            <h3>Independent load experiment</h3>
            <div className="form-grid">
              <Field label="Mode">
                <select aria-label="Load mode" value={load.workload_mode} onChange={(event) => setLoad({ ...load, workload_mode: event.target.value as LoadConfiguration["workload_mode"] })}>
                  <option value="cpu">CPU</option><option value="memory">Memory</option><option value="mixed">Mixed</option>
                </select>
              </Field>
              <Field label="Concurrency">
                <input aria-label="Concurrency" type="number" min="1" max="100" value={load.concurrency} onChange={(event) => setLoad({ ...load, concurrency: Number(event.target.value) })} />
              </Field>
              <Field label="Requests / second">
                <input aria-label="Request rate" type="number" min="0.1" max="1000" step="0.1" value={load.request_rate} onChange={(event) => setLoad({ ...load, request_rate: Number(event.target.value) })} />
              </Field>
              <Field label="Duration (seconds)">
                <input aria-label="Duration" type="number" min="1" max="3600" value={load.duration_seconds} onChange={(event) => setLoad({ ...load, duration_seconds: Number(event.target.value) })} />
              </Field>
              <Field label="Experiment ID (optional)">
                <input aria-label="Experiment ID" value={experimentId} onChange={(event) => setExperimentId(event.target.value)} placeholder="generated by API" />
              </Field>
            </div>
            <div className="actions">
              <button disabled={Boolean(busy)} onClick={() => run("load", () => client.startLoad(workload, load, experimentId || undefined), (record) => { setExperiment(record); setExperimentId(record.experiment_id); })}>Start load</button>
              <button className="secondary" disabled={Boolean(busy) || !currentExperimentId} onClick={() => run("load", () => client.getLoad(currentExperimentId), setExperiment)}>Refresh status</button>
              <button className="warning" disabled={Boolean(busy) || !currentExperimentId} onClick={() => run("load", () => client.stopLoad(currentExperimentId), setExperiment)}>Stop load only</button>
            </div>
            <p className="hint">Stopping load never deletes the application.</p>
            <ErrorNotice message={errors.load} />
            {experiment && <div className="experiment-status" data-testid="experiment-status">
              <div className="status-line"><strong>{experiment.experiment_id}</strong><span className={`pill ${experiment.lifecycle_state}`}>{experiment.lifecycle_state}</span></div>
              <dl>
                <div><dt>Submitted</dt><dd>{experiment.start_timestamp}</dd></div>
                <div><dt>Job started</dt><dd>{experiment.job_start_timestamp ?? "not observed"}</dd></div>
                <div><dt>Job UID</dt><dd>{experiment.job_uid ?? "not observed"}</dd></div>
                <div><dt>Ended</dt><dd>{experiment.end_timestamp ?? "running"}</dd></div>
                <div><dt>Termination</dt><dd>{experiment.termination_reason ? `${experiment.termination_reason} · ${experiment.termination_source}` : "pending"}</dd></div>
              </dl>
              {experiment.termination_message && <p className="hint">{experiment.termination_message}</p>}
              {experiment.load_summary && <p className="hint">
                Client outcomes: {experiment.load_summary.requests_succeeded} succeeded · {experiment.load_summary.request_failures} failed · {experiment.load_summary.request_timeouts} timed out · {experiment.load_summary.stuck_workers} stuck
              </p>}
            </div>}
            {experiment && <JsonDetails label="Raw experiment response" value={experiment} />}
          </article>

          <article className="card metrics-section">
            <h3>Live Prometheus range</h3>
            <div className="form-grid">
              <Field label="From"><input aria-label="Metrics from" type="datetime-local" value={metricsStart} onChange={(event) => setMetricsStart(event.target.value)} /></Field>
              <Field label="To"><input aria-label="Metrics to" type="datetime-local" value={metricsEnd} onChange={(event) => setMetricsEnd(event.target.value)} /></Field>
              <Field label="Step (seconds)"><input aria-label="Metrics step" type="number" min="1" max="60" value={stepSeconds} onChange={(event) => setStepSeconds(Number(event.target.value))} /></Field>
            </div>
            <button disabled={Boolean(busy)} onClick={() => run("metrics", () => client.queryMetrics(toRange(metricsStart, metricsEnd, stepSeconds)), setMetrics)}>Query live metrics</button>
            <ErrorNotice message={errors.metrics} />
            {metrics && <MissingDataList items={metrics.missing_data} />}
            {metrics && <p className="hint">Collected {metrics.series.length} source series at {metrics.collected_at}. Values are raw; absent signals remain absent.</p>}
            {metricGroups.map(([name, series]) => (
              <div className="metric-group" key={name}>
                <h4>{name} <span>{series?.length ?? 0} series</span></h4>
                {series?.map((item, index) => <MetricChart key={`${name}:${index}`} series={item} />)}
              </div>
            ))}
            {metrics && <JsonDetails label="Raw metrics response" value={metrics} />}
          </article>
        </section>

        <section className="panel" aria-labelledby="analysis-title">
          <div className="panel-title">
            <div><p className="eyebrow">Evidence pipeline</p><h2 id="analysis-title">Observation → LLM input</h2></div>
            <span className="panel-mark">02</span>
          </div>

          <article className="card stage">
            <StageHeader number={1} title="Observation" state={observationSummary?.quality_status ?? "not collected"} />
            <div className="form-grid">
              <Field label="Observation ID"><input aria-label="Observation ID" value={observationId} onChange={(event) => setObservationId(event.target.value)} /></Field>
              <Field label="From"><input aria-label="Observation from" type="datetime-local" value={metricsStart} onChange={(event) => setMetricsStart(event.target.value)} /></Field>
              <Field label="To"><input aria-label="Observation to" type="datetime-local" value={metricsEnd} onChange={(event) => setMetricsEnd(event.target.value)} /></Field>
            </div>
            <div className="actions">
              <button disabled={Boolean(busy) || !observationId} onClick={() => run("observation", async () => { const snapshot = await client.createObservation(toRange(metricsStart, metricsEnd, stepSeconds), observationId); const summary = await client.getObservationSummary(snapshot.observation_id); return { snapshot, summary }; }, ({ snapshot, summary }) => { setObservation(snapshot); setObservationSummary(summary); setAnalysis(undefined); setEvidence(undefined); setLlmInput(undefined); setLlmSummary(undefined); })}>Collect observation</button>
              <button className="secondary" disabled={Boolean(busy) || !observationId} onClick={() => run("observation", async () => ({ snapshot: await client.getObservation(observationId), summary: await client.getObservationSummary(observationId) }), ({ snapshot, summary }) => { setObservation(snapshot); setObservationSummary(summary); setAnalysis(undefined); setEvidence(undefined); setLlmInput(undefined); setLlmSummary(undefined); })}>Load saved</button>
            </div>
            <ErrorNotice message={errors.observation} />
            {observationSummary && <div className="summary-grid"><span><strong>{observationSummary.sample_count}</strong> samples</span><span><strong>{observationSummary.normalized_series_count}</strong> series</span><span><strong>{observationSummary.issue_count}</strong> issues</span></div>}
            {observation && <JsonDetails label="Observation artifact" value={observation} />}
          </article>

          <article className="card stage">
            <StageHeader number={2} title="Deterministic analysis" state={analysis?.sufficiency ?? "waiting for observation"} />
            <Field label="Analysis ID (optional)"><input aria-label="Analysis ID" value={analysisId} onChange={(event) => setAnalysisId(event.target.value)} /></Field>
            <button disabled={Boolean(busy) || !observationSummary} title={!observationSummary ? "Load or collect an observation first" : undefined} onClick={() => run("analysis", () => client.analyze(observationSummary!.observation_id, analysisId || undefined), (report) => { setAnalysis(report); setEvidence(undefined); setLlmInput(undefined); setLlmSummary(undefined); })}>Run M5 analysis</button>
            {!observationSummary && <p className="prerequisite">Requires a loaded observation.</p>}
            <ErrorNotice message={errors.analysis} />
            {analysis && (
              <>
                <div className="summary-grid"><span><strong>{analysis.statistics.length}</strong> statistics</span><span><strong>{analysis.conditions.length}</strong> conditions</span><span><strong>{analysis.recommendations.length}</strong> recommendations</span></div>
                <h4>Conditions</h4>
                <div className="finding-list">{analysis.conditions.map((condition) => <div className={`finding ${condition.severity}`} key={condition.condition_id}><strong>{condition.condition_type}</strong><span>{condition.message}</span><small>{condition.observed_value} ≥ {condition.threshold}</small></div>)}</div>
                <h4>Recommendations — approval required</h4>
                <div className="finding-list">{analysis.recommendations.map((recommendation) => <div className="finding recommendation" key={recommendation.recommendation_id}><strong>{recommendation.resource}: {recommendation.current_value} → {recommendation.recommended_value}</strong><span>{recommendation.rationale}</span><small>Not applied</small></div>)}</div>
                <h4>Risks & uncertainties</h4>
                <ul>{analysis.risks_and_uncertainties.map((risk) => <li key={risk}>{risk}</li>)}</ul>
                <JsonDetails label="Complete M5 response" value={analysis} />
              </>
            )}
          </article>

          <article className="card stage">
            <StageHeader number={3} title="RAG evidence" state={!ragEnabled ? "disabled" : evidence ? `${evidence.bundles.length} queries` : "not retrieved"} />
            <label className="toggle"><input aria-label="Enable RAG" type="checkbox" checked={ragEnabled} onChange={(event) => { setRagEnabled(event.target.checked); if (!event.target.checked) { setEvidence(undefined); setLlmInput(undefined); setLlmSummary(undefined); } }} /><span>Enable RAG retrieval</span></label>
            <button disabled={Boolean(busy) || !ragEnabled || !analysis} title={!analysis ? "Run M5 first" : !ragEnabled ? "RAG is disabled" : undefined} onClick={() => run("evidence", () => client.retrieveEvidence(analysis!), (result) => { setEvidence(result); setLlmInput(undefined); setLlmSummary(undefined); })}>Retrieve M8 evidence</button>
            {!analysis && <p className="prerequisite">Requires the exact M5 report.</p>}
            {!ragEnabled && <p className="prerequisite">Analysis remains available; M8 and M9 are intentionally paused.</p>}
            <ErrorNotice message={errors.evidence} />
            {evidence?.bundles.map((bundle) => <details className="evidence" key={bundle.query_id}><summary><span>{bundle.query_kind}</span>{bundle.query}</summary>{bundle.retrieval.hits.map((hit, index) => <div className="hit" key={hit.chunk.chunk_id}><div><strong>#{index + 1} {hit.chunk.document_title}</strong><span>{hit.chunk.section}</span></div><code>{hit.score.toFixed(4)} final · {hit.semantic_score?.toFixed(4) ?? "n/a"} semantic · {hit.lexical_match_ratio?.toFixed(4) ?? "n/a"} lexical</code><p>{hit.chunk.text}</p><small>{hit.chunk.chunk_id} · {hit.chunk.verification_status}</small>{hit.chunk.sources.map((source) => <a key={source.uri} href={source.uri} target="_blank" rel="noreferrer">{source.title}</a>)}</div>)}</details>)}
            {evidence && <JsonDetails label="Complete M8 response" value={evidence} />}
          </article>

          <article className="card stage">
            <StageHeader number={4} title="LLM input package" state={llmSummary?.retrieval_status ?? llmInput?.retrieval_status ?? "not created"} />
            <Field label="Package ID"><input aria-label="Package ID" value={packageId} onChange={(event) => setPackageId(event.target.value)} /></Field>
            <div className="actions">
              <button disabled={Boolean(busy) || !analysis || !evidence || !packageId} title={!evidence ? "Retrieve matching M8 evidence first" : undefined} onClick={() => run("package", async () => { const item = await client.createLLMInput(analysis!, evidence!, packageId); const summary = await client.getLLMInputSummary(item.package_id); return { item, summary }; }, ({ item, summary }) => { setLlmInput(item); setLlmSummary(summary); })}>Create M9 package</button>
              <button className="secondary" disabled={Boolean(busy) || !packageId} onClick={() => run("package", async () => ({ item: await client.getLLMInput(packageId), summary: await client.getLLMInputSummary(packageId) }), ({ item, summary }) => { setLlmInput(item); setLlmSummary(summary); })}>Load saved package</button>
            </div>
            {!evidence && <p className="prerequisite">Requires matching M5 and M8 contracts. No prompt is invented when RAG is off.</p>}
            <ErrorNotice message={errors.package} />
            {llmSummary && <div className="package-summary"><div className="summary-grid"><span><strong>{llmSummary.query_count}</strong> queries</span><span><strong>{llmSummary.hit_reference_count}</strong> hit references</span><span><strong>{llmSummary.excerpt_count}</strong> excerpts</span></div><code title={llmSummary.package_sha256}>sha256 {llmSummary.package_sha256}</code></div>}
            {llmInput && <><p className="hint">Created {llmInput.created_at}. This package is inspectable input only; no LLM was invoked.</p><JsonDetails label="Complete validated LLM input" value={llmInput} /></>}
          </article>
        </section>
      </div>
      {busy && <div className="busy" role="status">Running {busy}…</div>}
    </main>
  );
}
