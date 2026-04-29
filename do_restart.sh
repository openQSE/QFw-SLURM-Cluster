#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
DRY_RUN=false
FORCE_RECREATE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--force-recreate]

Options:
  --dry-run          Print the compose command without running it
  --force-recreate   Recreate containers with docker compose up -d
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force-recreate)
            FORCE_RECREATE=true
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

if ${DRY_RUN}; then
    echo "Would run:"
    printf '  %q' "${COMPOSE[@]}"
    if ${FORCE_RECREATE}; then
        printf ' %q %q %q\n' up -d --force-recreate
    else
        printf ' %q\n' restart
    fi
    exit 0
fi

set -xe

if ${FORCE_RECREATE}; then
    "${COMPOSE[@]}" up -d --force-recreate
else
    "${COMPOSE[@]}" restart
fi
