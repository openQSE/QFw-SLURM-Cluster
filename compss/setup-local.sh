#!/usr/bin/env bash
# Prepare the local cluster for the COMPSs examples: start the cluster and the
# QFw services they need, fetch the chemistry example's solver, and copy the
# examples where the nodes can see them.
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/.." && pwd)
source "${cluster_root}/qfw-install.env"
[[ ${QFW_CONTAINER_BASE} == /* ]] || { echo 'QFW_CONTAINER_BASE must be absolute' >&2; exit 2; }
docker info >/dev/null
if [[ $(docker inspect slurmctld --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    (cd "${cluster_root}" && ./do_startup.sh)
fi
# A rebuild does not change containers that are already running.
wanted=$(docker image inspect "${IMAGE_NAME}:${IMAGE_TAG}" --format '{{.Id}}' 2>/dev/null || true)
if [[ -n ${wanted} && $(docker inspect slurmctld --format '{{.Image}}') != "${wanted}" ]]; then
    if [[ -n $(docker exec slurmctld squeue --noheader) ]]; then
        echo 'The containers are on an older image, but jobs are running. When they end, run this again.' >&2
        exit 2
    fi
    echo "Moving the cluster to ${IMAGE_NAME}:${IMAGE_TAG}"
    (cd "${cluster_root}" && ./do_restart.sh --force-recreate && ./tools/provision-qfw-cluster.sh)
fi
docker exec slurmctld test -x /opt/COMPSs/Runtime/scripts/user/launch_compss || {
    echo 'The image has no COMPSs; configure it with --with-compss and rebuild' >&2
    exit 2
}
for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done

if [[ ! -f ${script_dir}/chemistry/chemistry_he/puccd.py ]] &&
    ! git -C "${cluster_root}" submodule update --init compss/chemistry/chemistry_he; then
    echo 'Could not fetch chemistry_he, so only the hello example will run.' >&2
    echo 'The chemistry example needs a git clone of this repository.' >&2
fi

examples=${QFW_CONTAINER_BASE}/compss-examples
rm -rf "${examples}"
mkdir -p "${examples}"
# chemistry_he's .git is a pointer that means nothing on the nodes.
tar -C "${script_dir}" --exclude=.git --exclude=__pycache__ -cf - hello chemistry |
    tar -C "${examples}" -xf -
echo 'Ready: ./compss/run-local.sh hello'
