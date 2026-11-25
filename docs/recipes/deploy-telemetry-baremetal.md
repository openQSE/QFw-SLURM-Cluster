# Deploy the telemetry stack on bare metal

The container cluster runs its telemetry stack (the OpenTelemetry
Collector, Prometheus, Tempo, Loki and Grafana) from
`docker-compose.telemetry.yml`. A real site has no containers, and often no
route to the internet. `telemetry/baremetal/` installs the same stack, from
the same configurations and dashboards, as plain processes on one host, and
says what the QFw processes on every node need in order to report to it.

The recipe is written for a site with three roles. The host names in it are
placeholders, `qpm-server` and `qpm-client1` to `qpm-client4`; use your own:

```text
 provider head node            QPM server                           QPM clients 1 .. 4
 (the vendor's interface) <---  QPM daemons (the QFw service plane)  <----  QFw clients (Slurm jobs)
                               the telemetry stack + Grafana        ----->  report to qpm-server:4318
```

Nothing of ours runs on the provider head node: the device's QPM on the QPM
server talks to it, and reports from there. Every QFw process, the daemons on
the QPM server and the clients on the four nodes, sends OTLP over HTTP to the
collector on the QPM server, which hands traces to Tempo, metrics to
Prometheus and log lines to Loki, all on the QPM server. Grafana on the QPM
server reads the three stores. See
[telemetry/README.md](../../telemetry/README.md) for what reports, the
dashboards, the metric names and the logs tier; this recipe only covers the
deployment.

## What listens where

| On the QPM server | Port | Who connects | Open to |
| --- | --- | --- | --- |
| Collector, OTLP/HTTP | 4318/tcp | every QFw process: the QPM daemons on the QPM server and the clients on QPM clients 1 to 4 | the QPM clients (and the QPM server itself) |
| Grafana | 3000/tcp | people, with a browser | nobody by default: reach it through an ssh tunnel (below). Open it with `--grafana-addr 0.0.0.0` if the site allows |
| Collector health, collector metrics | 13133, 8889 | the control script and Prometheus, on the same host | 127.0.0.1 only |
| Tempo | 3200, 4317, 9095 | Grafana and the collector, on the same host | 127.0.0.1 only |
| Loki | 3100, 9096 | Grafana and the collector, on the same host | 127.0.0.1 only |
| Prometheus | 9090 | Grafana, on the same host | 127.0.0.1 only |

So the only firewall change is **inbound TCP 4318 on the QPM server from the
client nodes**. Nothing needs an outbound route at run time: the stack never calls
out (Grafana's update checks, analytics and news feed are off, the dashboards
and data sources are provisioned from files, no plugins are downloaded), and
the QFw processes only talk to the QPM server. All five daemons bind ports above 1024
and run as an ordinary account; root, or the site's administrators, are needed
only for the firewall rule, for system-wide systemd units, and for a
`/etc/profile.d` entry on the clients.

What to ask the administrators for, in one line each:

- On the QPM server, with firewalld: `firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="<the client nodes' subnet>" port port="4318" protocol="tcp" accept'` then `firewall-cmd --reload`. With plain nftables or iptables, the equivalent rule for TCP 4318 from the same source. Four single-host rules work as well as one subnet rule.
- If Grafana is to be opened directly rather than tunnelled: the same for 3000, from wherever the people are.
- On a host with SELinux enforcing, binaries under the installing user's home run fine as that user. Running them from a system-wide systemd unit out of a non-standard prefix can need the binaries labelled `bin_t` (`chcon -R -t bin_t PREFIX/bin PREFIX/lib/grafana/bin`); `ausearch -m avc -ts recent` shows whether that is the case.

## The proxy, or no internet at all

`fetch.sh` downloads five release archives, about 700 MB, from GitHub and
dl.grafana.com, and verifies each against the project's published checksum.
It uses `curl`, so a proxy is the usual environment:

```bash
export https_proxy=http://proxy.example.gov:3128
export no_proxy=localhost,127.0.0.1
./telemetry/baremetal/fetch.sh --arch amd64 --dest ~/telemetry-dist
```

On a host with no route out, run it on a laptop instead, with `--arch` set
to the QPM server's architecture (`uname -m` there: `x86_64` is `amd64`), and
copy the directory in. That is the only download the stack ever needs.

## Install on the QPM server

Copy the repository's `telemetry/` directory to the QPM server (the kit takes the
configurations and dashboards from it) along with the fetched archives, then:

```bash
./telemetry/baremetal/install.sh --prefix ~/qfw-telemetry --dist ~/telemetry-dist \
    --advertise qpm-server --listen 0.0.0.0
```

- `--prefix` is where everything lives: `bin/`, `lib/grafana/`, `etc/` (the
  rendered configurations), `data/` (the three stores and Grafana's state),
  `log/`, `run/`, `systemd/`. No root is needed for a prefix you can write
  to; `/opt/qfw-telemetry` works as well, with the right ownership.
- `--advertise` is the name the QFw processes reach the QPM server by; it goes
  into the `QFW_TELEMETRY_ENDPOINT` the clients get. Use the name that resolves
  on the client nodes.
- `--listen` is the address the collector accepts OTLP on. `0.0.0.0` is
  simplest; the address of the QPM server's cluster-facing interface is stricter and
  keeps a management interface closed.

The installer prints what listens where, the path of the Grafana admin
password it generated (`etc/grafana.env`, mode 600, kept on reinstall), and
the two files the QFw processes need. Rerunning it later re-renders the
configurations and keeps the data.

## Start it

With systemd available and root, as a system service:

```bash
sudo cp ~/qfw-telemetry/systemd/system/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qfw-telemetry.target
systemctl status 'qfw-telemetry-*'
```

With systemd but no root, as the installing user's own services (lingering
keeps them up after logout):

```bash
mkdir -p ~/.config/systemd/user
cp ~/qfw-telemetry/systemd/user/* ~/.config/systemd/user/
loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now qfw-telemetry.target
systemctl --user status 'qfw-telemetry-*'
```

Without systemd, the control script runs the five as background processes
with pid files under `run/` and logs under `log/`:

```bash
~/qfw-telemetry/bin/qfw-telemetry start
~/qfw-telemetry/bin/qfw-telemetry status
~/qfw-telemetry/bin/qfw-telemetry logs otelcol
```

Either way, start order is the stores first (Tempo, Loki, Prometheus), then
the collector, then Grafana; the units declare it and the script follows it.
Loki answers its readiness check only some 25 s after starting, which the
script waits for.

## Check it

On the QPM server, the full path: readiness of the five, then one synthetic trace,
log line and metric sent through the collector and looked for in Tempo, Loki
and Prometheus, and the dashboards served by Grafana:

```bash
~/qfw-telemetry/bin/qfw-telemetry-check
```

On each client node, the one thing that matters there, that the collector
is reachable through the firewall (an HTTP 200 for each signal; `000` means
no route or a closed port):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' \
    --data '{"resourceSpans":[]}' http://qpm-server:4318/v1/traces
```

or, with the kit's check script copied over, `qfw-telemetry-check --endpoint
http://qpm-server:4318`.

To look at Grafana without opening its port, from your workstation:

```bash
ssh -L 3000:127.0.0.1:3000 qpm-server
```

and open `http://localhost:3000/`. The home dashboard is QFw Jobs; viewing
needs no login, editing the admin account from `etc/grafana.env`.

## Make the QFw processes report

The installer wrote the settings twice, with the same values:

- `etc/qfw-telemetry.env`, `KEY=VALUE` lines, for a systemd
  `EnvironmentFile=` or any launcher that reads such a file;
- `etc/qfw-telemetry.profile.sh`, `export KEY=VALUE` lines, to source.

The values are the overlay's demonstration settings: the `otlp` profile, the
endpoint `http://qpm-server:4318`, every trace sampled, the transport spans on,
the logs tier at `debug`, the vendor timeline on. For production keep the metrics on and turn the
rest down: `QFW_TELEMETRY_SAMPLE=off` or a ratio, `QFW_TELEMETRY_LOGS=error`;
the measured cost of each setting is in QFw's `docs/design/benchmarking.md`.

**The QPM daemons on the QPM server.** Whatever starts them must carry the variables
into their environment: `EnvironmentFile=/home/.../qfw-telemetry/etc/qfw-telemetry.env`
in their unit, or `source .../etc/qfw-telemetry.profile.sh` in the launcher
before the daemons start. A daemon reads the variables once, at start, so
restart them after the change. On the container cluster this is what
`qfw-site-services` does when it forwards the variables over ssh; on bare
metal the launcher is the site's own.

**QPM clients 1 to 4.** The variables must be in the environment
of the process that runs the Qiskit code, and Slurm carries a submitting
shell's environment into its jobs, so one of:

- `/etc/profile.d/qfw-telemetry.sh`, a copy of `etc/qfw-telemetry.profile.sh`,
  on each client node (root), which covers every login shell;
- the same lines in the QFw environment module or `qfw-activate` wrapper the
  site provides;
- `source` of the profile file in each user's shell before submitting.

Jobs submitted after that report as `qfw-client`; the QPM daemons as
`qfw-qpm` with the device they serve. The first job shows on QFw Jobs a few
seconds after it completes.

## Day to day

- **Where things are:** `etc/` holds every configuration, rendered from the
  repository's `telemetry/` directory with the container host names replaced
  by `127.0.0.1` and the paths by the prefix; edit there and restart the
  daemon, or change the source and rerun the installer.
- **Disk:** `data/`. Prometheus keeps 15 days, Tempo and Loki 14. On the
  container cluster a day of demonstration traffic stayed under half a
  gigabyte across the three; the figures are in QFw's design doc.
- **Logs:** `log/<daemon>.log` under the control script, `journalctl -u
  qfw-telemetry-<daemon>` (or `--user`) under systemd.
- **Upgrade:** bump the versions at the top of `fetch.sh`, fetch, rerun the
  installer, restart. The data directories are kept.
- **Remove:** stop the daemons, delete the prefix, drop the firewall rule.

## Differences from the container stack

Everything runs on one host, so the stores and the collector's health and
metrics endpoints bind `127.0.0.1`, and only the OTLP/HTTP port and Grafana
face the network. The collector's gRPC receiver is not rendered (QFw speaks
HTTP, and Tempo owns 4317 on the host), nor is Tempo's own OTLP/HTTP receiver
(the collector owns 4318), and Loki's gRPC port moves to 9096 because Tempo's
is 9095. Grafana's admin password is generated per install
rather than the overlay's fixed demonstration value. Nothing else differs:
the same versions, the same pipelines, the same dashboards and data sources.

## Troubleshooting

- **A daemon will not start, "address already in use".** Something else
  holds the port; `ss -ltnp | grep <port>` names it. The control script and
  the units never start a second copy.
- **A client gets `000` from the collector.** No route or the port is
  closed: check the firewall rule on the QPM server and that `--listen` was not
  an address the client cannot reach. `curl http://qpm-server:4318/` from the
  QPM server itself tells the two apart.
- **The check finds the trace but not the line, or the counter.** The
  collector's pipelines run separately; `log/otelcol.log` names the exporter
  that failed. Loki needs some 25 s after a start before it accepts anything.
- **Spans from the clients sit at odd offsets under the QPM's.** The hosts'
  clocks differ; every span carries its own host's time. Keep the QPM server and
  the clients on the same NTP source, and see the clocks section of QFw's design
  doc for what the per-hop histograms do about it.
- **SELinux denials in `audit.log`** after a system-wide systemd install:
  label the binaries as above.
- **Grafana shows no data but the check passes.** The dashboards look at
  the last hour by default and a fresh stack has only the check's own
  signals; run a job, or widen the time range.
