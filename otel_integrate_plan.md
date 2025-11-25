# OpenTelemetry Integration Plan

## Objectives
- Capture GPU/DCGM metrics with trace context so we can correlate throttling or ECC events with crawler/agent workloads.
- Trace crawler → agent → DB flows, including queues and background jobs, to spot propagation delays and bottlenecks.
- Surface kernel/NVIDIA driver logs in a structured form that ties back to spans.
- Maintain existing Prometheus-based alerting while enabling OTLP exports for tracing and logging backends (Tempo/Jaeger/Loki or hosted options).

## Collector Topology
- Deploy a node-level OpenTelemetry Collector (system service) on each workload host.
  - Receivers: `prometheus` (scrape DCGM exporter + node exporter), `hostmetrics`, `filelog` (kernel/NVIDIA logs), `otlp` (from instrumented apps running locally).
  - Processors: `resource` (tag host, GPU ID, environment), `attributes` (normalize labels), `batch`, optional `filter` or `memory_limiter`.
  - Exporters: `otlp` → central collector, optional `prometheus_remote_write` when Prometheus cannot scrape directly.
- Run a central collector (or HA pair) to receive OTLP data from nodes, enforce sampling/metric views, and fan out to:
  - Prometheus (metrics) via native scrape or remote_write.
  - Tempo/Jaeger (traces).
  - Loki/Elastic (logs) or another vendor-neutral store.

## Instrumentation Rollout
1. **Phase 1 – Core services**: enable auto-instrumentation in Python crawlers, agents, and API gateways with W3C context propagation. Add custom spans around GPU scheduling, model inference, DB calls.
2. **Phase 2 – Background jobs**: instrument queues, schedulers, and training jobs. Leverage baggage for article IDs / job IDs to unify traces and logs.
3. **Phase 3 – Shell / cron tasks**: wrap operational scripts via the OTel logging SDK or exec wrappers so kernel log alerts can be correlated back to the triggering job.

## Prometheus Strategy
- Short term: keep Prometheus as primary metrics store/alerting. Either continue native scrape of DCGM + node exporters or ingest via collector remote_write.
- Update alert rules and Grafana dashboards to use the OTel-normalized metric names while keeping semantics identical.
- Long term: if Prometheus scaling becomes painful, switch collector exporters to an OTLP-native metrics backend without touching instrumentation.

## Deployment Steps
1. Package collector configs under `infrastructure/monitoring/otel/`, including node template, central collector template, and systemd/Helm snippets.
2. Roll out node collectors: install binaries, drop config, enable systemd, validate scrapes (`curl 127.0.0.1:9400/metrics`) and OTLP ingestion.
3. Deploy central collector: configure OTLP receivers, exporters to Prometheus remote_write plus tracing/log stores, add TLS/auth as needed.
4. Instrument apps: add `opentelemetry-sdk` and OTLP exporter pointing at `localhost:4317`, verify spans and exemplars appear in the tracing backend and GPU metric panels.
5. Logging integration: configure `filelog` receiver for `/var/log/kern.log` and NVIDIA logs, map severity to `SeverityNumber`, forward to Loki/Elastic.
6. Observability UX: update Grafana with Tempo/Loki panels and correlation dashboards (GPU throttling vs crawler latency, etc.).
7. Runbooks/tests: document restart commands, sampling knobs, collector dry-run checks (`otelcol --config ... --dry-run`), and add CI validations for OTLP exporter health.

## Outcome
This hybrid architecture plugs the current gaps—GPU telemetry correlation, distributed traces, kernel log visibility—while preserving Prometheus for alerts. Switching or augmenting backends later only requires adjusting collector exporters because instrumentation already speaks OpenTelemetry.
