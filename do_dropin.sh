#!/bin/bash

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run]

Options:
  --dry-run   Print the interactive docker exec command without running it
EOF
}

DRY_RUN=false

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

if ${DRY_RUN}; then
    echo "Would run:"
    echo "  docker exec -it slurmctld bash"
    exit 0
fi

set -xe

docker exec -it slurmctld bash
