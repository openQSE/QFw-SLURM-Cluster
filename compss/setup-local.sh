#!/usr/bin/env bash
# Prepare the local cluster for the COMPSs examples: start the cluster and the
# QFw services they need, and copy the examples where the nodes can see them.
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/.." && pwd)
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

examples=${QFW_CONTAINER_BASE}/compss-examples
rm -rf "${examples}"
mkdir -p "${examples}"
cp -R "${script_dir}/hello" "${script_dir}/chemistry" "${examples}/"
echo 'Ready: ./compss/run-local.sh hello'
