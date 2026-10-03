#!/bin/bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command="${script_dir}/tools/qfw-site-services"
temporary="$(mktemp -d)"
trap 'rm -rf "${temporary}"' EXIT
# The tests below check the v1 plane's defaults unless they ask for v2.
unset QFW_DEFW_VERSION QFW_SITE_CONFIG QFW_SITE_RUN_ROOT

grep -q '/etc/openqse/qfw-slurm/gateway.yaml' "${command}"
grep -q '/etc/openqse/qfw-slurm/plugin.conf' \
	"${script_dir}/config/qfw-slurm/plugstack.conf"
grep -q '/etc/openqse/qfw-slurm/plugin.conf' \
	"${script_dir}/config/qfw-slurm/burst-buffer.lua.conf"
if grep -R -q '/etc/qfw-slurm' \
	"${script_dir}/Dockerfile" \
	"${script_dir}/config/qfw-slurm" \
	"${script_dir}/tools/qfw-site-services"; then
	echo "retired qfw-slurm configuration root remains" >&2
	exit 1
fi

"${command}" --dry-run start >"${temporary}/start.out"
grep -q '^slurmctld: qfw-dir-svc start ' "${temporary}/start.out"
grep -q '^nwqsim-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^iqm-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^shim-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^ibm-156-nh: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^aws: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^fake-iqm-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^slurmctld: qfw gateway start$' "${temporary}/start.out"
grep -q 'nwqsim-head,nwqsim-worker-1,nwqsim-worker-2' \
	"${temporary}/start.out"
# A dry run starts nothing and checks nothing, so it must not report the plane
# ready. It used to, even with SSH to the nodes completely broken.
grep -q '^Dry run: printed the startup plan, started nothing\.$' \
	"${temporary}/start.out"
if grep -q 'QFw site services are ready' "${temporary}/start.out"; then
	echo "a dry run must not claim the service plane is ready" >&2
	exit 1
fi

"${command}" --dry-run status >"${temporary}/status.out"
grep -q '^slurmctld: qfw-dir-svc status ' "${temporary}/status.out"
grep -q '^nwqsim-head: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^iqm-head: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^shim-head: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^ibm-156-nh: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^aws: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^fake-iqm-head: qfw-qpm-svc status ' "${temporary}/status.out"
grep -q '^slurmctld: qfw gateway status$' "${temporary}/status.out"

(
	source "${command}"
	dry_run=false
	target=all
	json_status=false
	directory_ready() { echo '{"state":"stopped"}'; return 1; }
	nwqsim_ready() { echo '{"state":"stale"}'; return 1; }
	iqm_ready() { echo '{"state":"stale"}'; return 1; }
	shim_ready() { echo '{"state":"stale"}'; return 1; }
	ibm_ready() { echo '{"state":"stale"}'; return 1; }
	aws_ready() { echo '{"state":"stale"}'; return 1; }
	fake_iqm_ready() { echo '{"state":"stale"}'; return 1; }
	gateway_managed_ready() { echo 'not-ready'; return 1; }
	service_status
) >"${temporary}/health-summary.out"
cat >"${temporary}/health-summary.expected" <<'EOF'
QFw site services: DOWN

Directory: DOWN
NWQSim: DOWN
IQM: DOWN
Shim: DOWN
IBM: DOWN
AWS: DOWN
Fake IQM: DOWN
Gateway: DOWN
EOF
cmp "${temporary}/health-summary.expected" "${temporary}/health-summary.out"

(
	source "${command}"
	dry_run=false
	target=all
	json_status=true
	directory_ready() {
		echo 'qfw-dir-svc: service-plane state not found: /var/lib/qfw-site-services/directory/state/service-plane.json'
		return 1
	}
	nwqsim_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/nwqsim/state/service-plane.json'
		return 1
	}
	iqm_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/iqm-ornl-20q/state/service-plane.json'
		return 1
	}
	shim_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/shim-ornl-20q/state/service-plane.json'
		return 1
	}
	ibm_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/shim-ibm-156-nh/state/service-plane.json'
		return 1
	}
	aws_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/shim-aws-qpm/state/service-plane.json'
		return 1
	}
	fake_iqm_ready() {
		echo 'qfw-qpm-svc: service-plane state not found: /var/lib/qfw-site-services/qpm/fake-iqm/state/service-plane.json'
		return 1
	}
	gateway_managed_ready() { echo 'not-ready'; return 1; }
	service_status
) >"${temporary}/missing-state-health.json"
python3 - "${temporary}/missing-state-health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    status = json.load(stream)
assert status["schema"] == "qfw-site-services-status-v1"
assert status["state"] == "down"
assert all(
    service["state"] == "down"
    for service in status["services"].values()
)
assert status["services"]["directory"]["detail"]["state"] == "stopped"
PY

(
	source "${command}"
	dry_run=false
	target=all
	json_status=true
	directory_ready() { echo '{"state":"ready"}'; }
	nwqsim_ready() { echo '{"state":"ready"}'; }
	iqm_ready() { echo '{"state":"ready"}'; }
	shim_ready() { echo '{"state":"ready"}'; }
	ibm_ready() { echo '{"state":"ready"}'; }
	aws_ready() { echo '{"state":"ready"}'; }
	fake_iqm_ready() { echo '{"state":"ready"}'; }
	gateway_managed_ready() { echo 'ready'; }
	service_status
) >"${temporary}/health.json"
python3 - "${temporary}/health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    status = json.load(stream)
assert status["schema"] == "qfw-site-services-status-v1"
assert status["state"] == "up"
assert set(status["services"]) == {
    "directory", "nwqsim", "iqm", "shim", "ibm", "aws", "fake-iqm",
    "gateway"
}
PY

for target in directory nwqsim iqm shim ibm aws fake-iqm gateway; do
	"${command}" --dry-run start --target "${target}" \
		>"${temporary}/start-${target}.out"
	"${command}" --dry-run status --target "${target}" \
		>"${temporary}/status-${target}.out"
	"${command}" --dry-run restart --target "${target}" \
		>"${temporary}/restart-${target}.out"
	"${command}" --dry-run recover --target "${target}" \
		>"${temporary}/recover-${target}.out"
done
grep -q '^slurmctld: qfw-dir-svc start ' \
	"${temporary}/start-directory.out"
grep -q '^nwqsim-head: qfw-qpm-svc start ' \
	"${temporary}/start-nwqsim.out"
grep -q '^iqm-head: qfw-qpm-svc start ' \
	"${temporary}/start-iqm.out"
grep -q '^shim-head: qfw-qpm-svc start ' \
	"${temporary}/start-shim.out"
grep -q '^ibm-156-nh: qfw-qpm-svc start ' \
	"${temporary}/start-ibm.out"
grep -q '^aws: qfw-qpm-svc start ' \
	"${temporary}/start-aws.out"
grep -q '^fake-iqm-head: qfw-qpm-svc start ' \
	"${temporary}/start-fake-iqm.out"
grep -q '^slurmctld: qfw gateway start$' \
	"${temporary}/start-gateway.out"
if "${command}" --dry-run status --target missing >/dev/null 2>&1; then
	echo "unknown target unexpectedly succeeded" >&2
	exit 1
fi

"${command}" --dry-run stop >"${temporary}/stop.out"
gateway_line="$(grep -n 'qfw gateway stop$' "${temporary}/stop.out" | cut -d: -f1)"
fake_iqm_line="$(grep -n '^fake-iqm-head: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
aws_line="$(grep -n '^aws: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
ibm_line="$(grep -n '^ibm-156-nh: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
shim_line="$(grep -n '^shim-head: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
iqm_line="$(grep -n '^iqm-head: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
nwqsim_line="$(grep -n '^nwqsim-head: qfw-qpm-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
directory_line="$(grep -n '^slurmctld: qfw-dir-svc stop ' "${temporary}/stop.out" | cut -d: -f1)"
[[ "${gateway_line}" -lt "${fake_iqm_line}" ]]
[[ "${fake_iqm_line}" -lt "${aws_line}" ]]
[[ "${aws_line}" -lt "${ibm_line}" ]]
[[ "${ibm_line}" -lt "${shim_line}" ]]
[[ "${shim_line}" -lt "${iqm_line}" ]]
[[ "${iqm_line}" -lt "${nwqsim_line}" ]]
[[ "${nwqsim_line}" -lt "${directory_line}" ]]

(
	source "${command}"
	dry_run=false
	directory_ready() { return 0; }
	nwqsim_ready() { return 0; }
	iqm_ready() { return 0; }
	shim_ready() { return 0; }
	ibm_ready() { return 0; }
	aws_ready() { return 0; }
	fake_iqm_ready() { return 0; }
	gateway_managed_ready() { return 0; }
	run_qfw() { return 99; }
	run_gateway() { return 99; }
	start_services
) >"${temporary}/already-ready.out"
grep -q 'Directory service is already ready' "${temporary}/already-ready.out"
grep -q 'NWQSim QPM is already ready' "${temporary}/already-ready.out"
grep -q 'IQM QPM is already ready' "${temporary}/already-ready.out"
grep -q 'Shim QPM is already ready' "${temporary}/already-ready.out"
grep -q 'IBM Shim QPM is already ready' "${temporary}/already-ready.out"
grep -q 'AWS is already ready' "${temporary}/already-ready.out"
grep -q 'Fake IQM QPM is already ready' "${temporary}/already-ready.out"
grep -q 'QFw Slurm gateway is already ready' "${temporary}/already-ready.out"

: >"${temporary}/non-ready.events"
: >"${temporary}/non-ready.calls"
(
	source "${command}"
	dry_run=false
	directory_ready() { return 1; }
	nwqsim_ready() { return 1; }
	iqm_ready() { return 1; }
	shim_ready() { return 1; }
	ibm_ready() { return 1; }
	aws_ready() { return 1; }
	fake_iqm_ready() { return 1; }
	gateway_managed_ready() { return 1; }
	require_directory() { return 0; }
	wait_for_gateway() { return 0; }
	stop_directory() { echo stop-directory >>"${temporary}/non-ready.calls"; }
	stop_nwqsim() { echo stop-nwqsim >>"${temporary}/non-ready.calls"; }
	stop_iqm() { echo stop-iqm >>"${temporary}/non-ready.calls"; }
	stop_shim() { echo stop-shim >>"${temporary}/non-ready.calls"; }
	stop_ibm() { echo stop-ibm >>"${temporary}/non-ready.calls"; }
	stop_aws() { echo stop-aws >>"${temporary}/non-ready.calls"; }
	stop_fake_iqm() { echo stop-fake-iqm >>"${temporary}/non-ready.calls"; }
	stop_gateway() { echo stop-gateway >>"${temporary}/non-ready.calls"; }
	run_qfw() { echo "run-qfw:$1:$2" >>"${temporary}/non-ready.calls"; }
	run_gateway() { echo "run-gateway:$1" >>"${temporary}/non-ready.calls"; }
	start_directory
	start_nwqsim
	start_iqm
	start_shim
	start_ibm
	start_aws
	start_fake_iqm
	start_gateway
) >"${temporary}/non-ready.events"
grep -q 'Directory service is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-directory$' "${temporary}/non-ready.calls"
grep -q 'NWQSim QPM is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-nwqsim$' "${temporary}/non-ready.calls"
grep -q 'IQM QPM is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-iqm$' "${temporary}/non-ready.calls"
grep -q 'Shim QPM is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-shim$' "${temporary}/non-ready.calls"
grep -q 'IBM Shim QPM is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-ibm$' "${temporary}/non-ready.calls"
grep -q 'AWS is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-aws$' "${temporary}/non-ready.calls"
grep -q 'Fake IQM QPM is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-fake-iqm$' "${temporary}/non-ready.calls"
grep -q 'QFw Slurm gateway is not ready; cleaning retained state' \
	"${temporary}/non-ready.events"
grep -q '^stop-gateway$' "${temporary}/non-ready.calls"
[[ "$(grep -c '^run-qfw:' "${temporary}/non-ready.calls")" -eq 7 ]]
grep -q '^run-gateway:start$' "${temporary}/non-ready.calls"

(
	source "${command}"
	dry_run=false
	directory_up=false
	nwqsim_up=true
	iqm_up=true
	shim_up=true
	ibm_up=true
	aws_up=true
	fake_iqm_up=true
	gateway_up=true
	directory_ready() { ${directory_up}; }
	nwqsim_ready() { ${nwqsim_up}; }
	iqm_ready() { ${iqm_up}; }
	shim_ready() { ${shim_up}; }
	ibm_ready() { ${ibm_up}; }
	aws_ready() { ${aws_up}; }
	fake_iqm_ready() { ${fake_iqm_up}; }
	gateway_managed_ready() { ${gateway_up}; }
	stop_gateway() { echo stop-gateway; gateway_up=false; }
	stop_fake_iqm() { echo stop-fake-iqm; fake_iqm_up=false; }
	stop_aws() { echo stop-aws; aws_up=false; }
	stop_ibm() { echo stop-ibm; ibm_up=false; }
	stop_shim() { echo stop-shim; shim_up=false; }
	stop_iqm() { echo stop-iqm; iqm_up=false; }
	stop_nwqsim() { echo stop-nwqsim; nwqsim_up=false; }
	start_directory() { echo start-directory; directory_up=true; }
	start_nwqsim() { echo start-nwqsim; nwqsim_up=true; }
	start_iqm() { echo start-iqm; iqm_up=true; }
	start_shim() { echo start-shim; shim_up=true; }
	start_ibm() { echo start-ibm; ibm_up=true; }
	start_aws() { echo start-aws; aws_up=true; }
	start_fake_iqm() { echo start-fake-iqm; fake_iqm_up=true; }
	start_gateway() { echo start-gateway; gateway_up=true; }
	stop_directory() { echo stop-directory; directory_up=false; }
	start_services
) >"${temporary}/partial-state.out"
sed '/QFw site services are ready/d' "${temporary}/partial-state.out" \
	>"${temporary}/partial-state.events"
cat >"${temporary}/partial-state.expected" <<'EOF'
stop-gateway
stop-fake-iqm
stop-aws
stop-ibm
stop-shim
stop-iqm
stop-nwqsim
start-directory
start-nwqsim
start-iqm
start-shim
start-ibm
start-aws
start-fake-iqm
start-gateway
EOF
cmp "${temporary}/partial-state.expected" "${temporary}/partial-state.events"

: >"${temporary}/rollback.events"
(
	source "${command}"
	dry_run=false
	directory_up=true
	nwqsim_up=false
	iqm_up=false
	shim_up=false
	ibm_up=false
	aws_up=false
	directory_ready() { ${directory_up}; }
	nwqsim_ready() { ${nwqsim_up}; }
	iqm_ready() { ${iqm_up}; }
	shim_ready() { ${shim_up}; }
	ibm_ready() { ${ibm_up}; }
	aws_ready() { ${aws_up}; }
	fake_iqm_ready() { return 1; }
	gateway_managed_ready() { return 1; }
	start_directory() { return 0; }
	start_nwqsim() {
		echo start-nwqsim >>"${temporary}/rollback.events"
		nwqsim_up=true
	}
	start_iqm() {
		echo start-iqm >>"${temporary}/rollback.events"
		iqm_up=true
	}
	start_shim() {
		echo start-shim >>"${temporary}/rollback.events"
		shim_up=true
	}
	start_ibm() {
		echo start-ibm >>"${temporary}/rollback.events"
		ibm_up=true
	}
	start_aws() {
		echo start-aws >>"${temporary}/rollback.events"
		aws_up=true
	}
	start_fake_iqm() {
		echo fail-fake-iqm >>"${temporary}/rollback.events"
		return 1
	}
	stop_shim() {
		echo stop-shim >>"${temporary}/rollback.events"
		shim_up=false
	}
	stop_ibm() {
		echo stop-ibm >>"${temporary}/rollback.events"
		ibm_up=false
	}
	stop_aws() {
		echo stop-aws >>"${temporary}/rollback.events"
		aws_up=false
	}
	stop_iqm() {
		echo stop-iqm >>"${temporary}/rollback.events"
		iqm_up=false
	}
	stop_nwqsim() {
		echo stop-nwqsim >>"${temporary}/rollback.events"
		nwqsim_up=false
	}
	stop_directory() {
		echo stop-directory >>"${temporary}/rollback.events"
		directory_up=false
	}
	! start_services
)
grep -q '^start-nwqsim$' "${temporary}/rollback.events"
grep -q '^start-iqm$' "${temporary}/rollback.events"
grep -q '^start-shim$' "${temporary}/rollback.events"
grep -q '^start-ibm$' "${temporary}/rollback.events"
grep -q '^start-aws$' "${temporary}/rollback.events"
grep -q '^fail-fake-iqm$' "${temporary}/rollback.events"
grep -q '^stop-aws$' "${temporary}/rollback.events"
grep -q '^stop-ibm$' "${temporary}/rollback.events"
grep -q '^stop-shim$' "${temporary}/rollback.events"
grep -q '^stop-iqm$' "${temporary}/rollback.events"
grep -q '^stop-nwqsim$' "${temporary}/rollback.events"
if grep -q '^stop-directory$' "${temporary}/rollback.events"; then
	echo "rollback stopped a pre-existing directory" >&2
	exit 1
fi

# UNKNOWN is the one state that carries a reason, because it means the status
# output could not be read at all, and it was the one state that printed none.
# A broken SSH path reported eight bare UNKNOWNs and the captured error, which
# named the cause outright, reached only --json.
(
	source "${command}"
	dry_run=false
	json_status=false
	target=all
	directory_ready() {
		echo "ssh: connect to host slurmctld port 22: Connection refused" >&2
		return 255
	}
	nwqsim_ready() { echo '{"state": "ready"}'; }
	iqm_ready() { echo '{"state": "ready"}'; }
	shim_ready() { echo '{"state": "ready"}'; }
	ibm_ready() { echo '{"state": "ready"}'; }
	aws_ready() { echo '{"state": "ready"}'; }
	fake_iqm_ready() { echo '{"state": "ready"}'; }
	gateway_managed_ready() { echo ready; }
	service_status
) >"${temporary}/unknown-reason.out" 2>&1 || true
grep -q '^Directory: UNKNOWN$' "${temporary}/unknown-reason.out"
grep -q '^  ssh: connect to host slurmctld port 22: Connection refused$' \
	"${temporary}/unknown-reason.out"
# A service that is merely stopped reports DOWN and needs no explaining, so the
# reason line belongs to UNKNOWN alone.
grep -q '^NWQSim: UP$' "${temporary}/unknown-reason.out"

# QFW_DEFW_VERSION=2 selects the DEFw v2 plane. It runs beside the v1 plane,
# from a site configuration and a run root of its own, and has only the
# directory and the QPMs that run on v2.
QFW_DEFW_VERSION=2 "${command}" --dry-run start >"${temporary}/v2-start.out"
cat >"${temporary}/v2-start.expected" <<'EOF'
NWQSim simulator nodes: nwqsim-head,nwqsim-worker-1,nwqsim-worker-2
slurmctld: qfw-dir-svc start --scope site --run-dir /var/lib/qfw-site-services-defw2/directory --site-config /etc/openqse/qfw/site-defw2.yaml --timeout 300 
nwqsim-head: qfw-qpm-svc start --scope site --run-dir /var/lib/qfw-site-services-defw2/qpm/nwqsim --site-config /etc/openqse/qfw/site-defw2.yaml --service-id nwqsim --timeout 300 
fake-iqm-head: qfw-qpm-svc start --scope site --run-dir /var/lib/qfw-site-services-defw2/qpm/fake-iqm --site-config /etc/openqse/qfw/site-defw2.yaml --service-id fake-iqm --timeout 300 
Dry run: printed the startup plan, started nothing.
EOF
cmp "${temporary}/v2-start.expected" "${temporary}/v2-start.out"

QFW_DEFW_VERSION=2 "${command}" --dry-run stop >"${temporary}/v2-stop.out"
cat >"${temporary}/v2-stop.expected" <<'EOF'
fake-iqm-head: qfw-qpm-svc stop --run-dir /var/lib/qfw-site-services-defw2/qpm/fake-iqm 
nwqsim-head: qfw-qpm-svc stop --run-dir /var/lib/qfw-site-services-defw2/qpm/nwqsim 
slurmctld: qfw-dir-svc stop --run-dir /var/lib/qfw-site-services-defw2/directory 
EOF
cmp "${temporary}/v2-stop.expected" "${temporary}/v2-stop.out"

QFW_DEFW_VERSION=2 "${command}" --dry-run status >"${temporary}/v2-status.out"
cat >"${temporary}/v2-status.expected" <<'EOF'
slurmctld: qfw-dir-svc status --run-dir /var/lib/qfw-site-services-defw2/directory 
nwqsim-head: qfw-qpm-svc status --run-dir /var/lib/qfw-site-services-defw2/qpm/nwqsim 
fake-iqm-head: qfw-qpm-svc status --run-dir /var/lib/qfw-site-services-defw2/qpm/fake-iqm 
EOF
cmp "${temporary}/v2-status.expected" "${temporary}/v2-status.out"

for target in iqm shim ibm aws gateway; do
	if QFW_DEFW_VERSION=2 "${command}" --dry-run start --target "${target}" \
		>/dev/null 2>"${temporary}/v2-${target}.err"; then
		echo "the v2 plane unexpectedly accepted ${target}" >&2
		exit 1
	fi
	grep -q "the DEFw v2 plane has no ${target}\." \
		"${temporary}/v2-${target}.err"
done
if QFW_DEFW_VERSION=3 "${command}" --dry-run status >/dev/null 2>&1; then
	echo "an unknown DEFw version unexpectedly succeeded" >&2
	exit 1
fi

# ssh hands the remote command a bare environment, so the version reaches a
# node only because run_qfw forwards it. Run the remote side here, with a
# stand-in for qfw-activate, to see what it exports.
mkdir -p "${temporary}/prefix/bin"
echo 'qfw-deactivate() { :; }' >"${temporary}/prefix/bin/qfw-activate"
for version in "" 2; do
	(
		QFW_DEFW_VERSION="${version}"
		source "${command}"
		QFW_INSTALL_PREFIX="${temporary}/prefix"
		ssh() {
			while [[ "$1" != /bin/bash ]]; do
				shift
			done
			shift
			bash "$@"
		}
		run_qfw nwqsim-head bash -c \
			'echo "version=${QFW_DEFW_VERSION-unset} site=${QFW_SITE_CONFIG}"'
	) >"${temporary}/forwarded-${version:-1}.out"
done
grep -q '^version=unset site=/etc/openqse/qfw/site.yaml$' \
	"${temporary}/forwarded-1.out"
grep -q '^version=2 site=/etc/openqse/qfw/site-defw2.yaml$' \
	"${temporary}/forwarded-2.out"

# A v2 status reports the v2 plane alone, and asks nothing of the components
# it does not have.
: >"${temporary}/v2-asked.calls"
(
	QFW_DEFW_VERSION=2
	source "${command}"
	dry_run=false
	target=all
	json_status=true
	directory_ready() { echo '{"state":"ready"}'; }
	nwqsim_ready() { echo '{"state":"ready"}'; }
	fake_iqm_ready() { echo '{"state":"ready"}'; }
	iqm_ready() { echo iqm >>"${temporary}/v2-asked.calls"; }
	shim_ready() { echo shim >>"${temporary}/v2-asked.calls"; }
	ibm_ready() { echo ibm >>"${temporary}/v2-asked.calls"; }
	aws_ready() { echo aws >>"${temporary}/v2-asked.calls"; }
	gateway_managed_ready() { echo gateway >>"${temporary}/v2-asked.calls"; }
	service_status
) >"${temporary}/v2-health.json"
python3 - "${temporary}/v2-health.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    status = json.load(stream)
assert status["state"] == "up"
assert list(status["services"]) == ["directory", "fake-iqm", "nwqsim"]
PY
[[ ! -s "${temporary}/v2-asked.calls" ]]

# Nor does a live v1 QPM or gateway hold up a v2 directory stop.
(
	QFW_DEFW_VERSION=2
	source "${command}"
	dry_run=false
	nwqsim_ready() { return 1; }
	fake_iqm_ready() { return 1; }
	iqm_ready() { return 0; }
	shim_ready() { return 0; }
	ibm_ready() { return 0; }
	aws_ready() { return 0; }
	gateway_managed_ready() { return 0; }
	require_directory_dependents_stopped
)

# The v2 start follows the v1 rules. A directory that was not ready is a new
# incarnation, so live QPMs are stopped and started again after it.
(
	QFW_DEFW_VERSION=2
	source "${command}"
	dry_run=false
	directory_up=false
	nwqsim_up=true
	fake_iqm_up=true
	directory_ready() { ${directory_up}; }
	nwqsim_ready() { ${nwqsim_up}; }
	fake_iqm_ready() { ${fake_iqm_up}; }
	stop_fake_iqm() { echo stop-fake-iqm; fake_iqm_up=false; }
	stop_nwqsim() { echo stop-nwqsim; nwqsim_up=false; }
	stop_directory() { echo stop-directory; directory_up=false; }
	start_directory() { echo start-directory; directory_up=true; }
	start_nwqsim() { echo start-nwqsim; nwqsim_up=true; }
	start_fake_iqm() { echo start-fake-iqm; fake_iqm_up=true; }
	start_target
) >"${temporary}/v2-partial-state.out"
cat >"${temporary}/v2-partial-state.expected" <<'EOF'
stop-fake-iqm
stop-nwqsim
start-directory
start-nwqsim
start-fake-iqm
QFw site services are ready.
EOF
cmp "${temporary}/v2-partial-state.expected" \
	"${temporary}/v2-partial-state.out"

# A failure stops only what this invocation started. The rollback silences
# the stops, so the stand-ins record them in a file.
: >"${temporary}/v2-rollback.out"
(
	QFW_DEFW_VERSION=2
	source "${command}"
	dry_run=false
	events="${temporary}/v2-rollback.out"
	directory_ready() { return 0; }
	nwqsim_ready() { return 1; }
	fake_iqm_ready() { return 1; }
	start_directory() { echo start-directory >>"${events}"; }
	start_nwqsim() { echo start-nwqsim >>"${events}"; }
	start_fake_iqm() { echo fail-fake-iqm >>"${events}"; return 1; }
	stop_nwqsim() { echo stop-nwqsim >>"${events}"; }
	stop_directory() { echo stop-directory >>"${events}"; }
	! start_target
)
cat >"${temporary}/v2-rollback.expected" <<'EOF'
start-directory
start-nwqsim
fail-fake-iqm
stop-nwqsim
EOF
cmp "${temporary}/v2-rollback.expected" "${temporary}/v2-rollback.out"

echo "qfw-site-services dry-run lifecycle passed"
