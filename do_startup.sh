#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
. "${SCRIPT_DIR}/tools/compose-env.sh"
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run]

Options:
  --dry-run   Print the compose startup sequence without running it
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

wait_for_slurmdbd_ready() {
   while true; do
    if docker exec slurmdbd /usr/bin/sacctmgr --immediate list cluster >/dev/null 2>&1 ; then
        echo "SlurmDBD ready!"
        break
    else
        echo "Waiting on SlurmDBD..."
        sleep 2
    fi
   done
}

# The containers mount the etc_slurm named volume over the image's /etc/slurm.
# Compose fills that volume from the image only when it creates it, so on a
# cluster that already existed the Slurm configuration lags the checkout after a
# pull. A node added to docker-compose.yml and slurm.conf then gets its
# container, but its slurmd finds no NodeName and exits at once, and
# ./tools/provision-qfw-cluster.sh fails on it (#77). Refresh the files that
# differ before registering and provisioning. ./update_slurmfiles.sh restarts
# the containers, which also brings back a slurmd that had exited.
slurm_files="slurm.conf slurmdbd.conf cgroup.conf rest.conf gres.conf"

stale_slurm_files() {
    local file
    for file in ${slurm_files}; do
        if ! docker exec slurmctld cat "/etc/slurm/${file}" 2>/dev/null |
                cmp -s - "${SCRIPT_DIR}/${file}"; then
            echo "${file}"
        fi
    done
}

refresh_slurm_files() {
    local stale
    stale="$(stale_slurm_files)"
    if [ -z "${stale}" ]; then
        return 0
    fi
    # shellcheck disable=SC2086
    echo "---> Slurm configuration in the etc_slurm volume differs from the checkout:" ${stale}
    echo "---> Refreshing it with ./update_slurmfiles.sh, which restarts the containers ..."
    # shellcheck disable=SC2086
    ./update_slurmfiles.sh ${stale}
    wait_for_slurmdbd_ready
}

qfw_container_base() {
    awk -F= '$1 == "QFW_CONTAINER_BASE" {
        print substr($0, index($0, "=") + 1)
    }' "${ENV_FILE}" | tail -n 1
}

if ${DRY_RUN}; then
    echo "Would run startup sequence:"
    printf '  %q' "${COMPOSE[@]}"
    printf ' %q %q\n' up -d
    echo "  wait for: sacctmgr --immediate list cluster to succeed in slurmdbd"
    echo "  refresh the Slurm files in the etc_slurm volume that differ from the checkout:"
    echo "    ./update_slurmfiles.sh <files>, then wait for slurmdbd again"
    echo "  sleep 5"
    echo "  ./register_cluster.sh"
    echo "  wait for: sacctmgr --immediate list cluster to succeed in slurmdbd"
    echo "  ./tools/provision-qfw-cluster.sh"
    exit 0
fi

set -xe

QFW_CONTAINER_BASE="$(qfw_container_base)"
if [[ "${QFW_CONTAINER_BASE}" != /* ]]; then
    echo "QFW_CONTAINER_BASE must be an absolute path in ${ENV_FILE}" >&2
    exit 1
fi
install -d -m 0755 "${QFW_CONTAINER_BASE}/home"

"${COMPOSE[@]}" up -d

wait_for_slurmdbd_ready

refresh_slurm_files

sleep 5

./register_cluster.sh

wait_for_slurmdbd_ready

./tools/provision-qfw-cluster.sh
