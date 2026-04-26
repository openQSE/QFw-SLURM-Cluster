#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

docker exec slurmctld bash -c "/usr/bin/sacctmgr --immediate add cluster name=linux" && \
"${COMPOSE[@]}" restart slurmdbd slurmctld
