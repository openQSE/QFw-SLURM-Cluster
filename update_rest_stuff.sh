#!/usr/bin/env bash

# TJN: Hack to get all the rest bits in place on a new setup
#      in case they are missing or goofed.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

restart=false

files="slurmdbd.conf slurm.conf rest.conf jwt.key"
images="slurmctld slurmdbd slurmrestd"

for img in $images ; do
    echo "=== Image: $img ==="
    for file in $files ; do
        fqp_file="/etc/slurm/$file"
        #echo " >> File: $fqp_file"

        docker exec -ti $img ls -l $fqp_file || echo "Error: missing $img:$fqp_file"
    done
done

#
# If pass 'copy' arg to script, we will do following.
#
if [ "${1:-}" == "copy" ] ; then
    restart=true
    for img in $images ; do
        echo "=== Image: $img ==="
        for file in $files ; do
            fqp_file="/etc/slurm/$file"
            #echo " >>File: $fqp_file"

            docker cp $file $img:$fqp_file                   || echo "Error: copy problem $img:$fqp_file"
            docker exec -ti $img chown slurm.slurm $fqp_file || echo "Error: chown problem $img:$fqp_file"

            if [ "$file" == "jwt.key" ] ; then
                docker exec -ti $img chmod 600 $fqp_file     || echo "Error: chmod problem $img:$fqp_file"
            fi
            if [ "$file" == "slurmdbd.conf" ] ; then
                docker exec -ti $img chmod 600 $fqp_file     || echo "Error: chmod problem $img:$fqp_file"
            fi
        done

    done
fi

if $restart; then "${COMPOSE[@]}" restart; fi
