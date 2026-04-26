#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
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

if ${DRY_RUN}; then
    echo "Would run startup sequence:"
    printf '  %q' "${COMPOSE[@]}"
    printf ' %q %q\n' up -d
    echo "  wait for: sacctmgr --immediate list cluster to succeed in slurmdbd"
    echo "  sleep 5"
    echo "  ./register_cluster.sh"
    exit 0
fi

set -xe

"${COMPOSE[@]}" up -d

wait_for_slurmdbd_ready

sleep 5

./register_cluster.sh
