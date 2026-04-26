#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

wait_for_slurmdbd_ready() {
   #str="slurmdbd: slurmdbd version"
   str="slurmdbd version"

   while true; do
    if "${COMPOSE[@]}" logs | grep -q "$str" ; then
        echo "SlurmDBD ready!"
        break
    else
        echo "Waiting on SlurmDBD..."
        sleep 2
    fi
   done
}

set -xe

"${COMPOSE[@]}" up -d

wait_for_slurmdbd_ready

sleep 5

./register_cluster.sh
