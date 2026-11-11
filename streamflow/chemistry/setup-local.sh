#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
[[ ${QFW_CONTAINER_BASE} == /* ]] || { echo 'QFW_CONTAINER_BASE must be absolute' >&2; exit 2; }
docker info >/dev/null
if [[ $(docker inspect slurmctld --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    (cd "${cluster_root}" && ./do_startup.sh)
fi
for target in directory nwqsim fake-iqm gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done
host_setup=${QFW_CONTAINER_BASE}/streamflow-chemistry
container_setup=/workspace/qfw-container-base/streamflow-chemistry
venv=/workspace/qfw-container-base/streamflow-chemistry/venv-0.2.0rc3
mkdir -p "${host_setup}"
rm -rf "${host_setup}/cwl" "${host_setup}/slurm"
cp -R "${script_dir}/tests" "${script_dir}/cwl" "${script_dir}/run.py" \
    "${script_dir}/streamflow.yml" "${script_dir}/requirements.txt" "${host_setup}/"
cp "${script_dir}/cases.yml" "${host_setup}/cases.yml"
cp "${script_dir}/local.yml" "${host_setup}/profile.yml"
if [[ ! -d ${QFW_CONTAINER_BASE}/chemistry_he ]]; then
    mkdir "${QFW_CONTAINER_BASE}/chemistry_he"
    tar -C "${cluster_root}/../chemistry_he" --exclude=.git --exclude=__pycache__ -cf - . | \
        tar -C "${QFW_CONTAINER_BASE}/chemistry_he" -xf -
fi
if ! docker exec slurmctld test -x "${venv}/bin/python"; then
    docker exec slurmctld uv venv --python python3 "${venv}"
fi
docker exec slurmctld uv pip install --python "${venv}" -r "${container_setup}/requirements.txt"
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a non-root application user' >&2; exit 2; }
login_home=$(docker exec slurmctld getent passwd "${app_user}" | cut -d: -f6)
[[ ${login_home} == /workspace/home/* ]] || { echo 'User needs a shared home' >&2; exit 2; }
echo 'Ready: ./streamflow/chemistry/run-local.sh'
