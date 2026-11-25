#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
. "${SCRIPT_DIR}/tools/compose-env.sh"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

restart=false

for var in "$@"
do
    if [ "$var" = "slurmdbd.conf" ] || [ "$var" = "slurm.conf" ] || [ "$var" = "cgroup.conf" ] || [ "$var" = "rest.conf" ] || [ "$var" = "gres.conf" ]
    then
        # Stream the checkout's file in as the new content of the volume's
        # copy, which keeps that copy's owner and mode and writes the bytes as
        # they are. (Echoing the content through bash -c expanded $ and
        # backticks and dropped trailing newlines.)
        docker exec -i slurmctld sh -c "cat >/etc/slurm/${var}" <"${SCRIPT_DIR}/${var}"
        restart=true
    fi
done
if $restart; then "${COMPOSE[@]}" restart; fi
