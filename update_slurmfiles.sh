#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

restart=false

for var in "$@"
do
    if [ "$var" = "slurmdbd.conf" ] || [ "$var" = "slurm.conf" ] || [ "$var" = "cgroup.conf" ] || [ "$var" = "rest.conf" ] || [ "$var" = "gres.conf" ]
    then
        export SLURM_TMP=$(cat $var)
        docker exec slurmctld bash -c "echo \"$SLURM_TMP\" >/etc/slurm/\"$var\""
        restart=true
    fi
done
if $restart; then "${COMPOSE[@]}" restart; fi
