#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then
    echo 'Usage: run-local.sh (backend bindings: streamflow.yml)'
    exit 0
fi
[[ $# -eq 0 ]] || { echo 'Unexpected argument; use --help' >&2; exit 2; }
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
app_user=${QFW_USER:-user-a}
run_id=${CHEMISTRY_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}
[[ ${run_id} =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { echo 'Invalid run name' >&2; exit 2; }
[[ ${app_user} != root ]] || { echo 'Use a provisioned non-root user' >&2; exit 2; }
[[ ${QFW_CONTAINER_BASE} == /* ]] || { echo 'QFW_CONTAINER_BASE must be absolute' >&2; exit 2; }

runtime=/workspace/qfw-container-base/streamflow-chemistry
if ! docker exec slurmctld test -f "${runtime}/run.py"; then
    echo 'Prepare the cluster first: ./streamflow/chemistry/setup-local.sh' >&2
    exit 2
fi
login_home=$(docker exec slurmctld getent passwd "${app_user}" | cut -d: -f6)
[[ ${login_home} == /workspace/home/* ]] || { echo 'User needs a shared home' >&2; exit 2; }
container_run=${login_home}/chemistry-streamflow-${run_id}
host_run=${QFW_CONTAINER_BASE}/home/${login_home#/workspace/home/}/chemistry-streamflow-${run_id}
[[ ! -e ${host_run} ]] || { echo 'Run already exists' >&2; exit 2; }

docker exec --user "${app_user}" slurmctld mkdir "${container_run}"
if ! docker exec --user "${app_user}" --env "HOME=${login_home}" slurmctld \
    "${runtime}/venv-0.2.0rc3/bin/python" "${runtime}/run.py" "${runtime}" "${container_run}" > "${host_run}/streamflow.log" 2>&1; then
    tail -n 40 "${host_run}/streamflow.log" >&2
    exit 1
fi
printf 'Results and logs: %s\n' "${host_run}"
