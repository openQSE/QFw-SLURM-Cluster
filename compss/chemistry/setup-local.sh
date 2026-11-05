#!/usr/bin/env bash
# Prepare the local cluster for the COMPSs chemistry example: start the
# cluster and the site services it needs, and copy the example into the shared
# directory.
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
[[ ${QFW_CONTAINER_BASE} == /* ]] || { echo 'QFW_CONTAINER_BASE must be absolute' >&2; exit 2; }
docker info >/dev/null
if [[ $(docker inspect slurmctld --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    (cd "${cluster_root}" && ./do_startup.sh)
fi
docker exec slurmctld test -x /opt/COMPSs/Runtime/scripts/user/launch_compss || {
    echo 'The image has no COMPSs; configure it with --with-compss and rebuild' >&2
    exit 2
}
for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done

example=${QFW_CONTAINER_BASE}/compss-chemistry
rm -rf "${example}"
mkdir -p "${example}"
cp -R "${script_dir}/he4_fmo_vqe.py" "${script_dir}/chemistry-nwqsim.sbatch" \
    "${script_dir}/chemistry_he" "${example}/"
echo 'Ready: ./compss/chemistry/run-local.sh'
