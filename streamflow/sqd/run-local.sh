#!/usr/bin/env bash
set -euo pipefail
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a non-root application user' >&2; exit 2; }
workspace=/workspace/qfw-container-base/streamflow-sqd
inputs=${1:-inputs.yml}
run_id=${SQD_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}
[[ ${run_id} =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || { echo 'Invalid run name' >&2; exit 2; }
run=${workspace}/runs/${run_id}
docker exec --user "${app_user}" slurmctld mkdir -p "${workspace}/runs"
docker exec --user "${app_user}" slurmctld mkdir "${run}"
if ! docker exec --user "${app_user}" slurmctld bash -c \
    '"$1/coordinator/bin/python" "$1/run.py" "$1" "$2" "$3" > "$2/streamflow.log" 2>&1' _ "${workspace}" "${run}" "${inputs}"; then
    docker exec --user "${app_user}" slurmctld tail -n 40 "${run}/streamflow.log" >&2
    exit 1
fi
printf 'Results: %s/output/state.json\nLog: %s/streamflow.log\n' "${run}" "${run}"
