#!/bin/bash
#
# Run the bare-metal telemetry stack as plain processes, for a host without
# systemd access: start, stop, restart, status and logs for the five daemons
# installed by install.sh. With systemd, use the units install.sh rendered
# instead; this script and the units never run the same daemon twice because
# both refuse a port that is already listening.
#
#   qfw-telemetry start|stop|restart|status|logs [SERVICE]
#
# SERVICE is one of tempo loki prometheus otelcol grafana (default: all, in
# dependency order). The prefix is this script's parent directory unless
# QFW_TELEMETRY_PREFIX says otherwise.
set -u

PREFIX="${QFW_TELEMETRY_PREFIX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ETC="${PREFIX}/etc"; RUN="${PREFIX}/run"; LOG="${PREFIX}/log"; DATA="${PREFIX}/data"
ALL="tempo loki prometheus otelcol grafana"
mkdir -p "${RUN}" "${LOG}"

# The command line of each daemon; the configs were rendered by install.sh.
command_for() {
	case "$1" in
		tempo) echo "${PREFIX}/bin/tempo -config.file=${ETC}/tempo.yaml" ;;
		loki) echo "${PREFIX}/bin/loki -config.file=${ETC}/loki.yaml" ;;
		prometheus) echo "${PREFIX}/bin/prometheus --config.file=${ETC}/prometheus.yml --storage.tsdb.path=${DATA}/prometheus --storage.tsdb.retention.time=15d --web.enable-remote-write-receiver --web.listen-address=127.0.0.1:9090" ;;
		otelcol) echo "${PREFIX}/bin/otelcol-contrib --config=${ETC}/otel-collector.yaml" ;;
		grafana) echo "${PREFIX}/lib/grafana/bin/grafana server --homepath=${PREFIX}/lib/grafana --config=${ETC}/grafana.ini" ;;
		*) echo "qfw-telemetry: unknown service $1" >&2; return 2 ;;
	esac
}

# The readiness URL of each daemon.
ready_url() {
	case "$1" in
		tempo) echo "http://127.0.0.1:3200/ready" ;;
		loki) echo "http://127.0.0.1:3100/ready" ;;
		prometheus) echo "http://127.0.0.1:9090/-/ready" ;;
		otelcol) echo "http://127.0.0.1:13133/" ;;
		grafana) echo "http://127.0.0.1:${GF_SERVER_HTTP_PORT:-3000}/api/health" ;;
	esac
}

pid_of() {
	local f="${RUN}/$1.pid"
	[[ -r "${f}" ]] || return 1
	local pid
	pid="$(cat "${f}")"
	[[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && echo "${pid}"
}

start_one() {
	local svc="$1" pid
	if pid="$(pid_of "${svc}")"; then
		echo "  ${svc}: already running (pid ${pid})"
		return 0
	fi
	local cmd
	cmd="$(command_for "${svc}")" || return 2
	# Grafana reads its settings from the environment file install.sh wrote.
	if [[ "${svc}" == grafana && -r "${ETC}/grafana.env" ]]; then
		set -a; . "${ETC}/grafana.env"; set +a
	fi
	if command -v setsid >/dev/null 2>&1; then
		setsid nohup ${cmd} >> "${LOG}/${svc}.log" 2>&1 < /dev/null &
	else
		nohup ${cmd} >> "${LOG}/${svc}.log" 2>&1 < /dev/null &
	fi
	echo $! > "${RUN}/${svc}.pid"
	local url i
	url="$(ready_url "${svc}")"
	for i in $(seq 1 40); do
		if curl -fsS -o /dev/null -m 2 "${url}" 2>/dev/null; then
			echo "  ${svc}: up (pid $(cat "${RUN}/${svc}.pid"))"
			return 0
		fi
		if ! kill -0 "$(cat "${RUN}/${svc}.pid")" 2>/dev/null; then
			echo "  ${svc}: EXITED, see ${LOG}/${svc}.log" >&2
			tail -5 "${LOG}/${svc}.log" >&2
			return 1
		fi
		sleep 1
	done
	echo "  ${svc}: started (pid $(cat "${RUN}/${svc}.pid")) but not ready after 40 s, see ${LOG}/${svc}.log" >&2
	return 1
}

stop_one() {
	local svc="$1" pid
	if ! pid="$(pid_of "${svc}")"; then
		echo "  ${svc}: not running"
		rm -f "${RUN}/${svc}.pid"
		return 0
	fi
	kill "${pid}" 2>/dev/null
	local i
	for i in $(seq 1 30); do
		kill -0 "${pid}" 2>/dev/null || break
		sleep 1
	done
	if kill -0 "${pid}" 2>/dev/null; then
		kill -9 "${pid}" 2>/dev/null
		echo "  ${svc}: killed (pid ${pid})"
	else
		echo "  ${svc}: stopped (pid ${pid})"
	fi
	rm -f "${RUN}/${svc}.pid"
}

status_one() {
	local svc="$1" pid state
	if pid="$(pid_of "${svc}")"; then
		if curl -fsS -o /dev/null -m 2 "$(ready_url "${svc}")" 2>/dev/null; then
			state="UP (pid ${pid})"
		else
			state="running, not ready (pid ${pid})"
		fi
	else
		state="DOWN"
	fi
	printf "  %-11s %s\n" "${svc}" "${state}"
}

action="${1:-}"; shift || true
services="${*:-${ALL}}"
case "${action}" in
	start)
		echo "qfw-telemetry: starting in ${PREFIX}"
		rc=0; for s in ${services}; do start_one "${s}" || rc=1; done; exit ${rc} ;;
	stop)
		# Reverse order: consumers before the stores they write to.
		rev=""; for s in ${services}; do rev="${s} ${rev}"; done
		for s in ${rev}; do stop_one "${s}"; done ;;
	restart)
		"$0" stop ${services}; exec "$0" start ${services} ;;
	status)
		echo "qfw-telemetry in ${PREFIX}:"; for s in ${services}; do status_one "${s}"; done ;;
	logs)
		for s in ${services}; do echo "=== ${s} (${LOG}/${s}.log)"; tail -n "${LINES:-20}" "${LOG}/${s}.log" 2>/dev/null; done ;;
	*)
		sed -n '2,13p' "$0"; exit 2 ;;
esac
