# QFw telemetry stack

The optional live view of QFw's own telemetry: the spans and metrics QFw's
job path emits under the conventions in
[`docs/design/benchmarking.md`](https://github.com/openQSE/QFw/blob/main/docs/design/benchmarking.md)
of openQSE/QFw. This directory and `docker-compose.telemetry.yml` are that
design's **collector profile**: QFw emits OTLP and stops, and everything past
the collector is a deployment choice made here with stock components.

```
 Qiskit client ──┐                     ┌──> Tempo       (traces)  ──┐
 QPM services  ──┼─ OTLP/HTTP ─> OTel ─┤                            ├─> Grafana
                 │   :4318    Collector└──> Prometheus (metrics) ──┘
                 └ QFW_TELEMETRY=otlp
```

Four containers on the cluster network, pinned in the overlay:

| Container | Image | Role | Host port |
| --- | --- | --- | --- |
| `otel-collector` | `otel/opentelemetry-collector-contrib` | Receives OTLP from QFw, forwards traces to Tempo, exposes metrics for Prometheus | `127.0.0.1:4318` |
| `prometheus` | `prom/prometheus` | Scrapes the collector every 5 s, keeps 15 days | `127.0.0.1:9090` |
| `tempo` | `grafana/tempo` | Stores traces, 14 days | `127.0.0.1:3200` |
| `grafana` | `grafana/grafana` | The dashboards, provisioned from this directory | `${QFW_GRAFANA_PORT:-3000}` on every interface |

Nothing in QFw changes when the stack is absent: with `QFW_TELEMETRY` unset,
every instrumentation site in QFw is a boolean test.

## Starting it

On a cluster that is already running:

```bash
./do_telemetry.sh up
```

That starts the four containers and nothing else. The cluster's containers
keep the environment they were created with, so QFw processes in them do not
report yet. To make them report, either:

- configure the overlay in before the cluster starts, so the containers are
  created with the QFw telemetry variables and the stack starts with them:

  ```bash
  ./do_configure.sh --telemetry ...   # writes COMPOSE_FILE into qfw-install.env
  ./do_startup.sh
  ```

- or, on a running cluster, add `COMPOSE_FILE=docker-compose.yml:docker-compose.telemetry.yml`
  to `qfw-install.env` (list `docker-compose.override.yml` between them if you
  have one) and run `./do_restart.sh --force-recreate`.

For a single shell, exporting the variables by hand works too; see the table
below. `./do_telemetry.sh` also takes `down`, `purge` (removes the data
volumes), `status`, `logs` and `url`.

## What reports, and how the variables reach it

The overlay sets these on every container that runs QFw code:

| Variable | Overlay value | Meaning |
| --- | --- | --- |
| `QFW_TELEMETRY` | `otlp` | The deployment profile: ship to a collector |
| `QFW_TELEMETRY_ENDPOINT` | `http://otel-collector:4318` | The collector's OTLP/HTTP base URL |
| `QFW_TELEMETRY_SAMPLE` | `always` (`QFW_TELEMETRY_SAMPLE` overrides) | Trace sampling. `always` for a demo or a benchmark; a ratio or `off` for production, where the metrics stay on regardless |
| `OTEL_METRIC_EXPORT_INTERVAL` | `5000` (`QFW_TELEMETRY_METRIC_INTERVAL_MS` overrides) | Milliseconds between metric exports |
| `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE` | `delta` | Each export carries what happened since the last one, not totals since the process started. See the note on short-lived clients below |

Where they come from for each kind of QFw process:

- **A shell from `do_ssh.sh`, and Slurm jobs submitted from it.** `docker exec`
  gives the shell the container's environment, and `srun`/`sbatch` carry it
  into the job. The Qiskit client reports as `service.name` `qfw-client`.
- **Site services started by `qfw-site-services`.** ssh does not carry a
  container's environment, so `qfw-site-services` forwards the variables to
  the service hosts itself (see `tools/qfw-site-services`). Each QPM reports as
  `qfw-qpm` with the device it serves on its resource (`qfw.device.name`).
- **Local service planes** started by the examples (`qfw-setup`) inherit the
  shell's environment.

The QFw side needs openQSE/QFw main with the job-path instrumentation
(QFw#115) and the endpoint fix (QFw#116), so an image built from an older
`QFW_REF` reports nothing.

## The dashboards

Provisioned from `grafana/dashboards/*.json` into the **QFw** folder. Grafana
re-reads the files every ten seconds, so a change to a file shows up on the
next refresh; a change made in the UI is not saved. Anyone who can reach the
port can view; `admin` (password `QFW_GRAFANA_ADMIN_PASSWORD`, default
`qfw-demo`) can edit.

**QFw Jobs** (`/d/qfw-jobs`, the home dashboard) is the metrics view, always
on whatever the trace sampling:

- the last five minutes: jobs completed, jobs failed, jobs per minute, end to
  end p50 and p95, devices reporting;
- jobs per minute by device, and end to end latency p50/p95 by device;
- the end to end latency distribution as a heatmap, and **where the time
  goes**, the mean of every instrumented hop (QPM receive, queue, dispatch and
  transpile; backend acquire, submit, collect and the whole execute) against
  the client's end to end mean;
- backend execute p50 by device and API path (`native`, `qrmi`, `qdmi`,
  `simulator`), and the QPM stages per job;
- the latest job traces, as a list to open.

**QFw Traces** (`/d/qfw-traces`) is trace search over Tempo: recent jobs, the
slowest provider interactions, and failed or cancelled jobs. Open one for the
waterfall of a single job: `qfw.app.job` from the client, `qfw.qpm.receive`
in the QPM across the DEFw RPC, then queue, dispatch and the provider call.

## Metric names

The collector turns QFw's OTLP metrics into Prometheus series. Dots become
underscores, units become suffixes, and resource attributes become labels:

| QFw metric | Prometheus series | Labels |
| --- | --- | --- |
| `qfw.app.job.duration` | `qfw_app_job_duration_seconds_{bucket,sum,count}` | `qfw_device_name`, `qfw_backend_kind`, `qfw_outcome` |
| `qfw.app.job.count` | `qfw_app_job_count_total` | same |
| `qfw.qpm.duration` | `qfw_qpm_duration_seconds_*` | `qfw_qpm_op` (`receive`, `queue`, `dispatch`, `transpile`), `qfw_qpm_request` on receive |
| `qfw.backend.duration` | `qfw_backend_duration_seconds_*` | `qfw_backend_op` (`execute`, `acquire`, `submit`, `collect`), `qfw_stack_api_path`, `qfw_device_name`, `qfw_backend_kind`, `qfw_outcome` |

Every series also carries `service_name` (`qfw-client` or `qfw-qpm`),
`qfw_component_role` and, from a QPM's resource, `qfw_device_name`. The
OpenTelemetry SDK's own name, language and version are dropped on the way,
so an install on a different SDK release does not split a device's series.

**One series per service and device, not per process.** A Qiskit client is
one process per Slurm job: it reports a handful of samples and exits, and
every process is a new `service.instance.id`. Left alone, Prometheus would
hold one short series per job, and `rate()` and `increase()` see nothing in
a series with a single sample. So the collector takes deltas, drops the
instance id and accumulates the deltas again
(`cumulativetodelta`, `resource`, `deltatocumulative` in
`otel-collector.yaml`), and the overlay asks QFw processes to export deltas
in the first place. The result is one counter per client population and one
per QPM device that behaves like a long-lived process's.

## Feeding the dashboards

QFw's `examples/qfw_job_stream.sh` streams Qiskit jobs through one backend:
a mix of GHZ and random circuits over a range of qubit counts, at an
interval, from one or more concurrent workers, for a number of jobs or a
length of time. From `slurmctld`, against the site fake IQM service:

```bash
./do_ssh.sh slurmctld
cd $QFW_SHARE_DIR/examples
./qfw_job_stream.sh --service-mode site --backend fake-iqm --jobs 0 --duration 600 --interval 2
```

Every job shows on QFw Jobs as it runs. `--workers 3` makes the queue and
dispatch hops visible, since the jobs then wait for each other at the QPM.

## Measuring what the telemetry costs

`telemetry/overhead-budget.sh` runs the same 300-job stream through the site
fake IQM service with telemetry off, with metrics only, and with traces on,
three times each interleaved, restarting the QPM into each state, and prints
the per-job p50 latency and the client's and the QPM's CPU for each. The
numbers from 2026-10-08 are the budget in QFw's
`docs/design/benchmarking.md`; run it again after a change to the
instrumentation and compare. It needs a QFw with the job stream example at
`QFW_PREFIX` (QFw#117 or later), the site services up, and about six
minutes.

## Checking that data flows

From `slurmctld`, with the stack up and the variables exported, run any
example; the fake IQM plane needs no hardware:

```bash
./do_ssh.sh slurmctld
export QFW_TELEMETRY=otlp QFW_TELEMETRY_ENDPOINT=http://otel-collector:4318 QFW_TELEMETRY_SAMPLE=always
cd $QFW_SHARE_DIR/examples && ./qfw_qiskit_simple.sh --service-mode local --backend fake-iqm 3
```

Then on the host:

```bash
curl -s 'localhost:9090/api/v1/label/__name__/values' | grep -o '"qfw[^"]*"'
curl -s 'localhost:3200/api/search?q=%7B%20name%20%3D%20%22qfw.app.job%22%20%7D'
```

The first lists the four metric families; the second returns the job's trace.

## Notes for a demo

- Start the cluster with `--telemetry` configured in, so the site services
  report from the first job.
- Stop services, do not kill them. Spans are batched and metrics export on an
  interval; a process that dies on a signal loses what it had not exported
  yet, bounded by the export interval.
- Grafana's port is `QFW_GRAFANA_PORT` (default 3000). The home dashboard is
  QFw Jobs; a second screen can show it from any machine that reaches the
  host.
- Take the fallback after a rehearsal, below, in case the live stack
  misbehaves on the day.

## The fallback

`telemetry/fallback.sh` freezes a good window of both dashboards in two
layers, so a demonstration has something to show whatever fails:

```bash
./telemetry/fallback.sh --from now-30m --to now        # after a rehearsal
./telemetry/fallback.sh --from 2026-11-17T16:00:00 --to 2026-11-17T17:00:00
```

- **Grafana local snapshots** of QFw Jobs and QFw Traces, with the panel
  data embedded, made through Grafana's API the way Share, Snapshot does in
  the UI. They render inside Grafana without Prometheus, Tempo or live jobs,
  the panels still answer to hover, and they live in Grafana's own volume.
  The script prints their links and keeps them in `snapshots.json`; they are
  also listed under Dashboards, Snapshots.
- **Screenshots** of both dashboards by headless Chrome, and an `index.html`
  that shows them with the snapshot links. That page needs nothing running.

The output goes to `<QFW_CONTAINER_BASE>/qfw-fallback-<timestamp>` unless
`--out` says otherwise. Chrome or Chromium is found on `PATH` or in
`/Applications`; `QFW_CHROME` names another binary. Without one the script
makes the snapshots and the page without images.

A third layer costs nothing: Prometheus keeps 15 days and Tempo 14, so any
dashboard opened with an absolute time range over a rehearsal shows it, as
long as the stack is up.

At the booth: if jobs stop or a QPM is unreachable, open a snapshot link,
or set the time range to the rehearsal; if Grafana itself is down, open
`index.html` from the fallback directory.

## Troubleshooting

- **Panels say No data.** Check the QFw process really has the variables
  (`env | grep QFW_TELEMETRY` where it runs), then the collector's log
  (`./do_telemetry.sh logs otel-collector`). A QPM on an older QFw emits
  nothing.
- **Metrics but no traces, or the reverse.** Prometheus and Tempo are fed by
  separate collector pipelines; `docker logs tempo` and the Prometheus targets
  page (`localhost:9090/targets`) show which side is unhappy.
- **Port 3000 is taken.** Set `QFW_GRAFANA_PORT` in `qfw-install.env`.
- **Dashboard edits vanish.** They are provisioned from files; edit the JSON
  in `grafana/dashboards` instead.
- **A cluster container does not have the variables.** It was created before
  the overlay was in `COMPOSE_FILE`; recreate it with
  `./do_restart.sh --force-recreate`.
