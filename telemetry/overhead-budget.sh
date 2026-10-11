#!/bin/bash
#
# Measure what QFw's telemetry costs per job on this cluster: the same
# back-to-back job stream through the site fake IQM service in seven
# telemetry states, repeated and interleaved, with the client's latency and
# CPU from the stream's own summary and the QPM's CPU from /proc.
#
#   off         QFW_TELEMETRY=off                                every call site a boolean test
#   metrics     QFW_TELEMETRY=otlp QFW_TELEMETRY_SAMPLE=off      the production default
#   traces      ... QFW_TELEMETRY_SAMPLE=always                  full tracing
#   transport   ... QFW_TELEMETRY_TRANSPORT=1                    plus the transport spans
#   logs-error  ... QFW_TELEMETRY_LOGS=error                     plus the logs tier a production site would run
#   logs-debug  ... QFW_TELEMETRY_LOGS=debug                     the overlay as shipped: a job's story under its trace
#   logs-all    ... QFW_TELEMETRY_LOGS=all                       the ceiling: DEFw's transport chatter too
#
# Every state sets all four variables, because the overlay gives the
# containers the demo's values and a state must not inherit them.
#
# The fake IQM executes a job in about a millisecond, so the stream is the
# fastest job the framework can run and the relative overhead is a worst
# case. The numbers this produced on 2026-10-08 are the budget recorded in
# QFw's docs/design/benchmarking.md; run it again after a change to the
# instrumentation and compare.
#
# Needs: the cluster up with the telemetry stack (docker-compose.telemetry.yml),
# the site services started, and a QFw with the job stream example (#117) at
# QFW_PREFIX. Run on the host; takes about a quarter of an hour with the
# defaults.
#
#   ./telemetry/overhead-budget.sh [--jobs N] [--reps N] [--states "off metrics ..."] [--out DIR]
#   QFW_PREFIX=/workspace/qfw-container-base/qfw-install ./telemetry/overhead-budget.sh
set -u

JOBS=300
REPS=3
OUT=""
STATES="off metrics traces transport logs-error logs-debug logs-all"
QFW_PREFIX="${QFW_PREFIX:-/opt/openqse/qfw}"
QFW_VENV="${QFW_VENV:-/opt/openqse/qfw-venv}"
QPM_NODE="${QFW_FAKE_IQM_NODE:-fake-iqm-head}"

while [ "$#" -gt 0 ]; do
	case "$1" in
		--jobs) JOBS="$2"; shift 2 ;;
		--reps) REPS="$2"; shift 2 ;;
		--out) OUT="$2"; shift 2 ;;
		--states) STATES="$2"; shift 2 ;;
		-h|--help) sed -n '2,25p' "$0"; exit 0 ;;
		*) echo "unknown option: $1" >&2; exit 2 ;;
	esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$(sed -n 's/^QFW_CONTAINER_BASE=//p' "${SCRIPT_DIR}/qfw-install.env" | tail -n 1)"
[ -n "${BASE}" ] || { echo "QFW_CONTAINER_BASE not found in qfw-install.env" >&2; exit 1; }
[ -n "${OUT}" ] || OUT="${BASE}/qfw-overhead-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${OUT}"
# The same directory as the containers see it.
COUT="/workspace/qfw-container-base/${OUT#"${BASE}/"}"
CSV="${OUT}/overhead.csv"
echo "rep,state,jobs,completed,failed,mean_ms,p50_ms,p95_ms,max_ms,jobs_per_min,client_cpu_ms_per_job,qpm_cpu_ms_per_job,t0,t1,qpm_pid,qpm_env" > "${CSV}"

state_env() {
	local t=otlp s=always x=0 l=off
	case "$1" in
		off) t=off; s=off ;;
		metrics) s=off ;;
		traces) ;;
		transport) x=1 ;;
		logs-error) x=1; l=error ;;
		logs-debug) x=1; l=debug ;;
		logs-all) x=1; l=all ;;
		*) echo "unknown state: $1" >&2; exit 2 ;;
	esac
	echo "-e QFW_TELEMETRY=${t} -e QFW_TELEMETRY_SAMPLE=${s} -e QFW_TELEMETRY_TRANSPORT=${x} -e QFW_TELEMETRY_LOGS=${l}"
}
qpm_pid() { docker exec "${QPM_NODE}" pgrep -f "defwp -d -x" | head -1; }
qpm_cpu_s() { docker exec "${QPM_NODE}" awk '{print ($14+$15)/100.0}' "/proc/$1/stat"; }
qpm_env() { docker exec "${QPM_NODE}" bash -c "tr '\0' '\n' < /proc/$1/environ | grep -E '^QFW_TELEMETRY(_SAMPLE|_TRANSPORT|_LOGS)?=' | sort | tr '\n' ' '"; }

run_stream() {
	# The stream from QFW_PREFIX in site mode, as root, with the state's
	# variables from the docker exec environment.
	local result="$1"
	shift
	docker exec "$@" -e QFW_EXAMPLE_RESULT_FILE="${result}" slurmctld bash -c '
		unset QFW_SITE_CONFIG _QFW_ACTIVE QFW_DEFW_VERSION
		export QFW_PREFIX='"${QFW_PREFIX}"'
		source "${QFW_PREFIX}/bin/qfw-activate" --venv '"${QFW_VENV}"' >/dev/null 2>&1
		export QFW_SHARED_ROOT=/workspace/qfw-container-base
		export QFW_RUN_BASE_DIR='"${COUT}"'/runs
		export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml
		export SALLOC_ACCOUNT=root SBATCH_ACCOUNT=root
		mkdir -p "${QFW_RUN_BASE_DIR}"
		cd "${QFW_SHARE_DIR}/examples"
		./qfw_job_stream.sh --service-mode site --backend fake-iqm \
			--jobs '"${JOBS}"' --interval 0 --qubits 3 --circuits ghz --shots 100 --seed 1 \
			--tolerate-failures'
}

for rep in $(seq 1 "${REPS}"); do
	for state in ${STATES}; do
		envargs=$(state_env "${state}")
		echo "### rep ${rep} state ${state}  $(date +%H:%M:%S)"
		# shellcheck disable=SC2086
		docker exec ${envargs} slurmctld qfw-site-services restart --target fake-iqm \
			> "${OUT}/restart-${rep}-${state}.log" 2>&1
		for _ in $(seq 1 30); do
			docker exec slurmctld qfw-site-services status 2>/dev/null | grep -q "Fake IQM: UP" && break
			sleep 2
		done
		sleep 3
		pid=$(qpm_pid)
		env_seen=$(qpm_env "${pid}")
		cpu0=$(qpm_cpu_s "${pid}")
		rm -f "${OUT}/stream-${rep}-${state}.jsonl"
		t0=$(date +%s)
		# shellcheck disable=SC2086
		run_stream "${COUT}/stream-${rep}-${state}.jsonl" ${envargs} \
			> "${OUT}/run-${rep}-${state}.log" 2>&1
		rc=$?
		t1=$(date +%s)
		cpu1=$(qpm_cpu_s "${pid}")
		python3 - "${OUT}/stream-${rep}-${state}.jsonl" "${rep}" "${state}" "${cpu0}" "${cpu1}" "${t0}" "${t1}" "${pid}" "${env_seen}" >> "${CSV}" <<'PY'
import json, sys
path, rep, state, cpu0, cpu1, t0, t1, pid, env_seen = sys.argv[1:]
rec = None
for line in open(path):
    d = json.loads(line)
    if d.get("kind") == "example" and d.get("example") == "job-stream":
        rec = d
m = rec["metrics"]; lat = m["latency_seconds"]
n = m["completed"] or 1
qpm = (float(cpu1) - float(cpu0)) / n * 1000
client = (m["process_cpu_seconds_per_job"] or 0) * 1000
print(",".join(str(x) for x in (rep, state, m["jobs"], m["completed"], m["failed"],
    f"{lat['mean']*1000:.3f}", f"{lat['p50']*1000:.3f}", f"{lat['p95']*1000:.3f}", f"{lat['max']*1000:.3f}",
    f"{m['jobs_per_minute']:.1f}", f"{client:.3f}", f"{qpm:.3f}", t0, t1, pid, env_seen.strip().replace(",", ";"))))
PY
		echo "  rc=${rc} $(tail -1 "${CSV}")"
	done
done

echo
echo "### medians of ${REPS} repetitions, and the delta against telemetry off"
python3 - "${CSV}" ${STATES} <<'PY'
import csv, statistics as st, sys
rows = list(csv.DictReader(open(sys.argv[1])))
states = sys.argv[2:]
by = {}
for r in rows:
    by.setdefault(r["state"], []).append(r)
def med(rs, k): return st.median(float(r[k]) for r in rs)
print(f"{'state':10} {'p50 ms':>8} {'p95 ms':>8} {'client cpu ms':>14} {'qpm cpu ms':>11}")
summ = {}
for state in states:
    rs = by.get(state)
    if not rs: continue
    summ[state] = {k: med(rs, c) for k, c in (("p50", "p50_ms"), ("p95", "p95_ms"), ("ccpu", "client_cpu_ms_per_job"), ("qcpu", "qpm_cpu_ms_per_job"))}
    s = summ[state]
    print(f"{state:10} {s['p50']:8.3f} {s['p95']:8.3f} {s['ccpu']:14.3f} {s['qcpu']:11.3f}")
off = summ.get("off")
for state in [x for x in states if x != "off"]:
    s = summ.get(state)
    if not (s and off): continue
    print(f"{state:10} vs off: p50 {s['p50']-off['p50']:+.3f} ms ({(s['p50']/off['p50']-1)*100:+.1f}%), "
          f"client cpu {s['ccpu']-off['ccpu']:+.3f} ms, qpm cpu {s['qcpu']-off['qcpu']:+.3f} ms per job")
PY
echo "results: ${OUT}"
