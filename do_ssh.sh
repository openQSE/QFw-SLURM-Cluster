#!/bin/bash

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [container]

Arguments:
  container   Container name to enter. Default: slurmctld

Options:
  --dry-run   Print the docker exec command without running it
EOF
}

DRY_RUN=false
TARGET="slurmctld"

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
            if [ "${TARGET}" != "slurmctld" ]; then
                echo "Too many arguments: $1" >&2
                usage >&2
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

if ${DRY_RUN}; then
    echo "Would run:"
    echo "  docker exec -it ${TARGET} bash"
    exit 0
fi

set -xe

docker exec -it "${TARGET}" bash
