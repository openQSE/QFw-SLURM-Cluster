#!/usr/bin/env bash
# Run a COMPSs example as a test user, wait for it and show the result.
set -euo pipefail
usage='Usage: run-local.sh hello|chemistry   (prepare first with setup-local.sh)'
case "${1:-}" in
    hello) batch=hello/hello.sbatch ;;
    chemistry) batch=chemistry/chemistry-nwqsim.sbatch ;;
    --help) echo "${usage}"; exit 0 ;;
    *) echo "${usage}" >&2; exit 2 ;;
esac
name=$1
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/.." && pwd)
source "${cluster_root}/qfw-install.env"
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a provisioned non-root user' >&2; exit 2; }

batch=/workspace/qfw-container-base/compss-examples/${batch}
if ! docker exec slurmctld test -f "${batch}"; then
    echo 'Prepare the cluster first: ./compss/setup-local.sh' >&2
    exit 2
fi
login_home=$(docker exec slurmctld getent passwd "${app_user}" | cut -d: -f6)
[[ ${login_home} == /workspace/home/* ]] || { echo 'User needs a shared home' >&2; exit 2; }
host_home=${QFW_CONTAINER_BASE}/home/${login_home#/workspace/home/}

# Workers from a job that was cancelled can stay behind and break the next one.
if [[ -z $(docker exec slurmctld squeue --noheader --user "${app_user}") ]]; then
    for node in c1 c2 c3; do
        docker exec "${node}" pkill -9 -u "${app_user}" 2>/dev/null || true
    done
fi

echo "Running the ${name} example; this waits until the job ends"
# A login shell applies the test user's QFw profile.
status=0
job=$(docker exec --user "${app_user}" --workdir "${login_home}" \
    --env "HOME=${login_home}" slurmctld \
    bash -lc 'sbatch --parsable --wait "$1"' _ "${batch}") || status=$?
job=${job%%;*}
[[ ${job} =~ ^[0-9]+$ ]] || { echo "Submission failed: ${job}" >&2; exit 1; }
output=${host_home}/compss-${name}-${job}.out
echo "Job ${job}: exit status ${status}"
if [[ ${status} -ne 0 ]]; then
    tail -n 40 "${output}" >&2 || true
    echo "Output:  ${output}" >&2
    exit 1
fi
grep -hE '^hello: |FMO-VQE energy' "${output}" | sed 's/^hello: //'
echo "Output:  ${output}"
if [[ -f ${output%.out}.json ]]; then
    echo "Results: ${output%.out}.json"
fi
for graph in "${host_home}/.qfw-compss/${job}"-*/.COMPSs/"${job}"/monitor/complete_graph.dot; do
    latest_graph=${graph}
done
echo "Graph:   ${latest_graph}"
