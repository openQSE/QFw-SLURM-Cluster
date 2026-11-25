#!/bin/bash
#
# Check a bare-metal telemetry stack end to end, or a client node's path to
# it. Sends one synthetic trace, log line and metric for the service
# "qfw-check" through the collector and looks for them in Tempo, Loki and
# Prometheus, the way a QFw job's signals travel.
#
#   On the telemetry host:   qfw-telemetry-check
#   On a client node:        qfw-telemetry-check --endpoint http://qpm-server:4318
#
# With --endpoint only the send is checked: an HTTP 200 from the collector
# means the node can reach it through the firewall. Everything else is read
# from the stores on 127.0.0.1, so run the full check on the telemetry host.
set -u

ENDPOINT="http://127.0.0.1:4318"; LOCAL=1
GRAFANA="http://127.0.0.1:${GF_SERVER_HTTP_PORT:-3000}"
while [[ $# -gt 0 ]]; do
	case "$1" in
		--endpoint) ENDPOINT="${2%/}"; LOCAL=0; shift 2 ;;
		--grafana) GRAFANA="${2%/}"; shift 2 ;;
		-h|--help) sed -n '2,13p' "$0"; exit 0 ;;
		*) echo "check.sh: unknown option $1" >&2; exit 2 ;;
	esac
done
command -v python3 >/dev/null || { echo "check.sh: python3 is required" >&2; exit 2; }
rc=0
say() { printf "  %-34s %s\n" "$1" "$2"; }
fail() { say "$1" "FAIL: $2"; rc=1; }

if [[ ${LOCAL} -eq 1 ]]; then
	echo "readiness on 127.0.0.1:"
	for pair in "tempo http://127.0.0.1:3200/ready" "loki http://127.0.0.1:3100/ready" \
		"prometheus http://127.0.0.1:9090/-/ready" "collector http://127.0.0.1:13133/" "grafana ${GRAFANA}/api/health"; do
		name="${pair%% *}"; url="${pair#* }"
		code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "${url}")"
		[[ "${code}" == 200 ]] && say "${name}" "UP" || fail "${name}" "HTTP ${code} from ${url}"
	done
fi

# One trace, one log line stitched to it and one counter, as OTLP/JSON.
host="$(hostname -s)"
read -r trace_id span_id now_ns < <(python3 -c 'import secrets, time; print(secrets.token_hex(16), secrets.token_hex(8), time.time_ns())')
stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
resource='{"attributes":[{"key":"service.name","value":{"stringValue":"qfw-check"}},{"key":"qfw.component.role","value":{"stringValue":"check"}},{"key":"qfw.device.name","value":{"stringValue":"'"${host}"'"}}]}'
traces='{"resourceSpans":[{"resource":'"${resource}"',"scopeSpans":[{"scope":{"name":"qfw-check"},"spans":[{"traceId":"'"${trace_id}"'","spanId":"'"${span_id}"'","name":"qfw.check","kind":1,"startTimeUnixNano":"'"${now_ns}"'","endTimeUnixNano":"'"$((now_ns + 1000000))"'","attributes":[{"key":"qfw.check.host","value":{"stringValue":"'"${host}"'"}}]}]}]}]}'
logs='{"resourceLogs":[{"resource":'"${resource}"',"scopeLogs":[{"scope":{"name":"qfw-check"},"logRecords":[{"timeUnixNano":"'"${now_ns}"'","severityNumber":9,"severityText":"INFO","body":{"stringValue":"qfw-check from '"${host}"' at '"${stamp}"'"},"traceId":"'"${trace_id}"'","spanId":"'"${span_id}"'"}]}]}]}'
metrics='{"resourceMetrics":[{"resource":'"${resource}"',"scopeMetrics":[{"scope":{"name":"qfw-check"},"metrics":[{"name":"qfw.check","unit":"1","sum":{"aggregationTemporality":1,"isMonotonic":true,"dataPoints":[{"startTimeUnixNano":"'"$((now_ns - 1000000000))"'","timeUnixNano":"'"${now_ns}"'","asInt":"1","attributes":[{"key":"qfw.check.host","value":{"stringValue":"'"${host}"'"}}]}]}}]}]}]}'

echo "sending to ${ENDPOINT}:"
for pair in "traces ${traces}" "logs ${logs}" "metrics ${metrics}"; do
	signal="${pair%% *}"; body="${pair#* }"
	code="$(curl -s -o /dev/null -m 10 -w '%{http_code}' -H 'Content-Type: application/json' -X POST --data "${body}" "${ENDPOINT}/v1/${signal}")"
	[[ "${code}" == 200 ]] && say "${signal}" "accepted" || fail "${signal}" "HTTP ${code} (000 = no route or nothing listening)"
done
if [[ ${LOCAL} -eq 0 ]]; then
	[[ ${rc} -eq 0 ]] && echo "this node reaches the collector; the signals carry trace ${trace_id}" || echo "this node cannot reach the collector"
	exit ${rc}
fi

echo "looking for them in the stores (up to 30 s):"
found_trace=0; found_log=0; found_metric=0
for i in $(seq 1 15); do
	now=$(date +%s)
	if [[ ${found_trace} -eq 0 ]] && curl -s -m 5 "http://127.0.0.1:3200/api/traces/${trace_id}" | grep -q '"qfw.check"'; then found_trace=1; fi
	if [[ ${found_log} -eq 0 ]] && curl -s -m 5 -G 'http://127.0.0.1:3100/loki/api/v1/query_range' --data-urlencode 'query={service_name="qfw-check"}' --data-urlencode "start=$(( (now - 600) * 1000000000 ))" | grep -q "${stamp}"; then found_log=1; fi
	if [[ ${found_metric} -eq 0 ]] && curl -s -m 5 -G 'http://127.0.0.1:9090/api/v1/query' --data-urlencode 'query=qfw_check_total{service_name="qfw-check"}' | grep -q '"value"'; then found_metric=1; fi
	[[ ${found_trace} -eq 1 && ${found_log} -eq 1 && ${found_metric} -eq 1 ]] && break
	sleep 2
done
[[ ${found_trace} -eq 1 ]] && say "Tempo has the trace" "${trace_id}" || fail "Tempo" "trace ${trace_id} not found (the collector's traces pipeline, see log/otelcol.log)"
[[ ${found_log} -eq 1 ]] && say "Loki has the line" "stitched to it" || fail "Loki" "no qfw-check line (the collector's logs pipeline or Loki's OTLP endpoint)"
[[ ${found_metric} -eq 1 ]] && say "Prometheus has the counter" "qfw_check_total" || fail "Prometheus" "qfw_check_total absent (the collector's 8889 exporter or Prometheus's scrape of it)"
if curl -s -m 5 "${GRAFANA}/api/dashboards/uid/qfw-jobs" | grep -q '"QFw Jobs"'; then
	say "Grafana serves the dashboards" "${GRAFANA}/d/qfw-jobs"
else
	fail "Grafana dashboards" "QFw Jobs not provisioned (etc/grafana/provisioning, log/grafana)"
fi
[[ ${rc} -eq 0 ]] && echo "all good" || echo "something is off, see above"
exit ${rc}
