#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

if docker exec slurmctld bash -c \
        "/usr/bin/sacctmgr --noheader --parsable2 list cluster name=linux format=Cluster" \
        | grep -qx 'linux'; then
    echo "Cluster linux is already registered."
    exit 0
fi

docker exec slurmctld bash -c \
    "/usr/bin/sacctmgr --immediate add cluster name=linux"
"${COMPOSE[@]}" restart slurmdbd slurmctld
