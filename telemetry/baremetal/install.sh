#!/bin/bash
#
# Install the telemetry stack on a bare-metal host from the files fetch.sh
# downloaded: the binaries under a prefix of your choosing, the container
# stack's configurations rewritten for one host (every store on 127.0.0.1,
# only the collector's OTLP/HTTP port and Grafana reachable from outside), a
# control script for hosts without systemd, rendered systemd units for hosts
# with it, and the environment file the QFw processes need.
#
#   telemetry/baremetal/install.sh --prefix DIR [options]
#
#   --prefix DIR        where to install (created; no root needed if writable)
#   --dist DIR          fetch.sh's output (default ./telemetry-dist)
#   --advertise HOST    the name the QFw processes reach this host by; it goes
#                       into QFW_TELEMETRY_ENDPOINT (default: hostname -s)
#   --listen ADDR       the address the collector accepts OTLP on (default
#                       0.0.0.0; the cluster-facing interface's address to be
#                       stricter)
#   --grafana-addr ADDR Grafana's listen address (default 127.0.0.1: reach it
#                       through an ssh tunnel; 0.0.0.0 to open it directly)
#   --grafana-port N    Grafana's port (default 3000)
#   --user NAME         the account the systemd system units run as (default:
#                       the invoking user)
#   --source DIR        the telemetry directory to take the configurations and
#                       dashboards from (default: this script's parent)
#
# Rerunnable: binaries are unpacked again, configurations rendered again, the
# data directories and the Grafana admin password are kept.
set -euo pipefail

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$(cd "${KIT}/.." && pwd)"
PREFIX=""; DIST="telemetry-dist"; ADVERTISE=""; LISTEN="0.0.0.0"
GRAFANA_ADDR="127.0.0.1"; GRAFANA_PORT="3000"; RUN_USER="${USER:-$(id -un)}"
while [[ $# -gt 0 ]]; do
	case "$1" in
		--prefix) PREFIX="$2"; shift 2 ;;
		--dist) DIST="$2"; shift 2 ;;
		--advertise) ADVERTISE="$2"; shift 2 ;;
		--listen) LISTEN="$2"; shift 2 ;;
		--grafana-addr) GRAFANA_ADDR="$2"; shift 2 ;;
		--grafana-port) GRAFANA_PORT="$2"; shift 2 ;;
		--user) RUN_USER="$2"; shift 2 ;;
		--source) SOURCE="$(cd "$2" && pwd)"; shift 2 ;;
		-h|--help) sed -n '2,28p' "$0"; exit 0 ;;
		*) echo "install.sh: unknown option $1" >&2; exit 2 ;;
	esac
done
[[ -n "${PREFIX}" ]] || { echo "install.sh: --prefix is required" >&2; exit 2; }
[[ -r "${DIST}/MANIFEST" ]] || { echo "install.sh: no MANIFEST in ${DIST}; run fetch.sh first" >&2; exit 2; }
[[ -z "${ADVERTISE}" ]] && ADVERTISE="$(hostname -s)"
for f in otel-collector.yaml prometheus.yml tempo.yaml loki.yaml \
	grafana/provisioning/datasources/qfw.yaml grafana/provisioning/dashboards/qfw.yaml; do
	[[ -r "${SOURCE}/${f}" ]] || { echo "install.sh: ${SOURCE}/${f} not found (pass --source)" >&2; exit 2; }
done
command -v python3 >/dev/null || { echo "install.sh: python3 is required" >&2; exit 2; }

mkdir -p "${PREFIX}"
PREFIX="$(cd "${PREFIX}" && pwd)"
DIST="$(cd "${DIST}" && pwd)"
# shellcheck disable=SC1091
. "${DIST}/MANIFEST"
ETC="${PREFIX}/etc"; DATA="${PREFIX}/data"
mkdir -p "${PREFIX}/bin" "${PREFIX}/lib" "${ETC}/grafana/dashboards" "${PREFIX}/log" "${PREFIX}/run" "${PREFIX}/systemd/system" "${PREFIX}/systemd/user" \
	"${DATA}/prometheus" "${DATA}/tempo" "${DATA}/loki" "${DATA}/grafana" "${DATA}/grafana/plugins"

echo "install.sh: binaries (linux/${arch}) into ${PREFIX}"
tmp="$(mktemp -d)"; trap 'rm -rf "${tmp}"' EXIT
tar -xzf "${DIST}/${otelcol}" -C "${tmp}" otelcol-contrib
install -m 0755 "${tmp}/otelcol-contrib" "${PREFIX}/bin/otelcol-contrib"
tar -xzf "${DIST}/${prometheus}" -C "${tmp}"
install -m 0755 "${tmp}/${prometheus%.tar.gz}/prometheus" "${tmp}/${prometheus%.tar.gz}/promtool" "${PREFIX}/bin/"
tar -xzf "${DIST}/${tempo}" -C "${tmp}" tempo
install -m 0755 "${tmp}/tempo" "${PREFIX}/bin/tempo"
if command -v unzip >/dev/null 2>&1; then
	unzip -qo "${DIST}/${loki}" -d "${tmp}"
else
	python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "${DIST}/${loki}" "${tmp}"
fi
install -m 0755 "${tmp}/${loki%.zip}" "${PREFIX}/bin/loki"
rm -rf "${PREFIX}/lib/grafana"
# The archive's top directory has carried different names across releases.
# (tar may get SIGPIPE from head, which pipefail would turn into a failure)
grafana_dir="$( (tar -tzf "${DIST}/${grafana}" || true) | head -1 | cut -d/ -f1)"
tar -xzf "${DIST}/${grafana}" -C "${tmp}"
[[ -x "${tmp}/${grafana_dir}/bin/grafana" ]] || { echo "install.sh: no bin/grafana under ${grafana_dir} in ${grafana}" >&2; exit 1; }
mv "${tmp}/${grafana_dir}" "${PREFIX}/lib/grafana"
for b in otelcol-contrib prometheus tempo loki; do printf "  %-16s %s\n" "${b}" "$("${PREFIX}/bin/${b}" --version 2>&1 | head -1 | cut -c1-70)"; done
printf "  %-16s %s\n" grafana "$("${PREFIX}/lib/grafana/bin/grafana" --version 2>&1 | head -1 | cut -c1-70)"

echo "install.sh: configurations into ${ETC}"
cp "${SOURCE}/grafana/dashboards/"*.json "${ETC}/grafana/dashboards/"
mkdir -p "${ETC}/grafana/provisioning/datasources" "${ETC}/grafana/provisioning/dashboards"
# A random admin password on the first install, kept afterwards.
if [[ ! -r "${ETC}/grafana.env" ]]; then
	umask 077
	printf 'GF_SECURITY_ADMIN_PASSWORD=%s\n' "$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')" > "${ETC}/grafana.env"
	umask 022
fi
PREFIX="${PREFIX}" ETC="${ETC}" DATA="${DATA}" SOURCE="${SOURCE}" LISTEN="${LISTEN}" ADVERTISE="${ADVERTISE}" \
GRAFANA_ADDR="${GRAFANA_ADDR}" GRAFANA_PORT="${GRAFANA_PORT}" python3 - <<'PY'
import os, pathlib, re
E = os.environ
src, etc, data = pathlib.Path(E["SOURCE"]), pathlib.Path(E["ETC"]), E["DATA"]

def render(name, edits, dest=None):
	text = (src / name).read_text()
	for old, new in edits:
		if old not in text:
			raise SystemExit(f"install.sh: {name}: expected text not found: {old!r}; the source config changed, update install.sh")
		text = text.replace(old, new)
	(etc / (dest or name)).parent.mkdir(parents=True, exist_ok=True)
	(etc / (dest or name)).write_text(text)
	print(f"  {dest or name}")

# The collector: OTLP/HTTP on the cluster-facing address, nothing else open;
# the gRPC receiver goes (QFw speaks HTTP, and Tempo owns 4317 on this host);
# a health endpoint for the control script and the units.
render("otel-collector.yaml", [
	("        endpoint: 0.0.0.0:4318\n", f"        endpoint: {E['LISTEN']}:4318\n"),
	("      grpc:\n        endpoint: 0.0.0.0:4317\n", ""),
	("    endpoint: tempo:4317\n", "    endpoint: 127.0.0.1:4317\n"),
	("    endpoint: http://loki:3100/otlp\n", "    endpoint: http://127.0.0.1:3100/otlp\n"),
	("    endpoint: 0.0.0.0:8889\n", "    endpoint: 127.0.0.1:8889\n"),
	("\nservice:\n", "\nextensions:\n  health_check:\n    endpoint: 127.0.0.1:13133\n\nservice:\n  extensions: [health_check]\n"),
])
render("prometheus.yml", [
	('      - targets: ["otel-collector:8889"]\n', '      - targets: ["127.0.0.1:8889"]\n'),
])
# Tempo: the collector reaches it on 4317 locally; its own HTTP receiver would
# collide with the collector's 4318, so it goes.
render("tempo.yaml", [
	("server:\n  http_listen_port: 3200\n", "server:\n  http_listen_address: 127.0.0.1\n  http_listen_port: 3200\n  grpc_listen_address: 127.0.0.1\n"),
	("          endpoint: 0.0.0.0:4317\n", "          endpoint: 127.0.0.1:4317\n"),
	("        http:\n          endpoint: 0.0.0.0:4318\n", ""),
	("      path: /var/tempo/wal\n", f"      path: {data}/tempo/wal\n"),
	("      path: /var/tempo/blocks\n", f"      path: {data}/tempo/blocks\n"),
])
render("loki.yaml", [
	# Tempo and Loki both default their gRPC port to 9095; on one host Loki moves.
	("server:\n  http_listen_port: 3100\n", "server:\n  http_listen_address: 127.0.0.1\n  grpc_listen_address: 127.0.0.1\n  grpc_listen_port: 9096\n  http_listen_port: 3100\n"),
	# Loki's components reach each other over gRPC at the advertised address,
	# which defaults to the first non-loopback interface: with gRPC bound to
	# loopback it must advertise loopback too, or its own ingester is unreachable.
	("  path_prefix: /loki\n", f"  instance_addr: 127.0.0.1\n  path_prefix: {data}/loki\n"),
	("      chunks_directory: /loki/chunks\n", f"      chunks_directory: {data}/loki/chunks\n"),
	("      rules_directory: /loki/rules\n", f"      rules_directory: {data}/loki/rules\n"),
	("  working_directory: /loki/compactor\n", f"  working_directory: {data}/loki/compactor\n"),
	("      directory: /loki/rules\n", f"      directory: {data}/loki/rules\n"),
])
render("grafana/provisioning/datasources/qfw.yaml", [
	("    url: http://prometheus:9090\n", "    url: http://127.0.0.1:9090\n"),
	("    url: http://tempo:3200\n", "    url: http://127.0.0.1:3200\n"),
	("    url: http://loki:3100\n", "    url: http://127.0.0.1:3100\n"),
])
render("grafana/provisioning/dashboards/qfw.yaml", [
	("      path: /var/lib/grafana/dashboards/qfw\n", f"      path: {etc}/grafana/dashboards\n"),
])
# Grafana's settings, the same the container gets from its environment; the
# admin password stays in grafana.env (mode 600).
(etc / "grafana.ini").write_text(f"""# Rendered by telemetry/baremetal/install.sh; edit and restart grafana.
[paths]
data = {data}/grafana
logs = {E['PREFIX']}/log/grafana
plugins = {data}/grafana/plugins
provisioning = {etc}/grafana/provisioning

[server]
http_addr = {E['GRAFANA_ADDR']}
http_port = {E['GRAFANA_PORT']}

[security]
admin_user = admin

[auth.anonymous]
enabled = true
org_role = Viewer

[users]
viewers_can_edit = true

[dashboards]
default_home_dashboard_path = {etc}/grafana/dashboards/qfw-jobs.json

[analytics]
reporting_enabled = false
check_for_updates = false

[news]
news_feed_enabled = false
""")
print("  grafana.ini")
# What the QFw processes need: one file for systemd (KEY=VALUE) and one to
# source from a shell or a profile (export KEY=VALUE).
values = [
	("QFW_TELEMETRY", "otlp"),
	("QFW_TELEMETRY_ENDPOINT", f"http://{E['ADVERTISE']}:4318"),
	("QFW_TELEMETRY_SAMPLE", "always"),
	("QFW_TELEMETRY_TRANSPORT", "1"),
	("QFW_TELEMETRY_LOGS", "debug"),
	("QFW_TELEMETRY_VENDOR", "1"),
	("OTEL_METRIC_EXPORT_INTERVAL", "5000"),
	("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", "delta"),
]
head = ("# The QFw telemetry settings for every QFw process that should report to\n"
	f"# this host: the QPM daemons here and the clients on the other nodes.\n"
	"# SAMPLE always and LOGS debug are the demonstration values; production\n"
	"# keeps metrics on with SAMPLE off or a ratio, and LOGS error.\n")
(etc / "qfw-telemetry.env").write_text(head + "".join(f"{k}={v}\n" for k, v in values))
(etc / "qfw-telemetry.profile.sh").write_text(head + "".join(f"export {k}={v}\n" for k, v in values))
print("  qfw-telemetry.env, qfw-telemetry.profile.sh")
PY

echo "install.sh: scripts and units"
install -m 0755 "${KIT}/qfw-telemetry.sh" "${PREFIX}/bin/qfw-telemetry"
install -m 0755 "${KIT}/check.sh" "${PREFIX}/bin/qfw-telemetry-check"
for u in "${KIT}"/systemd/*.in; do
	name="$(basename "${u%.in}")"
	sed -e "s|@PREFIX@|${PREFIX}|g" -e "s|@USER_LINE@|User=${RUN_USER}|" -e "s|@WANTED_BY@|multi-user.target|" "${u}" > "${PREFIX}/systemd/system/${name}"
	sed -e "s|@PREFIX@|${PREFIX}|g" -e "/@USER_LINE@/d" -e "s|@WANTED_BY@|default.target|" "${u}" > "${PREFIX}/systemd/user/${name}"
done
echo "  ${PREFIX}/bin/qfw-telemetry, ${PREFIX}/bin/qfw-telemetry-check, ${PREFIX}/systemd/{system,user}/"

cat <<EOF

Installed in ${PREFIX}. What listens where:
  collector OTLP/HTTP   ${LISTEN}:4318   <- the QFw processes (open this port to the client nodes)
  Grafana               ${GRAFANA_ADDR}:${GRAFANA_PORT}
  Prometheus, Tempo, Loki, the collector's metrics and health: 127.0.0.1 only
The QFw processes use ${ETC}/qfw-telemetry.env (systemd EnvironmentFile) or
${ETC}/qfw-telemetry.profile.sh (source it); both say QFW_TELEMETRY_ENDPOINT=http://${ADVERTISE}:4318.
Grafana's admin password is in ${ETC}/grafana.env.

Next: without systemd   ${PREFIX}/bin/qfw-telemetry start && ${PREFIX}/bin/qfw-telemetry-check
      with systemd      see ${PREFIX}/systemd/ and the recipe
EOF
