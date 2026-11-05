#!/usr/bin/env bash
# Submit the COMPSs chemistry example as a test user, wait for it and print
# where its results are.
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: run-local.sh   (prepare first with setup-local.sh)'
    exit 0
fi
[[ $# -eq 0 ]] || { echo 'Unexpected argument; use --help' >&2; exit 2; }
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a provisioned non-root user' >&2; exit 2; }

batch=/workspace/qfw-container-base/compss-chemistry/chemistry-nwqsim.sbatch
if ! docker exec slurmctld test -f "${batch}"; then
    echo 'Prepare the cluster first: ./compss/chemistry/setup-local.sh' >&2
    exit 2
fi
login_home=$(docker exec slurmctld getent passwd "${app_user}" | cut -d: -f6)
[[ ${login_home} == /workspace/home/* ]] || { echo 'User needs a shared home' >&2; exit 2; }
host_home=${QFW_CONTAINER_BASE}/home/${login_home#/workspace/home/}

echo 'Submitting; sbatch --wait returns when the job ends'
# A login shell applies the test user's QFw profile.
status=0
job=$(docker exec --user "${app_user}" --workdir "${login_home}" \
    --env "HOME=${login_home}" slurmctld \
    bash -lc 'sbatch --parsable --wait "$1"' _ "${batch}") || status=$?
job=${job%%;*}
[[ ${job} =~ ^[0-9]+$ ]] || { echo "Submission failed: ${job}" >&2; exit 1; }
echo "Job ${job}: exit status ${status}"
echo "Output:  ${host_home}/compss-chemistry-${job}.out"
if [[ ${status} -ne 0 ]]; then
    tail -n 40 "${host_home}/compss-chemistry-${job}.out" >&2 || true
    exit 1
fi
echo "Results: ${host_home}/compss-chemistry-${job}.json"
for graph in "${host_home}/.qfw-compss/${job}"-*/.COMPSs/"${job}"/monitor/complete_graph.dot; do
    latest_graph=${graph}
done
echo "Graph:   ${latest_graph}"
grep -h 'FMO-VQE energy' "${host_home}/compss-chemistry-${job}.out"
