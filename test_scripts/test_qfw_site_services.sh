#!/bin/bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command="${script_dir}/tools/qfw-site-services"
temporary="$(mktemp -d)"
trap 'rm -rf "${temporary}"' EXIT

"${command}" --dry-run start >"${temporary}/start.out"
grep -q '^slurmctld: qfw-dir-svc start ' "${temporary}/start.out"
grep -q '^nwqsim-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q '^iqm-head: qfw-qpm-svc start ' "${temporary}/start.out"
grep -q 'nwqsim-head,nwqsim-worker-1,nwqsim-worker-2' \
	"${temporary}/start.out"
grep -q 'QFw site services are ready' "${temporary}/start.out"

"${command}" --dry-run status >"${temporary}/status.out"
grep -q 'Directory service (slurmctld)' "${temporary}/status.out"
grep -q 'NWQSim QPM (nwqsim-head)' "${temporary}/status.out"
grep -q 'IQM QPM (iqm-head)' "${temporary}/status.out"
grep -q 'QFw Slurm gateway (slurmctld:18095)' "${temporary}/status.out"

"${command}" --dry-run stop >"${temporary}/stop.out"
iqm_line="$(grep -n '^iqm-head:' "${temporary}/stop.out" | cut -d: -f1)"
nwqsim_line="$(grep -n '^nwqsim-head:' "${temporary}/stop.out" | cut -d: -f1)"
directory_line="$(grep -n '^slurmctld:' "${temporary}/stop.out" | cut -d: -f1)"
[[ "${iqm_line}" -lt "${nwqsim_line}" ]]
[[ "${nwqsim_line}" -lt "${directory_line}" ]]

echo "qfw-site-services dry-run lifecycle passed"
